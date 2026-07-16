from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.schemas import ChatRequest, ChatResponse
from app.agent.graph import run_agent

router = APIRouter(prefix="/api/chat", tags=["Chat Agent"])


@router.post("", response_model=ChatResponse)
def chat(payload: ChatRequest, db: Session = Depends(get_db)):
    final_state = run_agent(payload.message, db, hcp_id=payload.hcp_id)

    tool_calls = [final_state["tool_name"]] if final_state.get("tool_name") else []
    data = None
    if final_state.get("tool_result"):
        import json
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
        action=final_state.get("action"),
        draft=final_state.get("draft"),
    )