"""Chat streaming endpoint."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from . import services
from .models import ChatRequest

router = APIRouter(tags=["chat"])


@router.post("/chat")
async def chat(request_body: ChatRequest):
    if not request_body.messages:
        raise HTTPException(status_code=400, detail="No messages provided.")

    return StreamingResponse(
        services.stream_response(request_body.messages, request_body.document_filter),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
