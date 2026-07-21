from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import AppError, get_current_user, get_current_workspace
from app.models.answer import Answer
from app.models.citation import Citation
from app.models.conversation import Conversation, Message
from app.models.resource import Resource
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
        db.query(Resource).filter(Resource.workspace_id == workspace.id, Resource.status == "READY").count()
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

    result = answer_question(db, workspace_id=workspace.id, question=payload.content)

    assistant_message = Message(conversation_id=conversation.id, role="assistant", content=result.content)
    db.add(assistant_message)
    db.flush()

    answer = Answer(
        message_id=assistant_message.id,
        model_name=result.model_name,
        retrieval_latency_ms=result.retrieval_latency_ms,
        generation_latency_ms=result.generation_latency_ms,
        status=result.status,
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
            content=result.content,
            citations=[
                CitationOut(
                    documentId=row.resource_id,
                    documentFilename=filename,
                    pageNumber=row.page_number,
                    excerpt=row.excerpt,
                    order=row.citation_order,
                )
                for row, filename in citation_rows
            ],
        ),
    )


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
