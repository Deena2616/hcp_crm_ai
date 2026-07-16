"""
Five LangGraph tools for the HCP sales agent:

1. log_interaction_tool   - captures a new HCP interaction (uses LLM for summarization
                             + entity/topic/sentiment extraction from free text)
2. edit_interaction_tool  - modifies a previously logged interaction, keeping version history
3. fetch_hcp_profile_tool - retrieves an HCP's profile + recent interaction history
4. schedule_followup_tool - creates a follow-up reminder/task tied to an HCP
5. flag_adverse_event_tool- detects & files an adverse-event report from interaction text

Each tool is a plain Python function decorated with LangChain's @tool so it can be bound
to the LangGraph agent node and invoked by name with structured args.

NOTE on the draft flow: `extract_interaction_fields` below does the same LLM extraction as
log_interaction_tool but performs NO database write. It's used by the chat graph's
draft_log_interaction_node (see agent/graph.py) so a chat-described interaction gets bound
into the structured form for the rep to review/edit, rather than being committed straight
to the database. log_interaction_tool itself is kept (and still commits) so it remains
available as a genuine LangGraph tool for the classification step / tool listing and for
any future flow that wants an immediate, non-draft commit.
"""
import json
import re
from datetime import datetime, timedelta
from typing import Optional

from langchain_core.tools import tool
from sqlalchemy.orm import Session

from app.models.models import HCP, Interaction, FollowUp, AdverseEvent
from app.agent.llm import call_llm_json

# The tools need DB access but @tool functions are called by the graph with only
# LLM-provided args, so we inject the active session via this module-level handle,
# set once per request in agent/graph.py (and the relevant routers) before invoking.
_db_session: Optional[Session] = None


def set_db_session(db: Session):
    global _db_session
    _db_session = db


def _get_or_create_hcp(hcp_name: str, hcp_id: Optional[str] = None) -> HCP:
    db = _db_session
    if hcp_id:
        hcp = db.query(HCP).filter(HCP.id == hcp_id).first()
        if hcp:
            return hcp
    if hcp_name:
        hcp = db.query(HCP).filter(HCP.name.ilike(f"%{hcp_name}%")).first()
        if hcp:
            return hcp
        hcp = HCP(name=hcp_name)
        db.add(hcp)
        db.commit()
        db.refresh(hcp)
        return hcp
    raise ValueError("Either hcp_id or hcp_name must be provided")


_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def parse_relative_datetime(text: str, now: Optional[datetime] = None) -> dict:
    """
    Deterministically resolves common relative date/time phrases ("yesterday", "last
    Monday", "3 days ago", "at 3pm", "this morning") against `now`. Small/fast LLMs like
    gemma2-9b-it are unreliable at date arithmetic, so this handles the common cases in
    plain Python instead of asking the model to compute them - the LLM's own guess is only
    used as a fallback for phrasing this doesn't catch (see extract_interaction_fields).
    Returns {"occurred_date": "YYYY-MM-DD" | None, "occurred_time": "HH:MM" | None}.
    """
    now = now or datetime.utcnow()
    text_l = text.lower()
    result_date = None
    result_time = None

    # --- date ---
    if "yesterday" in text_l:
        result_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    elif "tomorrow" in text_l:
        result_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    elif "today" in text_l:
        result_date = now.strftime("%Y-%m-%d")

    m = re.search(r"(\d+)\s+days?\s+ago", text_l)
    if m:
        result_date = (now - timedelta(days=int(m.group(1)))).strftime("%Y-%m-%d")

    m = re.search(r"last\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)", text_l)
    if m:
        target = _WEEKDAYS.index(m.group(1))
        delta = (now.weekday() - target) % 7
        delta = delta if delta != 0 else 7  # "last Monday" always means a prior week's Monday
        result_date = (now - timedelta(days=delta)).strftime("%Y-%m-%d")
    elif not result_date:
        m = re.search(r"\bon\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", text_l)
        if m:
            target = _WEEKDAYS.index(m.group(1))
            delta = (now.weekday() - target) % 7
            result_date = (now - timedelta(days=delta)).strftime("%Y-%m-%d")

    # --- time ---
    m = re.search(r"\b(\d{1,2})(:(\d{2}))?\s*(am|pm)\b", text_l)
    if m:
        hour = int(m.group(1)) % 12
        minute = int(m.group(3)) if m.group(3) else 0
        if m.group(4) == "pm":
            hour += 12
        result_time = f"{hour:02d}:{minute:02d}"
    elif "this morning" in text_l or (result_date and "morning" in text_l):
        result_time = "09:00"
    elif "this afternoon" in text_l or (result_date and "afternoon" in text_l):
        result_time = "14:00"
    elif "this evening" in text_l or (result_date and "evening" in text_l):
        result_time = "18:00"

    return {"occurred_date": result_date, "occurred_time": result_time}


