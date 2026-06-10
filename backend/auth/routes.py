"""Authentication endpoints."""

from fastapi import APIRouter, HTTPException

from . import services
from .models import LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest) -> TokenResponse:
    if not services.verify_credentials(body.username, body.password):
        raise HTTPException(status_code=401, detail="Invalid credentials.")
    return TokenResponse(access_token=services.create_access_token(body.username))
