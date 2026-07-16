"""
AI-assist endpoints used only by the structured form (not part of the 5 mandatory
LangGraph tools, which live in app/agent/tools.py and are only reachable via the chat
agent). These give the "Log HCP Interaction" form its two AI affordances:

  - "Summarize from Voice Note": the rep pastes a transcript (no live audio capture in
    this build) and the LLM turns it into clean Topics Discussed / Outcomes text.
  - "AI Suggested Follow-ups": given what's been typed so far, the LLM proposes 2-4
    concrete next steps the rep can add to Follow-up Actions with one click.
"""
from fastapi import APIRouter
from app.agent.llm import call_llm_json
from app.schemas.schemas import (
    SuggestFollowupsRequest, SuggestFollowupsResponse,
    VoiceNoteRequest, VoiceNoteResponse,
)

router = APIRouter(prefix="/api/assist", tags=["AI Form Assist"])


@router.post("/suggest-followups", response_model=SuggestFollowupsResponse)
def suggest_followups(payload: SuggestFollowupsRequest):
    context = f"HCP: {payload.hcp_name or 'unknown'}\nTopics discussed: {payload.notes or ''}\nOutcomes: {payload.outcomes or ''}"
    result = call_llm_json(
        system_prompt=(
            "You are a pharma CRM assistant helping a field rep after they log an HCP "
            "interaction. Given the discussion topics and outcomes, suggest 2-4 short, "
            "concrete follow-up actions (e.g. scheduling, sending materials, adding to a "
            "list). Return STRICT JSON: {\"suggestions\": [\"...\", \"...\"]}. Each "
            "suggestion under 12 words."
        ),
        user_prompt=context,
    )
    suggestions = result.get("suggestions", [])
    if not isinstance(suggestions, list):
        suggestions = []
    return SuggestFollowupsResponse(suggestions=suggestions[:4])


@router.post("/summarize-voice-note", response_model=VoiceNoteResponse)
def summarize_voice_note(payload: VoiceNoteRequest):
    result = call_llm_json(
        system_prompt=(
            "You are a pharma CRM assistant. Given a raw transcript of a field rep's voice "
            "note about an HCP visit, produce STRICT JSON with two keys: "
            "'notes' (bullet-style key discussion points as a single string) and "
            "'outcomes' (key outcomes/agreements as a single string)."
        ),
        user_prompt=payload.transcript,
    )
    return VoiceNoteResponse(
        notes=result.get("notes", payload.transcript[:300]),
        outcomes=result.get("outcomes", ""),
    )
