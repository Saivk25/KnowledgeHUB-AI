"""
CompareIntent (Milestone 9): resolves evidence independently for each
target (resource / concept / freeform phrase), then asks the LLM to
compare across all of them in one call. Approved design decisions
(docs/milestones/MILESTONE_9.md Section 4):

1. Partial evidence (some targets have local evidence, others don't)
   proceeds -- the LLM is instructed (see llm.COMPARE_SYSTEM_INSTRUCTIONS)
   to state plainly when a target has no evidence, never to silently fill
   the gap from general knowledge.
2. `provenance` stays a single top-level value (`LOCAL`) rather than
   growing a fourth enum member -- per-target detail (`hasEvidence`) is
   nested in `result.targets`, not folded into `provenance` itself.

Total insufficiency (every target has zero evidence) is a materially
different case from partial insufficiency: it behaves like EXPLAIN's
insufficient case, including honoring `useExternalFallback`/the
workspace's `allow_external_fallback` setting for a single combined
general-knowledge comparison -- this is the one place Compare's
provenance can become `EXTERNAL`.
"""

from __future__ import annotations

from fastapi import status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.deps import AppError
from app.models.concept import Concept
from app.models.resource import Resource, ResourceStatus
from app.models.workspace import Workspace
from app.schemas.chat import CitationOut
from app.schemas.intents import (
    CompareResult,
    CompareTarget,
    CompareTargetResult,
    IntentRequest,
    IntentResponse,
    IntentType,
)
from app.services.intents.base import IntentHandler
from app.services.llm import ComparisonEvidence, EvidenceChunk, get_llm_provider
from app.services.retrieval_service import (
    CitationResult,
    resolve_concept_evidence,
    resolve_freeform_evidence,
    resolve_resource_evidence,
)

settings = get_settings()

_TotalInsufficientMessage = (
    "I could not find sufficient evidence for any of these targets in your authorized documents."
)


def _resolve_target(
    db: Session, workspace: Workspace, target: CompareTarget
) -> tuple[list[EvidenceChunk], list[CitationResult]]:
    """Resolves one Compare target to its evidence, reusing exactly the
    same resource/concept/freeform resolution modes Summarize uses (one
    shared implementation via retrieval_service.py, not a second one
    duplicated here). Returns ([], []) for a target that doesn't exist,
    isn't ready, or (for a freeform phrase) doesn't clear the same
    sufficiency bar Explain/Summarize's freeform mode uses -- this
    function never raises for a missing/empty target, since one target
    lacking evidence is an expected, honestly-reportable outcome for
    Compare, not an error."""
    if target.resourceId:
        resource = db.get(Resource, target.resourceId)
        not_ready = (
            resource is None
            or resource.workspace_id != workspace.id
            or resource.status != ResourceStatus.READY
        )
        if not_ready:
            return [], []
        return resolve_resource_evidence(
            db, target.resourceId, max_chunks=settings.COMPARE_MAX_EVIDENCE_PER_TARGET
        )

    if target.conceptId:
        concept = db.get(Concept, target.conceptId)
        if concept is None or concept.workspace_id != workspace.id:
            return [], []
        return resolve_concept_evidence(
            db, target.conceptId, max_chunks=settings.COMPARE_MAX_EVIDENCE_PER_TARGET
        )

    question = target.question or target.label
    evidence, citations, verdict = resolve_freeform_evidence(
        db, workspace.id, question, top_k=settings.COMPARE_MAX_EVIDENCE_PER_TARGET
    )
    if not verdict.is_sufficient:
        return [], []
    return evidence, citations