# ---------------------------------------------------------------------------
# Shared extraction logic (NO db write) - used by both log_interaction_tool
# and the chat draft flow in agent/graph.py
# ---------------------------------------------------------------------------
def extract_interaction_fields(raw_text: str, hcp_name: str = "", interaction_type: str = "meeting") -> dict:
    """
    Runs the LLM extraction only - does NOT touch the database. Returns a dict shaped to
    match the structured form's fields, so it can be bound directly into the form for the
    rep to review before they click "Log Interaction".
    """
    db = _db_session
    hcp_id = None
    resolved_name = hcp_name

    if hcp_name:
        existing = db.query(HCP).filter(HCP.name.ilike(f"%{hcp_name}%")).first()
        if existing:
            hcp_id = existing.id
            resolved_name = existing.name

    today_str = datetime.utcnow().strftime("%Y-%m-%d")

    extraction = call_llm_json(
        system_prompt=(
            "You are a pharmaceutical CRM assistant. Extract structured data from a field "
            "rep's account of an HCP interaction. Return STRICT JSON only, with keys: "
            "summary (1-2 sentence professional summary to use as Topics Discussed), "
            "outcomes (short string - key outcomes/agreements, empty string if none mentioned), "
            "sentiment (one of positive, neutral, negative), sentiment_score (float -1.0 to 1.0), "
            "samples_provided (list of sample product names mentioned as given to the HCP, "
            "empty list if none), materials_shared (list of materials/brochures mentioned as "
            "shared, empty list if none), follow_up_actions (short string describing any next "
            "steps mentioned, empty string if none), "
            f"occurred_date (the date the interaction happened, in YYYY-MM-DD format, computed "
            f"relative to today which is {today_str} - e.g. 'yesterday' or 'last Monday' should "
            "be resolved to an actual date; return null if no date is mentioned at all), "
            "occurred_time (24-hour HH:MM the interaction happened, ONLY if a time is explicitly "
            "or clearly implied in the text, e.g. 'at 3pm', 'this morning', 'around 9:30'; "
            "return null if no time is mentioned)."
        ),
        user_prompt=raw_text,
    )

    valid_types = ["meeting", "call", "video_call", "email", "conference"]
    sentiment = extraction.get("sentiment", "neutral")
    parsed_dt = parse_relative_datetime(raw_text)

    return {
        "hcp_id": hcp_id,
        "hcp_name": resolved_name,
        "interaction_type": interaction_type if interaction_type in valid_types else "meeting",
        "notes": raw_text,
        "summary": extraction.get("summary", raw_text[:200]),
        "outcomes": extraction.get("outcomes", "") or "",
        "sentiment": sentiment if sentiment in ["positive", "neutral", "negative"] else "neutral",
        "sentiment_score": float(extraction.get("sentiment_score", 0.0) or 0.0),
        "samples_provided": extraction.get("samples_provided", []) or [],
        "materials_shared": extraction.get("materials_shared", []) or [],
        "follow_up_actions": extraction.get("follow_up_actions", "") or "",
        # Deterministic parsing first (reliable for "yesterday", "last Monday", "at 3pm",
        # etc.) - the LLM's own guess is only used as a fallback for phrasing the regex
        # parser doesn't catch. Both end up null if the message truly doesn't mention a
        # date/time, and the frontend then keeps whatever was already in the form rather
        # than stomping it with "now".
        "occurred_date": parsed_dt["occurred_date"] or extraction.get("occurred_date") or None,
        "occurred_time": parsed_dt["occurred_time"] or extraction.get("occurred_time") or None,
    }


