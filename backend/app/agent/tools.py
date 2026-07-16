"""
Six LangGraph tools for the HCP sales agent:

1. log_interaction_tool    - captures a new HCP interaction (LLM extraction), used as a
                              DRAFT-ONLY path from chat (see graph.py); still a real,
                              immediately-committing tool if invoked directly.
2. edit_interaction_tool   - modifies a previously logged interaction immediately (commits
                              right away, no confirmation/draft step), keeping version history.
3. fetch_hcp_profile_tool  - retrieves an HCP's profile + recent interaction history.
4. schedule_followup_tool  - creates a follow-up reminder/task tied to an HCP. Committed
                              immediately, callable from both the chat "adding" flow and a
                              dedicated follow-up prompt area.
5. search_interactions_tool- searches/filters previously logged interactions in Postgres
                              by sentiment, HCP name, drug/topic keyword, and/or date range,
                              e.g. "Show me all positive interactions."
6. flag_adverse_event_tool - detects & files an adverse-event report from interaction text.
                              Commits immediately - regulatory/pharmacovigilance safety net.

Each tool is a plain Python function decorated with LangChain's @tool so it can be bound
to the LangGraph agent node and invoked by name with structured args.

NOTE on the draft flow: `extract_interaction_fields` below does the same LLM extraction as
log_interaction_tool but performs NO database write. It's used by the chat graph's
draft_log_interaction_node (see agent/graph.py) so a chat-described NEW interaction gets
bound into the structured form for the rep to review/edit, rather than being committed
straight to the database. log_interaction_tool itself is kept (and still commits) so it
remains available as a genuine LangGraph tool for the classification step / tool listing
and for any future flow that wants an immediate, non-draft commit.

IMPORTANT DISTINCTION FROM LOGGING:
`edit_interaction_tool`, `schedule_followup_tool`, and `flag_adverse_event_tool` are NOT
draft tools. Unlike creating a brand-new interaction (which benefits from a review step,
since the rep hasn't seen the extracted fields yet), an edit, a follow-up request, or an
adverse-event report is a small, targeted, already-specific instruction - routing these
through the structured form draft cycle would just add friction for no safety benefit (and
for AE reports, could risk losing a safety-relevant report if the rep never returns to
"confirm" it). So all three commit directly to the DB when the agent calls them, from
either the chat panel or a dedicated prompt area, with no separate "click to save" step.
"""
import json
import re
from datetime import datetime, timedelta
from typing import Optional

from langchain_core.tools import tool
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

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


def _find_hcp(hcp_name: str) -> Optional[HCP]:
    """Read-only lookup - does NOT create a new HCP. Used by tools that should fail
    gracefully (edit, search) rather than silently creating a phantom HCP record."""
    db = _db_session
    if not hcp_name:
        return None
    return db.query(HCP).filter(HCP.name.ilike(f"%{hcp_name}%")).first()


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

    # explicit DD-MM-YYYY or DD/MM/YYYY, e.g. "15-07-2026" - checked before the relative
    # phrases below so an explicit date always wins over a vague one if both appear.
    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", text)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            result_date = datetime(year, month, day).strftime("%Y-%m-%d")
        except ValueError:
            pass

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