class CompareIntent(IntentHandler):
    intent_type = IntentType.COMPARE

    def handle(self, db: Session, workspace: Workspace, request: IntentRequest) -> IntentResponse:
        targets = request.targets or []
        if len(targets) < 2:
            raise AppError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "COMPARE_NEEDS_TWO_TARGETS",
                "Compare needs at least two targets.",
            )
        if len(targets) > settings.COMPARE_MAX_TARGETS:
            raise AppError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "TOO_MANY_COMPARE_TARGETS",
                f"Compare accepts at most {settings.COMPARE_MAX_TARGETS} targets.",
            )

        resolved: list[tuple[str, list[EvidenceChunk], list[CitationResult]]] = []
        for target in targets:
            evidence, citations = _resolve_target(db, workspace, target)
            resolved.append((target.label, evidence, citations))

        if all(not evidence for _, evidence, _ in resolved):
            return self._total_insufficiency(db, workspace, request, resolved)

        # Reassign globally-unique citation/evidence order numbers across
        # all targets (each target's own evidence/citations were built
        # starting at 1 independently) so the LLM's [n] citations are
        # unambiguous across the whole comparison.
        comparison_evidence: list[ComparisonEvidence] = []
        all_citations: list[CitationOut] = []
        target_results: list[CompareTargetResult] = []
        next_order = 1
        for label, evidence, citations in resolved:
            renumbered_evidence: list[EvidenceChunk] = []
            renumbered_citations: list[CitationOut] = []
            for e, c in zip(evidence, citations, strict=True):
                renumbered_evidence.append(
                    EvidenceChunk(
                        order=next_order,
                        document_filename=e.document_filename,
                        page_number=e.page_number,
                        content=e.content,
                    )
                )
                renumbered_citations.append(
                    CitationOut(
                        documentId=c.document_id,
                        documentFilename=c.document_filename,
                        chunkId=c.chunk_id,
                        pageNumber=c.page_number,
                        excerpt=c.excerpt,
                        order=next_order,
                        targetLabel=label,
                    )
                )
                next_order += 1
            comparison_evidence.append(ComparisonEvidence(label=label, evidence=renumbered_evidence))
            all_citations.extend(renumbered_citations)
            target_results.append(
                CompareTargetResult(label=label, hasEvidence=bool(evidence), citations=renumbered_citations)
            )

        content = get_llm_provider().compare(comparison_evidence)
        has_gap = any(not r.hasEvidence for r in target_results)

        return IntentResponse(
            intent=IntentType.COMPARE,
            status="OK",
            # Approved design decision 2: provenance stays the single
            # top-level LOCAL value; per-target gaps are visible in
            # result.targets[*].hasEvidence, not in provenance itself.
            provenance="LOCAL",
            sufficiencyScore=1.0 if not has_gap else 0.5,
            retrievalConfidence=1.0 if not has_gap else 0.5,
            canOfferExternalFallback=has_gap,
            citations=all_citations,
            result=CompareResult(content=content, targets=target_results),
        )

    def _total_insufficiency(
        self,
        db: Session,
        workspace: Workspace,
        request: IntentRequest,
        resolved: list[tuple[str, list[EvidenceChunk], list[CitationResult]]],
    ) -> IntentResponse:
        """Every target came back with zero evidence -- behaves like
        EXPLAIN's insufficient case, including honoring the same external-
        fallback consent gates, since this is materially different from
        the partial-evidence case handle() otherwise takes (approved
        design, MILESTONE_9.md Section 4)."""
        target_results = [
            CompareTargetResult(label=label, hasEvidence=False, citations=[]) for label, _, _ in resolved
        ]

        if request.useExternalFallback or workspace.allow_external_fallback:
            labels = ", ".join(label for label, _, _ in resolved)
            llm = get_llm_provider()
            content = llm.answer_general_knowledge(f"Compare: {labels}")
            return IntentResponse(
                intent=IntentType.COMPARE,
                status="OK",
                provenance="EXTERNAL",
                sufficiencyScore=0.0,
                retrievalConfidence=0.0,
                canOfferExternalFallback=False,
                citations=[],
                result=CompareResult(content=content, targets=target_results),
            )

        return IntentResponse(
            intent=IntentType.COMPARE,
            status="INSUFFICIENT",
            provenance=None,
            sufficiencyScore=0.0,
            retrievalConfidence=0.0,
            canOfferExternalFallback=True,
            citations=[],
            result=CompareResult(content=_TotalInsufficientMessage, targets=target_results),
        )
