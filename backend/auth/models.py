from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class SignupRequest(BaseModel):
    email: str = Field(min_length=3, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, max_length=200)
    company_name: str = Field(min_length=2, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str = "admin"


class MeResponse(BaseModel):
    username: str
    role: str = "admin"
    company_name: str | None = None
