from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.models import AdverseEvent
from app.schemas.schemas import AdverseEventCreate, AdverseEventOut
from app.agent.tools import set_db_session, flag_adverse_event_tool

router = APIRouter(prefix="/api/adverse-events", tags=["Adverse Events"])


@router.get("", response_model=list[AdverseEventOut])
def list_adverse_events(hcp_id: str | None = None, db: Session = Depends(get_db)):
    q = db.query(AdverseEvent)
    if hcp_id:
        q = q.filter(AdverseEvent.hcp_id == hcp_id)
    return q.order_by(AdverseEvent.reported_at.desc()).all()


@router.post("")
def create_adverse_event(payload: AdverseEventCreate, db: Session = Depends(get_db)):
    set_db_session(db)
    result_json = flag_adverse_event_tool.invoke({
        "hcp_name": payload.hcp_name,
        "description": payload.description,
        "interaction_id": payload.interaction_id,
    })
    import json
    result = json.loads(result_json)
    ae = db.query(AdverseEvent).filter(AdverseEvent.id == result["adverse_event_id"]).first()
    return ae
