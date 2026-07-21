from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str
    requestId: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
