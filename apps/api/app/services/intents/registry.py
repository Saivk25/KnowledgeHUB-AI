"""
Intent handler registry (Milestones 9-10). See base.py's docstring for
why this is a registry of one handler instance per intent type, not a
single function branching on `intent`. Milestone 10 added five more
intents (Quiz me, Flashcards, Viva mode, Revision mode, Study planner) by
adding five new files (each implementing IntentHandler) and five new
lines here -- no other handler, and no branching logic, was touched.
"""

from __future__ import annotations

from app.schemas.intents import IntentType
from app.services.intents.base import IntentHandler
from app.services.intents.compare import CompareIntent
from app.services.intents.explain import ExplainIntent
from app.services.intents.flashcards import FlashcardsIntent
from app.services.intents.quiz import QuizIntent
from app.services.intents.revision import RevisionIntent
from app.services.intents.search import SearchIntent
from app.services.intents.study_planner import StudyPlannerIntent
from app.services.intents.summarize import SummarizeIntent
from app.services.intents.viva import VivaIntent

_HANDLERS: dict[str, IntentHandler] = {
    IntentType.EXPLAIN: ExplainIntent(),
    IntentType.SEARCH: SearchIntent(),
    IntentType.SUMMARIZE: SummarizeIntent(),
    IntentType.COMPARE: CompareIntent(),
    IntentType.QUIZ: QuizIntent(),
    IntentType.FLASHCARDS: FlashcardsIntent(),
    IntentType.VIVA: VivaIntent(),
    IntentType.REVISION: RevisionIntent(),
    IntentType.STUDY_PLAN: StudyPlannerIntent(),
}


def get_intent_handler(intent_type: str) -> IntentHandler:
    handler = _HANDLERS.get(intent_type)
    if handler is None:
        raise ValueError(f"Unknown intent type: {intent_type}")
    return handler
