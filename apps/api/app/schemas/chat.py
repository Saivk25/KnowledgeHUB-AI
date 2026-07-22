from pydantic import BaseModel, Field


class CreateMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    # Milestone 8: explicit, per-request consent to answer from general
    # knowledge if local evidence turns out to be insufficient (or, if the
    # question IS answerable locally, to append a clearly-delimited
    # general-knowledge supplement -- see retrieval_service.answer_question's
    # HYBRID branch). Defaults to False: an external model is never called
    # without consent (approved design, decision 4).
    useExternalFallback: bool = False


class CitationOut(BaseModel):
    documentId: str
    documentFilename: str
    pageNumber: int
    excerpt: str
    order: int


class MessageOut(BaseModel):
    id: str
    role: str
    content: str


class AnswerOut(BaseModel):
    id: str
    status: str  # OK | INSUFFICIENT | ERROR
    # Milestone 8: structurally required alongside every answer (Architecture
    # Section 9 item 4) -- provenance is None only when status is
    # INSUFFICIENT and no external fallback was used.
    provenance: str | None  # LOCAL | HYBRID | EXTERNAL | None
    sufficiencyScore: float
    retrievalConfidence: float
    canOfferExternalFallback: bool
    content: str
    citations: list[CitationOut]


class SendMessageResponse(BaseModel):
    userMessage: MessageOut
    answer: AnswerOut


class ConversationOut(BaseModel):
    id: str
    title: str


class ConversationDetailOut(BaseModel):
    conversation: ConversationOut
    messages: list[MessageOut]
