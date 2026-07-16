import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.models import Interaction, HCP

from app.schemas.schemas import (
    InteractionCreate,
    InteractionUpdate,
    InteractionOut,
    InteractionSearchParams,
)

from app.agent.tools import (
    set_db_session,
    log_interaction_tool,
    edit_interaction_tool,
    search_interactions_tool,
    _get_or_create_hcp,
)

router = APIRouter(
    prefix="/api/interactions",
    tags=["Interactions"]
)

VALID_TYPES = [
    "meeting",
    "call",
    "video_call",
    "email",
    "conference",
]

VALID_SENTIMENTS = [
    "positive",
    "neutral",
    "negative",
]


# ------------------------------------------------------------------
# List Interactions
# ------------------------------------------------------------------

@router.get("", response_model=list[InteractionOut])
def list_interactions(
    hcp_id: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(Interaction)

    if hcp_id:
        q = q.filter(Interaction.hcp_id == hcp_id)

    return q.order_by(
        Interaction.created_at.desc()
    ).all()


# ------------------------------------------------------------------
# Search Interactions (NEW)
# ------------------------------------------------------------------

@router.get("/search")
def search_interactions_rest(
    params: InteractionSearchParams = Depends(),
    db: Session = Depends(get_db),
):
    """
    Search interactions using the same backend logic as the
    chatbot/LangGraph search tool.

    Example:

    /api/interactions/search?sentiment=positive

    /api/interactions/search?hcp_name=Dr Smith

    /api/interactions/search?keyword=diabetes

    /api/interactions/search?interaction_type=meeting

    /api/interactions/search?date_from=2026-01-01&date_to=2026-01-31

    /api/interactions/search?limit=20
    """

    set_db_session(db)

    raw = search_interactions_tool.invoke(
        params.model_dump()
    )

    return json.loads(raw)["results"]


# ------------------------------------------------------------------
# Get Interaction
# ------------------------------------------------------------------

@router.get("/{interaction_id}", response_model=InteractionOut)
def get_interaction(
    interaction_id: str,
    db: Session = Depends(get_db),
):
    interaction = (
        db.query(Interaction)
        .filter(Interaction.id == interaction_id)
        .first()
    )

    if not interaction:
        raise HTTPException(
            status_code=404,
            detail="Interaction not found",
        )

    return interaction


# ------------------------------------------------------------------
# Create Interaction
# ------------------------------------------------------------------

@router.post("")
def create_interaction_form(
    payload: InteractionCreate,
    db: Session = Depends(get_db),
):
    """
    Structured-form path.

    If raw_text is provided,
    the request is routed through the
    LLM extraction pipeline.

    Otherwise all form fields are stored directly.
    """

    set_db_session(db)

    hcp_name = payload.hcp_name

    if not hcp_name and payload.hcp_id:
        hcp = (
            db.query(HCP)
            .filter(HCP.id == payload.hcp_id)
            .first()
        )

        hcp_name = hcp.name if hcp else None

    if not hcp_name:
        raise HTTPException(
            status_code=400,
            detail="hcp_id or hcp_name is required",
        )

    # ----------------------------
    # Chat / Raw text path
    # ----------------------------

    if payload.raw_text and not payload.notes:

        result_json = log_interaction_tool.invoke(
            {
                "hcp_name": hcp_name,
                "raw_text": payload.raw_text,
                "interaction_type": payload.interaction_type
                or "meeting",
            }
        )

        result = json.loads(result_json)

        interaction = (
            db.query(Interaction)
            .filter(
                Interaction.id == result["interaction_id"]
            )
            .first()
        )

        return interaction

    # ----------------------------
    # Structured form path
    # ----------------------------

    hcp = _get_or_create_hcp(
        hcp_name,
        payload.hcp_id,
    )

    interaction = Interaction(
        hcp_id=hcp.id,
        interaction_type=(
            payload.interaction_type
            if payload.interaction_type in VALID_TYPES
            else "meeting"
        ),
        occurred_at=payload.occurred_at
        or datetime.utcnow(),
        attendees=json.dumps(
            payload.attendees or []
        ),
        notes=payload.notes,
        summary=(
            payload.notes[:200]
            if payload.notes
            else None
        ),
        materials_shared=json.dumps(
            payload.materials_shared or []
        ),
        samples_provided=json.dumps(
            payload.samples_provided or []
        ),
        sentiment=(
            payload.sentiment
            if payload.sentiment in VALID_SENTIMENTS
            else "neutral"
        ),
        outcomes=payload.outcomes,
        follow_up_actions=payload.follow_up_actions,
        source="form",
    )

    db.add(interaction)
    db.commit()
    db.refresh(interaction)

    return interaction


# ------------------------------------------------------------------
# Update Interaction
# ------------------------------------------------------------------

@router.patch("/{interaction_id}")
def update_interaction(
    interaction_id: str,
    payload: InteractionUpdate,
    db: Session = Depends(get_db),
):
    set_db_session(db)

    interaction = (
        db.query(Interaction)
        .filter(
            Interaction.id == interaction_id
        )
        .first()
    )

    if not interaction:
        raise HTTPException(
            status_code=404,
            detail="Interaction not found",
        )

    # ----------------------------
    # AI Edit
    # ----------------------------

    if payload.edit_reason:

        edit_interaction_tool.invoke(
            {
                "interaction_id": interaction_id,
                "edit_instruction": payload.edit_reason,
            }
        )

        db.refresh(interaction)

        return interaction

    # ----------------------------
    # Manual Updates
    # ----------------------------

    if payload.notes is not None:
        interaction.notes = payload.notes

    if (
        payload.interaction_type is not None
        and payload.interaction_type
        in VALID_TYPES
    ):
        interaction.interaction_type = (
            payload.interaction_type
        )

    if payload.attendees is not None:
        interaction.attendees = json.dumps(
            payload.attendees
        )

    if payload.materials_shared is not None:
        interaction.materials_shared = json.dumps(
            payload.materials_shared
        )

    if payload.samples_provided is not None:
        interaction.samples_provided = json.dumps(
            payload.samples_provided
        )

    if (
        payload.sentiment is not None
        and payload.sentiment
        in VALID_SENTIMENTS
    ):
        interaction.sentiment = payload.sentiment

    if payload.sentiment_score is not None:
        interaction.sentiment_score = (
            payload.sentiment_score
        )

    if payload.outcomes is not None:
        interaction.outcomes = payload.outcomes

    if payload.follow_up_actions is not None:
        interaction.follow_up_actions = (
            payload.follow_up_actions
        )

    db.commit()
    db.refresh(interaction)

    return interaction