from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.models import HCP
from app.schemas.schemas import HCPCreate, HCPOut

router = APIRouter(prefix="/api/hcps", tags=["HCPs"])


@router.get("", response_model=list[HCPOut])
def list_hcps(db: Session = Depends(get_db)):
    return db.query(HCP).order_by(HCP.name).all()


@router.post("", response_model=HCPOut)
def create_hcp(payload: HCPCreate, db: Session = Depends(get_db)):
    hcp = HCP(**payload.model_dump())
    db.add(hcp)
    db.commit()
    db.refresh(hcp)
    return hcp


@router.get("/{hcp_id}", response_model=HCPOut)
def get_hcp(hcp_id: str, db: Session = Depends(get_db)):
    hcp = db.query(HCP).filter(HCP.id == hcp_id).first()
    if not hcp:
        raise HTTPException(status_code=404, detail="HCP not found")
    return hcp
