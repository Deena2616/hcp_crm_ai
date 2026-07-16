from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.models import FollowUp
from app.schemas.schemas import FollowUpCreate, FollowUpOut
from app.agent.tools import set_db_session, _get_or_create_hcp

router = APIRouter(prefix="/api/followups", tags=["Follow-ups"])


@router.get("", response_model=list[FollowUpOut])
def list_followups(hcp_id: str | None = None, db: Session = Depends(get_db)):
    q = db.query(FollowUp)
    if hcp_id:
        q = q.filter(FollowUp.hcp_id == hcp_id)
    return q.order_by(FollowUp.due_date).all()


@router.post("", response_model=FollowUpOut)
def create_followup(payload: FollowUpCreate, db: Session = Depends(get_db)):
    set_db_session(db)
    hcp = _get_or_create_hcp(payload.hcp_name, payload.hcp_id)
    followup = FollowUp(
        hcp_id=hcp.id,
        interaction_id=payload.interaction_id,
        due_date=payload.due_date,
        reason=payload.reason,
    )
    db.add(followup)
    db.commit()
    db.refresh(followup)
    return followup


@router.patch("/{followup_id}/complete", response_model=FollowUpOut)
def complete_followup(followup_id: str, db: Session = Depends(get_db)):
    followup = db.query(FollowUp).filter(FollowUp.id == followup_id).first()
    if not followup:
        raise HTTPException(status_code=404, detail="Follow-up not found")
    followup.completed = True
    db.commit()
    db.refresh(followup)
    return followup
