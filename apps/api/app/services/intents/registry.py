"""
Intent handler registry (Milestone 9). See base.py's docstring for why
this is a registry of one handler instance per intent type, not a single
function branching on `intent`. Adding a Milestone 10 intent means adding
one new file (implementing IntentHandler) and one line here.
"""

from __future__ import annotations

from app.schemas.intents import IntentType
from app.services.intents.base import IntentHandler
from app.services.intents.compare import CompareIntent
from app.services.intents.explain import ExplainIntent
from app.services.intents.search import SearchIntent
from app.services.intents.summarize import SummarizeIntent

_HANDLERS: dict[str, IntentHandler] = {
    IntentType.EXPLAIN: ExplainIntent(),
    IntentType.SEARCH: SearchIntent(),
    IntentType.SUMMARIZE: SummarizeIntent(),
    IntentType.COMPARE: CompareIntent(),
}


def get_intent_handler(intent_type: str) -> IntentHandler:
    handler = _HANDLERS.get(intent_type)
    if handler is None:
        raise ValueError(f"Unknown intent type: {intent_type}")
    return handler