def _parse_relative_days(text: str) -> Optional[int]:
    """
    Resolves phrases like 'in 5 days', 'next week', 'in 2 weeks', 'tomorrow', 'next month'
    into a days_from_now integer for schedule_followup_tool. Deterministic for the same
    reason parse_relative_datetime is deterministic - date arithmetic shouldn't be left to
    a small LLM. Returns None if nothing matches (caller falls back to the LLM's own guess
    or a default).
    """
    text_l = text.lower()

    m = re.search(r"in\s+(\d+)\s+days?", text_l)
    if m:
        return int(m.group(1))

    m = re.search(r"in\s+(\d+)\s+weeks?", text_l)
    if m:
        return int(m.group(1)) * 7

    if "tomorrow" in text_l:
        return 1
    if "next week" in text_l:
        return 7
    if "next month" in text_l:
        return 30
    if "next fortnight" in text_l or "in a fortnight" in text_l:
        return 14

    m = re.search(r"(\d+)\s+days?\s+from\s+now", text_l)
    if m:
        return int(m.group(1))

    return None


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

    NOTE: when called from the chat agent graph, new-interaction requests are routed to
    draft_log_interaction_node instead (see graph.py DRAFT_TOOLS), so in practice this
    executes as an immediate commit only when invoked outside that draft path (e.g. a
    future non-chat integration, or direct tool invocation/testing).

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
# Tool 2: Edit Interaction  (COMMITS IMMEDIATELY - no draft/confirmation step)
# ---------------------------------------------------------------------------
@tool
def edit_interaction_tool(edit_instruction: str, interaction_id: Optional[str] = None,
                           hcp_name: Optional[str] = None) -> str:
    """
    Edit a previously logged interaction based on a natural-language instruction,
    e.g. "change the sentiment to negative", "add that samples of DrugX were given", or
    "change the date of that meeting to 15-07-2026". Applies and COMMITS the change
    immediately - there is no draft/review step for edits, unlike creating a brand-new
    interaction from chat. Preserves the previous version in edit_history before applying
    changes.

    Resolution order for which interaction to edit:
      1. interaction_id, if given explicitly.
      2. Otherwise, if hcp_name is given, the most recent interaction for that HCP.
      3. Otherwise, the single most recent interaction across all HCPs (best-effort, used
         when the rep says something like "actually make that negative" right after
         logging/discussing one interaction in the same conversation).

    Args:
        edit_instruction: Natural language description of the desired change.
        interaction_id: ID of the interaction to modify, if known.
        hcp_name: Name of the HCP whose most recent interaction should be edited, if
            interaction_id isn't known/provided.
    """
    db = _db_session
    interaction = None

    if interaction_id:
        interaction = db.query(Interaction).filter(Interaction.id == interaction_id).first()

    if not interaction and hcp_name:
        hcp = _find_hcp(hcp_name)
        if hcp:
            interaction = (
                db.query(Interaction)
                .filter(Interaction.hcp_id == hcp.id)
                .order_by(Interaction.occurred_at.desc())
                .first()
            )
        if not interaction:
            return json.dumps({
                "status": "error",
                "message": f"No interaction found for HCP matching '{hcp_name}' to edit.",
            })

    if not interaction:
        interaction = db.query(Interaction).order_by(Interaction.updated_at.desc().nullslast(),
                                                       Interaction.occurred_at.desc()).first()

    if not interaction:
        return json.dumps({
            "status": "error",
            "message": "No interaction found to edit. Provide an interaction_id or hcp_name.",
        })

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
        "previous_occurred_at": interaction.occurred_at.isoformat() if interaction.occurred_at else None,
    })

    current_state = {
        "notes": interaction.notes,
        "summary": interaction.summary,
        "sentiment": interaction.sentiment.value if hasattr(interaction.sentiment, "value") else interaction.sentiment,
        "samples_provided": json.loads(interaction.samples_provided or "[]"),
        "materials_shared": json.loads(interaction.materials_shared or "[]"),
        "outcomes": interaction.outcomes,
        "follow_up_actions": interaction.follow_up_actions,
        "occurred_at": interaction.occurred_at.isoformat() if interaction.occurred_at else None,
    }

    today_str = datetime.utcnow().strftime("%Y-%m-%d")

    patch = call_llm_json(
        system_prompt=(
            "You are editing a structured HCP interaction record. Given the current record "
            "(JSON) and a natural language edit instruction, return STRICT JSON with ONLY the "
            "fields that should change, using the same schema: notes, summary, sentiment "
            "(positive/neutral/negative), samples_provided (list - the FULL desired list, not "
            "just the delta, if this field is included), materials_shared (list - FULL desired "
            "list if included), outcomes, follow_up_actions, occurred_date (YYYY-MM-DD, only if "
            f"the instruction mentions changing the date/when the meeting happened - today is "
            f"{today_str}, resolve any relative or DD-MM-YYYY / DD/MM/YYYY phrasing to an actual "
            "date). Only include keys that actually need to change. If the instruction says to "
            "ADD a sample/material, return the existing list plus the new item(s), not just the "
            "new item(s) alone."
        ),
        user_prompt=f"Current record: {json.dumps(current_state)}\n\nEdit instruction: {edit_instruction}",
    )

    applied_changes = {}

    # Deterministic date parsing takes priority over the LLM's own guess, same rationale
    # as parse_relative_datetime elsewhere in this module - date arithmetic/parsing (e.g.
    # explicit "15-07-2026") is more reliable done in plain Python than left to the LLM.
    parsed_dt = parse_relative_datetime(edit_instruction)
    new_occurred_date = parsed_dt["occurred_date"] or patch.get("occurred_date")

    if "notes" in patch:
        interaction.notes = patch["notes"]
        applied_changes["notes"] = patch["notes"]
    if "summary" in patch:
        interaction.summary = patch["summary"]
        applied_changes["summary"] = patch["summary"]
    if "sentiment" in patch and patch["sentiment"] in ["positive", "neutral", "negative"]:
        interaction.sentiment = patch["sentiment"]
        applied_changes["sentiment"] = patch["sentiment"]
    if "samples_provided" in patch:
        interaction.samples_provided = json.dumps(patch["samples_provided"])
        applied_changes["samples_provided"] = patch["samples_provided"]
    if "materials_shared" in patch:
        interaction.materials_shared = json.dumps(patch["materials_shared"])
        applied_changes["materials_shared"] = patch["materials_shared"]
    if "outcomes" in patch:
        interaction.outcomes = patch["outcomes"]
        applied_changes["outcomes"] = patch["outcomes"]
    if "follow_up_actions" in patch:
        interaction.follow_up_actions = patch["follow_up_actions"]
        applied_changes["follow_up_actions"] = patch["follow_up_actions"]
    if new_occurred_date:
        try:
            existing_time = interaction.occurred_at.time() if interaction.occurred_at else datetime.min.time()
            new_date = datetime.strptime(new_occurred_date, "%Y-%m-%d").date()
            interaction.occurred_at = datetime.combine(new_date, existing_time)
            applied_changes["occurred_at"] = interaction.occurred_at.isoformat()
        except ValueError:
            pass

    if not applied_changes:
        return json.dumps({
            "status": "no_change",
            "interaction_id": interaction.id,
            "message": "I couldn't determine a concrete field to change from that instruction.",
        })

    interaction.edit_history = json.dumps(history)
    interaction.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(interaction)

    return json.dumps({
        "status": "updated",
        "interaction_id": interaction.id,
        "hcp_id": interaction.hcp_id,
        "applied_changes": applied_changes,
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
# Tool 4: Schedule Follow-up  (COMMITS IMMEDIATELY, usable from both prompt areas)
# ---------------------------------------------------------------------------
@tool
def schedule_followup_tool(hcp_name: str, reason: str, days_from_now: Optional[int] = None,
                            when_text: Optional[str] = None,
                            interaction_id: Optional[str] = None) -> str:
    """
    Schedule a follow-up task/reminder for a rep to reconnect with an HCP. Commits
    immediately - no draft/review step. Callable from both the chat panel's "adding a new
    interaction" context (e.g. "...and follow up in 5 days with the trial data") and a
    dedicated follow-up prompt area (e.g. "Remind me to follow up with Dr. Rao next week
    about samples").

    Args:
        hcp_name: Name of the HCP to follow up with.
        reason: Why the follow-up is needed (e.g. "send clinical study data").
        days_from_now: How many days from today the follow-up should be due, if already
            known as a plain integer.
        when_text: Raw natural-language timing phrase (e.g. "next week", "in 5 days",
            "tomorrow"), used to deterministically resolve days_from_now when the caller
            only has the original phrase rather than a pre-computed integer. Ignored if
            days_from_now is already provided.
        interaction_id: Optional ID of the interaction this follow-up stems from.
    """
    db = _db_session
    hcp = _get_or_create_hcp(hcp_name)

    resolved_days = days_from_now
    if resolved_days is None and when_text:
        resolved_days = _parse_relative_days(when_text)
    if resolved_days is None:
        resolved_days = 7  # sensible default when nothing else resolves it

    due_date = datetime.utcnow() + timedelta(days=resolved_days)
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
        "days_from_now": resolved_days,
        "reason": reason,
    })


