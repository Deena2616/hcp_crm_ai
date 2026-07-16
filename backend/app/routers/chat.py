from typing import Optional
import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.schemas import ChatRequest, ChatResponse
from app.agent.graph import run_agent

router = APIRouter(prefix="/api/chat", tags=["Chat Agent"])


class ChatContext(BaseModel):
    """
    Optional context so a message from a scoped prompt area (e.g. the "Edit this entry"
    input tied to a specific row, or a "Schedule follow-up" input tied to a specific HCP)
    doesn't rely purely on the LLM guessing which interaction/HCP is meant.
    """
    interaction_id: Optional[str] = None
    hcp_name: Optional[str] = None


class ChatRequestWithContext(ChatRequest):
    context: Optional[ChatContext] = None


def _build_response(final_state: dict) -> ChatResponse:
    tool_calls = [final_state["tool_name"]] if final_state.get("tool_name") else []
    data = None
    if final_state.get("tool_result"):
        try:
            data = json.loads(final_state["tool_result"])
        except Exception:
            data = {"raw": final_state["tool_result"]}

    return ChatResponse(
        reply=final_state.get("reply", ""),
        intent=final_state.get("intent"),
        tool_calls=tool_calls,
        data=data,
        # When the agent produced a log_interaction draft, these get bound into the
        # structured form on the frontend instead of a DB row having already been created.
        # For edit_interaction_tool / schedule_followup_tool / search_interactions_tool,
        # `data` above already reflects the immediately-committed (or read) result.
        action=final_state.get("action"),
        draft=final_state.get("draft"),
    )


@router.post("", response_model=ChatResponse)
def chat(payload: ChatRequestWithContext, db: Session = Depends(get_db)):
    """
    Generic chat endpoint - used by the main AI Assistant panel. Handles new-interaction
    drafting as well as immediate edit / follow-up / search / profile-lookup requests, all
    routed by intent classification.
    """
    context = payload.context.dict() if payload.context else None
    final_state = run_agent(payload.message, db, hcp_id=payload.hcp_id, context=context)
    return _build_response(final_state)


@router.post("/edit", response_model=ChatResponse)
def chat_edit(payload: ChatRequestWithContext, db: Session = Depends(get_db)):
    """
    Dedicated endpoint for the "Edit this entry" prompt area in InteractionHistory. Forces
    routing toward edit_interaction_tool semantics by pinning interaction_id in context, so
    a short instruction like "change sentiment to negative" is unambiguous about which
    interaction it targets - it commits immediately, same as chatting the same instruction
    into the main assistant panel.
    """
    context = payload.context.dict() if payload.context else {}
    final_state = run_agent(payload.message, db, hcp_id=payload.hcp_id, context=context)
    return _build_response(final_state)


@router.post("/followup", response_model=ChatResponse)
def chat_followup(payload: ChatRequestWithContext, db: Session = Depends(get_db)):
    """
    Dedicated endpoint for a "Schedule follow-up" prompt area (e.g. on an HCP profile view
    or next to the structured form), scoped to a specific HCP via context.hcp_name. Commits
    immediately via schedule_followup_tool, same as asking for it from the main chat panel.
    """
    context = payload.context.dict() if payload.context else {}
    final_state = run_agent(payload.message, db, hcp_id=payload.hcp_id, context=context)
    return _build_response(final_state)