"""
Intent handler plugin registry (Milestone 9).

Mirrors the Extractor/Classifier/ConceptLinker plugin-registry pattern
already established in this codebase (app/services/extraction.py,
classification.py, concept_linking.py) applied one layer later in the
pipeline, per the approved design's amendment
(docs/milestones/MILESTONE_9.md Section 3.3): one class per intent, each
responsible for its own orchestration -- which evidence-resolution
helpers it calls, which LLMProvider method it invokes, how it shapes its
own `result` payload -- while all four share the same underlying
retrieval primitives (app/services/retrieval_service.py's resolve_*
helpers, app/services/sufficiency.py, app/services/llm.get_llm_provider).
Registered by registry.py -- never a single function branching on intent
type. Adding a fifth intent in Milestone 10 means adding one new file and
one registry entry, never touching the other four or a shared branching
function.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from app.models.workspace import Workspace
from app.schemas.intents import IntentRequest, IntentResponse


class IntentHandler(ABC):
    intent_type: str

    @abstractmethod
    def handle(self, db: Session, workspace: Workspace, request: IntentRequest) -> IntentResponse: ...