# ---------------------------------------------------------------------------
# Tool 1: Log Interaction
# ---------------------------------------------------------------------------
@tool
def log_interaction_tool(hcp_name: str, raw_text: str, interaction_type: str = "meeting") -> str:
    """
    Log a new interaction with a Healthcare Professional (HCP) from free text (e.g. typed
    into the chat interface). Uses the LLM to summarize the conversation, extract discussed
    drugs/topics, detect sentiment, and detect any samples mentioned as provided.
    Args:
        hcp_name: Name of the HCP the interaction was with.
        raw_text: Free-text description of what happened during the visit/call/chat.
        interaction_type: one of meeting, call, video_call, email, conference.
    """
    db = _db_session
    fields = extract_interaction_fields(raw_text, hcp_name, interaction_type)
    hcp = _get_or_create_hcp(fields["hcp_name"] or hcp_name, fields["hcp_id"])

    interaction = Interaction(
        hcp_id=hcp.id,
        interaction_type=fields["interaction_type"],
        occurred_at=datetime.utcnow(),
        attendees=json.dumps([]),
        notes=fields["notes"],
        summary=fields["summary"],
        materials_shared=json.dumps(fields["materials_shared"]),
        samples_provided=json.dumps(fields["samples_provided"]),
        sentiment=fields["sentiment"],
        sentiment_score=fields["sentiment_score"],
        outcomes=fields["outcomes"],
        follow_up_actions=fields["follow_up_actions"],
        source="chat",
    )
    db.add(interaction)
    db.commit()
    db.refresh(interaction)

    return json.dumps({
        "status": "logged",
        "interaction_id": interaction.id,
        "hcp_id": hcp.id,
        "hcp_name": hcp.name,
        "summary": fields["summary"],
        "sentiment": fields["sentiment"],
        "samples_provided": fields["samples_provided"],
    })


# ---------------------------------------------------------------------------
# Tool 2: Edit Interaction
# ---------------------------------------------------------------------------
@tool
def edit_interaction_tool(interaction_id: str, edit_instruction: str) -> str:
    """
    Edit a previously logged interaction based on a natural-language instruction,
    e.g. "change the sentiment to negative" or "add that samples of DrugX were given".
    Preserves the previous version in edit_history before applying changes.
    Args:
        interaction_id: ID of the interaction to modify.
        edit_instruction: Natural language description of the desired change.
    """
    db = _db_session
    interaction = db.query(Interaction).filter(Interaction.id == interaction_id).first()
    if not interaction:
        return json.dumps({"status": "error", "message": f"No interaction found with id {interaction_id}"})

    history = json.loads(interaction.edit_history) if interaction.edit_history else []
    history.append({
        "edited_at": datetime.utcnow().isoformat(),
        "previous_notes": interaction.notes,
        "previous_summary": interaction.summary,
        "previous_sentiment": interaction.sentiment.value if hasattr(interaction.sentiment, "value") else interaction.sentiment,
        "previous_samples": interaction.samples_provided,
        "previous_materials": interaction.materials_shared,
        "previous_outcomes": interaction.outcomes,
        "previous_follow_up_actions": interaction.follow_up_actions,
    })

    current_state = {
        "notes": interaction.notes,
        "summary": interaction.summary,
        "sentiment": interaction.sentiment.value if hasattr(interaction.sentiment, "value") else interaction.sentiment,
        "samples_provided": json.loads(interaction.samples_provided or "[]"),
        "materials_shared": json.loads(interaction.materials_shared or "[]"),
        "outcomes": interaction.outcomes,
        "follow_up_actions": interaction.follow_up_actions,
    }

    patch = call_llm_json(
        system_prompt=(
            "You are editing a structured HCP interaction record. Given the current record "
            "(JSON) and a natural language edit instruction, return STRICT JSON with ONLY the "
            "fields that should change, using the same schema: notes, summary, sentiment "
            "(positive/neutral/negative), samples_provided (list), materials_shared (list), "
            "outcomes, follow_up_actions. Only include keys that actually need to change."
        ),
        user_prompt=f"Current record: {json.dumps(current_state)}\n\nEdit instruction: {edit_instruction}",
    )

    if "notes" in patch:
        interaction.notes = patch["notes"]
    if "summary" in patch:
        interaction.summary = patch["summary"]
    if "sentiment" in patch and patch["sentiment"] in ["positive", "neutral", "negative"]:
        interaction.sentiment = patch["sentiment"]
    if "samples_provided" in patch:
        interaction.samples_provided = json.dumps(patch["samples_provided"])
    if "materials_shared" in patch:
        interaction.materials_shared = json.dumps(patch["materials_shared"])
    if "outcomes" in patch:
        interaction.outcomes = patch["outcomes"]
    if "follow_up_actions" in patch:
        interaction.follow_up_actions = patch["follow_up_actions"]

    interaction.edit_history = json.dumps(history)
    interaction.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(interaction)

    return json.dumps({
        "status": "updated",
        "interaction_id": interaction.id,
        "applied_changes": patch,
    })


