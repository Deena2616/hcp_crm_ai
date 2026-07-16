from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


# ---------- HCP ----------
class HCPBase(BaseModel):
    name: str
    specialty: Optional[str] = None
    hospital: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    preferred_channel: Optional[str] = None
    notes: Optional[str] = None


class HCPCreate(HCPBase):
    pass


class HCPOut(HCPBase):
    id: str
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Interaction ----------
class InteractionCreate(BaseModel):
    hcp_id: Optional[str] = None
    hcp_name: Optional[str] = None
    interaction_type: Optional[str] = "meeting"
    occurred_at: Optional[datetime] = None
    attendees: Optional[List[str]] = None
    notes: Optional[str] = None
    materials_shared: Optional[List[str]] = None
    samples_provided: Optional[List[str]] = None
    sentiment: Optional[str] = "neutral"
    outcomes: Optional[str] = None
    follow_up_actions: Optional[str] = None
    source: Optional[str] = "form"

    # Legacy/chat path: free text the LLM should summarize + extract from
    raw_text: Optional[str] = None


class InteractionUpdate(BaseModel):
    notes: Optional[str] = None
    interaction_type: Optional[str] = None
    attendees: Optional[List[str]] = None
    materials_shared: Optional[List[str]] = None
    samples_provided: Optional[List[str]] = None
    sentiment: Optional[str] = None
    sentiment_score: Optional[float] = None
    outcomes: Optional[str] = None
    follow_up_actions: Optional[str] = None
    edit_reason: Optional[str] = None


class InteractionOut(BaseModel):
    id: str
    hcp_id: str
    interaction_type: str
    occurred_at: datetime
    attendees: Optional[str]
    notes: Optional[str]
    summary: Optional[str]
    materials_shared: Optional[str]
    samples_provided: Optional[str]
    sentiment: str
    sentiment_score: Optional[float]
    outcomes: Optional[str]
    follow_up_actions: Optional[str]
    source: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# ---------- Interaction Search ----------
class InteractionSearchParams(BaseModel):
    sentiment: Optional[str] = None
    hcp_name: Optional[str] = None
    keyword: Optional[str] = None
    interaction_type: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    limit: int = 10

# ---------- FollowUp ----------
class FollowUpCreate(BaseModel):
    hcp_id: Optional[str] = None
    hcp_name: Optional[str] = None
    interaction_id: Optional[str] = None
    due_date: datetime
    reason: Optional[str] = None


class FollowUpOut(BaseModel):
    id: str
    hcp_id: str
    interaction_id: Optional[str]
    due_date: datetime
    reason: Optional[str]
    completed: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- AdverseEvent ----------
class AdverseEventCreate(BaseModel):
    hcp_id: Optional[str] = None
    hcp_name: Optional[str] = None
    interaction_id: Optional[str] = None
    drug_name: Optional[str] = None
    description: str
    severity: Optional[str] = "unknown"


class AdverseEventOut(BaseModel):
    id: str
    hcp_id: str
    interaction_id: Optional[str]
    drug_name: Optional[str]
    description: str
    severity: str
    reported_at: datetime
    status: str

    class Config:
        from_attributes = True


# ---------- Chat / Agent ----------
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = "default"
    hcp_id: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    intent: Optional[str] = None
    tool_calls: Optional[List[str]] = None
    data: Optional[dict] = None
    # When the agent produced a form draft (currently: log_interaction requests), the
    # frontend uses these to bind the extracted fields into the structured form instead
    # of treating the chat turn as a completed database write.
    action: Optional[str] = None      # e.g. "draft_interaction"
    draft: Optional[dict] = None      # extracted fields to bind into the form


# ---------- AI form-assist features (not LangGraph tools; used only by the structured form) ----------
class SuggestFollowupsRequest(BaseModel):
    hcp_name: Optional[str] = None
    notes: Optional[str] = None
    outcomes: Optional[str] = None


class SuggestFollowupsResponse(BaseModel):
    suggestions: List[str]


class VoiceNoteRequest(BaseModel):
    transcript: str


class VoiceNoteResponse(BaseModel):
    notes: str
    outcomes: str