"""Authentication endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from . import services
from .models import LoginRequest, MeResponse, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest) -> TokenResponse:
    if not services.verify_credentials(body.username, body.password):
        raise HTTPException(status_code=401, detail="Invalid credentials.")
    return TokenResponse(access_token=services.create_access_token(body.username))


@router.get("/me", response_model=MeResponse)
def me(username: str = Depends(services.get_current_user)) -> MeResponse:
    """Validate the current token and return the authenticated username."""
    return MeResponse(username=username)
