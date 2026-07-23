"""
QuizIntent (Milestone 10): a two-turn flow -- a generation turn creates a
QuizAttempt (server-side answer key, see app/models/study.py) and returns
questions with no answer key; a grading turn (`quizId` + `quizAnswers`)
grades against that stored key and returns per-question correctness.
MCQ-only (approved design, MILESTONE_10.md Section 4 decision 2), so
grading is exact-match against the stored `correctChoice` index -- no LLM
call needed to grade. Uses the same three-mode resolution
(resource-target, concept-target, freeform question) Summarize already
established. See docs/milestones/MILESTONE_10.md Section 3.3.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.deps import AppError
from app.models.concept import Concept
from app.models.resource import Resource, ResourceStatus
from app.models.study import QuizAttempt, QuizAttemptStatus
from app.models.workspace import Workspace
from app.schemas.chat import CitationOut
from app.schemas.intents import (
    IntentRequest,
    IntentResponse,
    IntentType,
    QuizGradedQuestionOut,
    QuizQuestionOut,
    QuizResult,
)
from app.services.intents.base import IntentHandler
from app.services.llm import get_llm_provider
from app.services.retrieval_service import (
    CitationResult,
    resolve_concept_evidence,
    resolve_freeform_evidence,
    resolve_resource_evidence,
)

settings = get_settings()


def _citation_out(c: CitationResult) -> CitationOut:
    return CitationOut(
        documentId=c.document_id,
        documentFilename=c.document_filename,
        chunkId=c.chunk_id,
        pageNumber=c.page_number,
        excerpt=c.excerpt,
        order=c.order,
    )


def _insufficient(target: str) -> IntentResponse:
    return IntentResponse(
        intent=IntentType.QUIZ,
        status="INSUFFICIENT",
        provenance=None,
        sufficiencyScore=0.0,
        retrievalConfidence=0.0,
        canOfferExternalFallback=False,
        citations=[],
        result=QuizResult(quizId="", target=target, status="AWAITING_ANSWERS", questions=[]),
    )


class QuizIntent(IntentHandler):
    intent_type = IntentType.QUIZ

    def handle(self, db: Session, workspace: Workspace, request: IntentRequest) -> IntentResponse:
        if request.quizId:
            return self._grade(db, workspace, request)
        return self._generate(db, workspace, request)

    def _generate(self, db: Session, workspace: Workspace, request: IntentRequest) -> IntentResponse:
        count = min(
            request.questionCount or settings.QUIZ_QUESTION_COUNT_DEFAULT, settings.QUIZ_MAX_QUESTIONS
        )

        if request.resourceId:
            resource = db.get(Resource, request.resourceId)
            if resource is None or resource.workspace_id != workspace.id:
                raise AppError(status.HTTP_404_NOT_FOUND, "RESOURCE_NOT_FOUND", "Resource not found.")
            if resource.status != ResourceStatus.READY:
                raise AppError(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "RESOURCE_NOT_READY",
                    "This resource has not finished processing yet.",
                )
            label = resource.filename or "this document"
            evidence, citations = resolve_resource_evidence(
                db, request.resourceId, max_chunks=settings.QUIZ_MAX_EVIDENCE_CHUNKS
            )
            return self._build_quiz(
                db, workspace, label, evidence, citations, count, request.resourceId, None, 1.0
            )

        if request.conceptId:
            concept = db.get(Concept, request.conceptId)
            if concept is None or concept.workspace_id != workspace.id:
                raise AppError(status.HTTP_404_NOT_FOUND, "CONCEPT_NOT_FOUND", "Concept not found.")
            evidence, citations = resolve_concept_evidence(
                db, request.conceptId, max_chunks=settings.QUIZ_MAX_EVIDENCE_CHUNKS
            )
            return self._build_quiz(
                db, workspace, concept.name, evidence, citations, count, None, request.conceptId, 1.0
            )

        question = request.question or ""
        evidence, citations, verdict = resolve_freeform_evidence(
            db, workspace.id, question, top_k=settings.QUIZ_MAX_EVIDENCE_CHUNKS
        )
        if not verdict.is_sufficient:
            return IntentResponse(
                intent=IntentType.QUIZ,
                status="INSUFFICIENT",
                provenance=None,
                sufficiencyScore=verdict.score,
                retrievalConfidence=verdict.score,
                canOfferExternalFallback=True,
                citations=[],
                result=QuizResult(quizId="", target=question, status="AWAITING_ANSWERS", questions=[]),
            )
        return self._build_quiz(
            db, workspace, question, evidence, citations, count, None, None, verdict.score
        )

    def _build_quiz(
        self,
        db: Session,
        workspace: Workspace,
        label: str,
        evidence,
        citations: list[CitationResult],
        count: int,
        resource_id: str | None,
        concept_id: str | None,
        sufficiency_score: float,
    ) -> IntentResponse:
        if not evidence:
            return _insufficient(label)

        drafts = get_llm_provider().generate_quiz(label, evidence, count)
        if not drafts:
            return _insufficient(label)

        citations_out = [_citation_out(c) for c in citations]
        citation_dicts = [c.model_dump() for c in citations_out]

        stored_questions = []
        public_questions = []
        for i, d in enumerate(drafts, start=1):
            stored_questions.append(
                {
                    "questionNumber": i,
                    "prompt": d.prompt,
                    "choices": d.choices,
                    "correctChoice": d.correct_choice,
                    "citationOrder": d.citation_order,
                }
            )
            public_questions.append(QuizQuestionOut(questionNumber=i, prompt=d.prompt, choices=d.choices))

        attempt = QuizAttempt(
            workspace_id=workspace.id,
            resource_id=resource_id,
            concept_id=concept_id,
            target_label=label,
            status=QuizAttemptStatus.GENERATED,
            question_count=len(stored_questions),
            questions_payload=json.dumps(
                {
                    "questions": stored_questions,
                    "citations": citation_dicts,
                    "sufficiencyScore": sufficiency_score,
                }
            ),
        )
        db.add(attempt)
        db.flush()

        return IntentResponse(
            intent=IntentType.QUIZ,
            status="OK",
            provenance="LOCAL",
            sufficiencyScore=sufficiency_score,
            retrievalConfidence=sufficiency_score,
            canOfferExternalFallback=False,
            citations=citations_out,
            result=QuizResult(
                quizId=attempt.id, target=label, status="AWAITING_ANSWERS", questions=public_questions
            ),
        )

    def _grade(self, db: Session, workspace: Workspace, request: IntentRequest) -> IntentResponse:
        attempt = db.get(QuizAttempt, request.quizId)
        if attempt is None or attempt.workspace_id != workspace.id:
            raise AppError(status.HTTP_404_NOT_FOUND, "QUIZ_NOT_FOUND", "Quiz attempt not found.")
        if attempt.status == QuizAttemptStatus.GRADED:
            raise AppError(
                status.HTTP_409_CONFLICT, "QUIZ_ALREADY_GRADED", "This quiz has already been graded."
            )

        payload = json.loads(attempt.questions_payload)
        questions_by_number = {q["questionNumber"]: q for q in payload["questions"]}
        citations_out = [CitationOut(**c) for c in payload["citations"]]
        sufficiency_score = payload.get("sufficiencyScore", 1.0)
        answers_by_number = {a.questionNumber: a.selectedChoice for a in (request.quizAnswers or [])}

        citations_by_order = {c.order: c for c in citations_out}
        graded_questions: list[QuizGradedQuestionOut] = []
        correct_count = 0
        for number, q in sorted(questions_by_number.items()):
            selected = answers_by_number.get(number, -1)
            is_correct = selected == q["correctChoice"]
            if is_correct:
                correct_count += 1
            fallback_citation = CitationOut(
                documentId="", documentFilename="unknown", chunkId="", pageNumber=0, excerpt="", order=0
            )
            citation = citations_by_order.get(q["citationOrder"], fallback_citation)
            graded_questions.append(
                QuizGradedQuestionOut(
                    questionNumber=number,
                    prompt=q["prompt"],
                    choices=q["choices"],
                    selectedChoice=selected,
                    correctChoice=q["correctChoice"],
                    isCorrect=is_correct,
                    citation=citation,
                )
            )

        score = correct_count / len(graded_questions) if graded_questions else 0.0
        attempt.status = QuizAttemptStatus.GRADED
        attempt.correct_count = correct_count
        attempt.score = score
        attempt.graded_at = datetime.now(timezone.utc)
        db.add(attempt)
        db.flush()

        return IntentResponse(
            intent=IntentType.QUIZ,
            status="OK",
            provenance="LOCAL",
            sufficiencyScore=sufficiency_score,
            retrievalConfidence=sufficiency_score,
            canOfferExternalFallback=False,
            citations=citations_out,
            result=QuizResult(
                quizId=attempt.id,
                target=attempt.target_label,
                status="GRADED",
                gradedQuestions=graded_questions,
                score=score,
            ),
        )
