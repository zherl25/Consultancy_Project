"""Authentication endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request

from ..core.limiter import limiter
from . import services, store
from .models import LoginRequest, MeResponse, SignupRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
@limiter.limit("20/minute")
async def login(request: Request, body: LoginRequest) -> TokenResponse:  # noqa: ARG001
    user = await services.authenticate(body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials.")
    return TokenResponse(access_token=services.create_access_token(user.id, user.role), role=user.role)


@router.post("/signup", response_model=TokenResponse, status_code=201)
@limiter.limit("5/minute")
async def signup(request: Request, body: SignupRequest) -> TokenResponse:  # noqa: ARG001
    user = await store.create_user(body.email, body.password, body.company_name)
    if not user:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    return TokenResponse(access_token=services.create_access_token(user["id"], services.CLIENT),
                         role=services.CLIENT)


@router.get("/me", response_model=MeResponse)
async def me(user: services.CurrentUser = Depends(services.get_current_user)) -> MeResponse:
    """Validate the current token and return who is signed in."""
    if user.role == services.ADMIN:
        return MeResponse(username=user.id, role=user.role)
    account = await store.get_by_id(user.id)
    if not account:
        raise HTTPException(status_code=401, detail="Account no longer exists.")
    return MeResponse(username=account["email"], role=user.role, company_name=account["company_name"])
