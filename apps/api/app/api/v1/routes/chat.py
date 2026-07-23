from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import AppError, get_current_user, get_current_workspace
from app.models.answer import Answer
from app.models.citation import Citation
from app.models.conversation import Conversation, Message
from app.models.resource import Resource, ResourceStatus
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.chat import (
    AnswerOut,
    CitationOut,
    ConversationDetailOut,
    ConversationOut,
    CreateMessageRequest,
    MessageOut,
    SendMessageResponse,
)
from app.schemas.intents import (
    FlashcardsResult,
    IntentRequest,
    IntentResponse,
    IntentType,
    QuizResult,
    RevisionResult,
    SearchResult,
    StudyPlanResult,
    VivaResult,
)
from app.services.intents.registry import get_intent_handler
from app.services.retrieval_service import answer_question

router = APIRouter(prefix="/conversations", tags=["chat"])


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
def create_conversation(
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation = Conversation(workspace_id=workspace.id, user_id=user.id, title="New conversation")
    db.add(conversation)
    db.commit()
    return ConversationOut(id=conversation.id, title=conversation.title)


@router.get("/{conversation_id}", response_model=ConversationDetailOut)
def get_conversation(
    conversation_id: str,
    workspace: Workspace = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    conversation = db.get(Conversation, conversation_id)
    if not conversation or conversation.workspace_id != workspace.id:
        raise AppError(status.HTTP_404_NOT_FOUND, "CONVERSATION_NOT_FOUND", "Conversation not found.")

    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc())
        .all()
    )
    return ConversationDetailOut(
        conversation=ConversationOut(id=conversation.id, title=conversation.title),
        messages=[MessageOut(id=m.id, role=m.role, content=m.content) for m in messages],
    )


@router.post(
    "/{conversation_id}/messages", response_model=SendMessageResponse, status_code=status.HTTP_201_CREATED
)
def send_message(
    conversation_id: str,
    payload: CreateMessageRequest,
    workspace: Workspace = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    conversation = db.get(Conversation, conversation_id)
    if not conversation or conversation.workspace_id != workspace.id:
        raise AppError(status.HTTP_404_NOT_FOUND, "CONVERSATION_NOT_FOUND", "Conversation not found.")

    ready_doc_count = (
        db.query(Resource)
        .filter(Resource.workspace_id == workspace.id, Resource.status == ResourceStatus.READY)
        .count()
    )
    if ready_doc_count == 0:
        raise AppError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "NO_READY_DOCUMENTS",
            "Upload and wait for at least one document to finish processing before asking a question.",
        )

    user_message = Message(conversation_id=conversation.id, role="user", content=payload.content)
    db.add(user_message)
    db.commit()

    result = answer_question(
        db,
        workspace_id=workspace.id,
        question=payload.content,
        use_external_fallback=payload.useExternalFallback,
        allow_external_fallback=workspace.allow_external_fallback,
    )

    assistant_message = Message(conversation_id=conversation.id, role="assistant", content=result.content)
    db.add(assistant_message)
    db.flush()

    answer = Answer(
        message_id=assistant_message.id,
        model_name=result.model_name,
        retrieval_latency_ms=result.retrieval_latency_ms,
        generation_latency_ms=result.generation_latency_ms,
        status=result.status,
        provenance=result.provenance,
        sufficiency_score=result.sufficiency_score,
        retrieval_confidence=result.retrieval_confidence,
        sufficiency_reason=result.sufficiency_reason,
    )
    db.add(answer)
    db.flush()

    citation_rows = []
    for c in result.citations:
        row = Citation(
            answer_id=answer.id,
            resource_id=c.document_id,
            chunk_id=c.chunk_id,
            page_number=c.page_number,
            excerpt=c.excerpt,
            citation_order=c.order,
        )
        db.add(row)
        citation_rows.append((row, c.document_filename))

    if conversation.title == "New conversation":
        conversation.title = payload.content[:80]

    db.commit()

    return SendMessageResponse(
        userMessage=MessageOut(id=user_message.id, role="user", content=user_message.content),
        answer=AnswerOut(
            id=answer.id,
            status=answer.status,
            provenance=answer.provenance,
            sufficiencyScore=answer.sufficiency_score,
            retrievalConfidence=answer.retrieval_confidence,
            canOfferExternalFallback=result.can_offer_external_fallback,
            content=result.content,
            sufficiencyReason=answer.sufficiency_reason,
            citations=[
                CitationOut(
                    documentId=row.resource_id,
                    documentFilename=filename,
                    chunkId=row.chunk_id,
                    pageNumber=row.page_number,
                    excerpt=row.excerpt,
                    order=row.citation_order,
                )
                for row, filename in citation_rows
            ],
        ),
    )


def _describe_intent_request(payload: IntentRequest) -> str:
    """A plain-text description of an intent request, for the
    conversation transcript's user-turn Message row -- never used for
    retrieval itself, just for the human-readable history."""
    if payload.intent == IntentType.COMPARE and payload.targets:
        return "Compare: " + " vs ".join(t.label for t in payload.targets)
    if payload.intent == IntentType.SUMMARIZE:
        if payload.resourceId:
            return f"Summarize resource {payload.resourceId}"
        if payload.conceptId:
            return f"Summarize concept {payload.conceptId}"
    # -- Milestone 10 (Study Workflows): additive branches only, no
    # existing branch above this changed. --
    if payload.intent == IntentType.QUIZ:
        if payload.quizId:
            return "Quiz: submitting answers"
        if payload.resourceId:
            return f"Quiz me on resource {payload.resourceId}"
        if payload.conceptId:
            return f"Quiz me on concept {payload.conceptId}"
    if payload.intent == IntentType.FLASHCARDS:
        if payload.resourceId:
            return f"Flashcards for resource {payload.resourceId}"
        if payload.conceptId:
            return f"Flashcards for concept {payload.conceptId}"
    if payload.intent == IntentType.VIVA:
        if payload.sessionId:
            return "Viva: submitting answer"
        if payload.resourceId:
            return f"Viva mode on resource {payload.resourceId}"
        if payload.conceptId:
            return f"Viva mode on concept {payload.conceptId}"
    if payload.intent == IntentType.REVISION:
        return "Revision mode"
    if payload.intent == IntentType.STUDY_PLAN and payload.targets:
        return "Study plan: " + ", ".join(t.label for t in payload.targets)
    return payload.question or f"{payload.intent} request"