# ---------------------------------------------------------------------------
# Tool 5: Search Interactions
# ---------------------------------------------------------------------------
@tool
def search_interactions_tool(sentiment: Optional[str] = None, hcp_name: Optional[str] = None,
                              keyword: Optional[str] = None, interaction_type: Optional[str] = None,
                              date_from: Optional[str] = None, date_to: Optional[str] = None,
                              when_text: Optional[str] = None, limit: int = 10) -> str:
    """
    Search / filter previously logged interactions in the database. Use this for requests
    like "Show me all positive interactions", "What did we discuss with Dr. Rao about
    Cardexil?", "Any negative interactions last week?", or "Show me all calls this month".
    The AI uses this tool to query PostgreSQL directly rather than guessing from memory.

    Args:
        sentiment: Filter by one of positive, neutral, negative. Omit for any sentiment.
        hcp_name: Filter to interactions with an HCP whose name matches (partial ok).
        keyword: Free-text keyword to match against notes/summary/outcomes (e.g. a drug
            or topic name like "Cardexil").
        interaction_type: Filter by one of meeting, call, video_call, email, conference.
        date_from: Only interactions on/after this date, format YYYY-MM-DD.
        date_to: Only interactions on/before this date, format YYYY-MM-DD.
        when_text: Raw natural-language time phrase (e.g. "last week", "this month",
            "yesterday"), used to derive date_from/date_to deterministically when the
            caller has the original phrase instead of pre-computed dates. Ignored if
            date_from/date_to are already provided.
        limit: Max number of results to return (default 10).
    """
    db = _db_session
    query = db.query(Interaction)

    resolved_from = date_from
    resolved_to = date_to

    if when_text and not (resolved_from or resolved_to):
        now = datetime.utcnow()
        text_l = when_text.lower()
        if "today" in text_l:
            resolved_from = resolved_to = now.strftime("%Y-%m-%d")
        elif "yesterday" in text_l:
            d = (now - timedelta(days=1)).strftime("%Y-%m-%d")
            resolved_from = resolved_to = d
        elif "this week" in text_l:
            start = now - timedelta(days=now.weekday())
            resolved_from = start.strftime("%Y-%m-%d")
            resolved_to = now.strftime("%Y-%m-%d")
        elif "last week" in text_l:
            start = now - timedelta(days=now.weekday() + 7)
            end = start + timedelta(days=6)
            resolved_from = start.strftime("%Y-%m-%d")
            resolved_to = end.strftime("%Y-%m-%d")
        elif "this month" in text_l:
            resolved_from = now.replace(day=1).strftime("%Y-%m-%d")
            resolved_to = now.strftime("%Y-%m-%d")
        elif "last month" in text_l:
            first_of_this_month = now.replace(day=1)
            last_month_end = first_of_this_month - timedelta(days=1)
            last_month_start = last_month_end.replace(day=1)
            resolved_from = last_month_start.strftime("%Y-%m-%d")
            resolved_to = last_month_end.strftime("%Y-%m-%d")
        else:
            parsed = parse_relative_datetime(when_text, now)
            if parsed["occurred_date"]:
                resolved_from = resolved_to = parsed["occurred_date"]

    if sentiment in ["positive", "neutral", "negative"]:
        query = query.filter(Interaction.sentiment == sentiment)

    if interaction_type in ["meeting", "call", "video_call", "email", "conference"]:
        query = query.filter(Interaction.interaction_type == interaction_type)

    if hcp_name:
        hcp = _find_hcp(hcp_name)
        if not hcp:
            return json.dumps({
                "status": "found",
                "count": 0,
                "results": [],
                "message": f"No HCP found matching '{hcp_name}', so no interactions to show.",
            })
        query = query.filter(Interaction.hcp_id == hcp.id)

    if keyword:
        like = f"%{keyword}%"
        query = query.filter(or_(
            Interaction.notes.ilike(like),
            Interaction.summary.ilike(like),
            Interaction.outcomes.ilike(like),
        ))

    if resolved_from:
        try:
            dt_from = datetime.strptime(resolved_from, "%Y-%m-%d")
            query = query.filter(Interaction.occurred_at >= dt_from)
        except ValueError:
            pass

    if resolved_to:
        try:
            dt_to = datetime.strptime(resolved_to, "%Y-%m-%d") + timedelta(days=1)
            query = query.filter(Interaction.occurred_at < dt_to)
        except ValueError:
            pass

    safe_limit = max(1, min(int(limit or 10), 50))
    results = query.order_by(Interaction.occurred_at.desc()).limit(safe_limit).all()

    hcp_ids = {r.hcp_id for r in results}
    hcp_names_by_id = {
        h.id: h.name for h in db.query(HCP).filter(HCP.id.in_(hcp_ids)).all()
    } if hcp_ids else {}

    return json.dumps({
        "status": "found",
        "count": len(results),
        "filters_applied": {
            "sentiment": sentiment,
            "hcp_name": hcp_name,
            "keyword": keyword,
            "interaction_type": interaction_type,
            "date_from": resolved_from,
            "date_to": resolved_to,
        },
        "results": [
            {
                "id": r.id,
                "hcp_name": hcp_names_by_id.get(r.hcp_id, "Unknown"),
                "date": r.occurred_at.isoformat(),
                "interaction_type": r.interaction_type.value if hasattr(r.interaction_type, "value") else r.interaction_type,
                "summary": r.summary or (r.notes or "")[:150],
                "sentiment": r.sentiment.value if hasattr(r.sentiment, "value") else r.sentiment,
                "outcomes": r.outcomes,
            }
            for r in results
        ],
    })


# ---------------------------------------------------------------------------
# Tool 6: Flag Adverse Event  (COMMITS IMMEDIATELY - regulatory safety net)
# ---------------------------------------------------------------------------
@tool
def flag_adverse_event_tool(hcp_name: str, description: str,
                             interaction_id: Optional[str] = None) -> str:
    """
    Detect and file an adverse event (AE) report mentioned during an HCP interaction.
    This is a regulatory/pharmacovigilance safety net - any mention of a patient side
    effect or safety concern related to a drug should be captured here for review.
    Commits immediately - no draft/review step, since AE capture must not be lost.

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
    search_interactions_tool,
    flag_adverse_event_tool,
]