# ---------------------------------------------------------------------------
# Tool 3: Fetch HCP Profile
# ---------------------------------------------------------------------------
@tool
def fetch_hcp_profile_tool(hcp_name: str) -> str:
    """
    Retrieve an HCP's profile along with a summary of their recent interaction history,
    so a rep can quickly get context before a visit or call.
    Args:
        hcp_name: Name (or partial name) of the HCP to look up.
    """
    db = _db_session
    hcp = db.query(HCP).filter(HCP.name.ilike(f"%{hcp_name}%")).first()
    if not hcp:
        return json.dumps({"status": "not_found", "message": f"No HCP found matching '{hcp_name}'"})

    recent = (
        db.query(Interaction)
        .filter(Interaction.hcp_id == hcp.id)
        .order_by(Interaction.occurred_at.desc())
        .limit(5)
        .all()
    )

    return json.dumps({
        "status": "found",
        "hcp": {
            "id": hcp.id,
            "name": hcp.name,
            "specialty": hcp.specialty,
            "hospital": hcp.hospital,
            "preferred_channel": hcp.preferred_channel,
            "notes": hcp.notes,
        },
        "recent_interactions": [
            {
                "id": i.id,
                "date": i.occurred_at.isoformat(),
                "summary": i.summary or (i.notes or "")[:150],
                "sentiment": i.sentiment.value if hasattr(i.sentiment, "value") else i.sentiment,
            }
            for i in recent
        ],
    })


# ---------------------------------------------------------------------------
# Tool 4: Schedule Follow-up
# ---------------------------------------------------------------------------
@tool
def schedule_followup_tool(hcp_name: str, reason: str, days_from_now: int = 7,
                            interaction_id: Optional[str] = None) -> str:
    """
    Schedule a follow-up task/reminder for a rep to reconnect with an HCP.
    Args:
        hcp_name: Name of the HCP to follow up with.
        reason: Why the follow-up is needed (e.g. "send clinical study data").
        days_from_now: How many days from today the follow-up should be due.
        interaction_id: Optional ID of the interaction this follow-up stems from.
    """
    db = _db_session
    hcp = _get_or_create_hcp(hcp_name)

    due_date = datetime.utcnow() + timedelta(days=days_from_now)
    followup = FollowUp(
        hcp_id=hcp.id,
        interaction_id=interaction_id,
        due_date=due_date,
        reason=reason,
    )
    db.add(followup)
    db.commit()
    db.refresh(followup)

    return json.dumps({
        "status": "scheduled",
        "followup_id": followup.id,
        "hcp_name": hcp.name,
        "due_date": due_date.isoformat(),
        "reason": reason,
    })


# ---------------------------------------------------------------------------
# Tool 5: Flag Adverse Event
# ---------------------------------------------------------------------------
@tool
def flag_adverse_event_tool(hcp_name: str, description: str,
                             interaction_id: Optional[str] = None) -> str:
    """
    Detect and file an adverse event (AE) report mentioned during an HCP interaction.
    This is a regulatory/pharmacovigilance safety net - any mention of a patient side
    effect or safety concern related to a drug should be captured here for review.
    Args:
        hcp_name: Name of the HCP who reported the adverse event.
        description: Description of the adverse event as reported.
        interaction_id: Optional ID of the related interaction.
    """
    db = _db_session
    hcp = _get_or_create_hcp(hcp_name)

    extraction = call_llm_json(
        system_prompt=(
            "You are a pharmacovigilance assistant. Given a description of a possible "
            "adverse drug event, return STRICT JSON with keys: drug_name (best guess of "
            "the implicated drug, or null), severity (one of mild, moderate, severe, unknown)."
        ),
        user_prompt=description,
    )

    ae = AdverseEvent(
        hcp_id=hcp.id,
        interaction_id=interaction_id,
        drug_name=extraction.get("drug_name"),
        description=description,
        severity=extraction.get("severity", "unknown"),
        status="pending_review",
    )
    db.add(ae)
    db.commit()
    db.refresh(ae)

    return json.dumps({
        "status": "flagged",
        "adverse_event_id": ae.id,
        "hcp_name": hcp.name,
        "drug_name": ae.drug_name,
        "severity": ae.severity,
        "note": "This AE has been routed to pending_review for compliance follow-up.",
    })


ALL_TOOLS = [
    log_interaction_tool,
    edit_interaction_tool,
    fetch_hcp_profile_tool,
    schedule_followup_tool,
    flag_adverse_event_tool,
]