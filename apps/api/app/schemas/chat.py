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
    # Milestone 9: exposed so a citation can be persisted end-to-end from
    # a generic IntentResponse (see app/schemas/intents.py) without a
    # second, richer citation type -- previously only used internally via
    # retrieval_service.CitationResult.
    chunkId: str
    pageNumber: int
    excerpt: str
    order: int
    # Milestone 9: which Compare target this citation supports (e.g.
    # "Resource A", a concept's name). None for Explain/Search/resource-
    # or concept-targeted Summarize, where a citation belongs to the
    # answer as a whole rather than to one side of a comparison.
    targetLabel: str | None = None


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
    # Milestone 11 (Confidence & Correction UX): one of the five fixed
    # sufficiency reason codes from services/sufficiency.py
    # (no_candidates | strong_single_hit | insufficient_supporting_hits |
    # below_min_score | top_score). Exposes Answer.sufficiency_reason,
    # already computed and persisted since Milestone 8 -- no new
    # computation. Optional/None for rows predating this field.
    sufficiencyReason: str | None = None


class SendMessageResponse(BaseModel):
    userMessage: MessageOut
    answer: AnswerOut


class ConversationOut(BaseModel):
    id: str
    title: str


class ConversationDetailOut(BaseModel):
    conversation: ConversationOut
    messages: list[MessageOut]
