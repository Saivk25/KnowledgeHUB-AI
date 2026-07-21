from pydantic import BaseModel, Field


class CreateMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


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
    status: str
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
