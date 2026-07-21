from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    displayName: str = Field(min_length=1, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    displayName: str


class WorkspaceOut(BaseModel):
    id: str
    name: str


class AuthResponse(BaseModel):
    user: UserOut
    workspace: WorkspaceOut
    accessToken: str