def _extract_assistant_content(intent_response: IntentResponse) -> str:
    """A plain-text rendering of whatever `result` payload this intent
    produced, for the conversation transcript's assistant-turn Message
    row. Every result type except SearchResult carries a single
    `content` string; Search's shape (a ranked hit list plus an optional
    synthesis) needs its own rendering."""
    result = intent_response.result
    if isinstance(result, SearchResult):
        if result.assistedSynthesis:
            return result.assistedSynthesis
        return f"Found {len(result.hits)} matching result(s)."
    # -- Milestone 10 (Study Workflows): additive branches only, no
    # existing branch above this changed. --
    if isinstance(result, QuizResult):
        if result.status == "GRADED":
            return f"Quiz: {result.score:.0%} correct" if result.score is not None else "Quiz graded."
        return f"Quiz: {len(result.questions or [])} question(s) generated."
    if isinstance(result, FlashcardsResult):
        return f"Flashcards: {len(result.cards)} card(s) generated."
    if isinstance(result, VivaResult):
        if result.isComplete:
            return "Viva: session complete."
        return f"Viva: {result.nextQuestion}" if result.nextQuestion else "Viva: next question."
    if isinstance(result, RevisionResult):
        return f"Revision: {len(result.items)} item(s) flagged."
    if isinstance(result, StudyPlanResult):
        return f"Study plan: {len(result.days)} day(s) scheduled."
    return getattr(result, "content", "")


@router.post("/{conversation_id}/intents", response_model=IntentResponse, status_code=status.HTTP_201_CREATED)
def create_intent(
    conversation_id: str,
    payload: IntentRequest,
    workspace: Workspace = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    """
    Milestone 9: the one real dispatch entry point for every intent
    (EXPLAIN/SEARCH/SUMMARIZE/COMPARE, and whatever Milestone 10 adds) --
    see app/services/intents/registry.py. `POST /messages` above is kept,
    unchanged, as a separate, full-fidelity path specifically for EXPLAIN
    (it persists retrieval latency/model-name detail this generic route's
    IntentResponse envelope deliberately doesn't carry -- see
    docs/milestones/MILESTONE_9.md's implementation notes on why this is
    a refinement of, not a deviation from, the approved "thin wrapper"
    design: both paths call the identical retrieval_service.answer_question(),
    so there is still exactly one implementation of the retrieval logic,
    just two persistence granularities for two different call sites).
    """
    conversation = db.get(Conversation, conversation_id)
    if not conversation or conversation.workspace_id != workspace.id:
        raise AppError(status.HTTP_404_NOT_FOUND, "CONVERSATION_NOT_FOUND", "Conversation not found.")

    ready_doc_count = (
        db.query(Resource)
        .filter(Resource.workspace_id == workspace.id, Resource.status == ResourceStatus.READY)
        .count()
    )
    if ready_doc_count == 0:
        raise AppError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "NO_READY_DOCUMENTS",
            "Upload and wait for at least one document to finish processing before using this.",
        )

    user_message = Message(
        conversation_id=conversation.id, role="user", content=_describe_intent_request(payload)
    )
    db.add(user_message)
    db.commit()

    try:
        handler = get_intent_handler(payload.intent)
    except ValueError as exc:
        raise AppError(status.HTTP_400_BAD_REQUEST, "UNKNOWN_INTENT", str(exc)) from exc

    intent_response = handler.handle(db, workspace, payload)

    assistant_message = Message(
        conversation_id=conversation.id, role="assistant", content=_extract_assistant_content(intent_response)
    )
    db.add(assistant_message)
    db.flush()

    answer = Answer(
        message_id=assistant_message.id,
        status=intent_response.status,
        provenance=intent_response.provenance,
        sufficiency_score=intent_response.sufficiencyScore,
        retrieval_confidence=intent_response.retrievalConfidence,
        intent=intent_response.intent,
        intent_payload=intent_response.result.model_dump_json(),
    )
    db.add(answer)
    db.flush()

    for c in intent_response.citations:
        db.add(
            Citation(
                answer_id=answer.id,
                resource_id=c.documentId,
                chunk_id=c.chunkId,
                page_number=c.pageNumber,
                excerpt=c.excerpt,
                citation_order=c.order,
                target_label=c.targetLabel,
            )
        )

    if conversation.title == "New conversation":
        conversation.title = _describe_intent_request(payload)[:80]

    db.commit()
    return intent_response


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: str,
    workspace: Workspace = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    conversation = db.get(Conversation, conversation_id)
    if not conversation or conversation.workspace_id != workspace.id:
        raise AppError(status.HTTP_404_NOT_FOUND, "CONVERSATION_NOT_FOUND", "Conversation not found.")
    db.delete(conversation)
    db.commit()
    return None
