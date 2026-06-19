"""Chat streaming endpoint."""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..auth.services import get_current_user
from ..core.limiter import limiter
from . import services
from .models import ChatRequest

router = APIRouter(tags=["chat"])


@router.post("/chat")
@limiter.limit("30/minute")
async def chat(
    request: Request,  # required by slowapi
    request_body: ChatRequest,
    _: str = Depends(get_current_user),
):
    if not request_body.messages:
        raise HTTPException(status_code=400, detail="No messages provided.")

    return StreamingResponse(
        services.stream_response(request_body.messages, request_body.project_filter),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
