import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Text, DateTime, ForeignKey, Enum as SAEnum, Float, Boolean
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


def gen_uuid():
    return str(uuid.uuid4())


class SentimentEnum(str, enum.Enum):
    positive = "positive"
    neutral = "neutral"
    negative = "negative"


class InteractionType(str, enum.Enum):
    meeting = "meeting"
    call = "call"
    video_call = "video_call"
    email = "email"
    conference = "conference"


class HCP(Base):
    __tablename__ = "hcps"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name = Column(String(255), nullable=False)
    specialty = Column(String(255), nullable=True)
    hospital = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    preferred_channel = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    interactions = relationship("Interaction", back_populates="hcp", cascade="all, delete-orphan")
    follow_ups = relationship("FollowUp", back_populates="hcp", cascade="all, delete-orphan")
    adverse_events = relationship("AdverseEvent", back_populates="hcp", cascade="all, delete-orphan")


class Interaction(Base):
    __tablename__ = "interactions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    hcp_id = Column(UUID(as_uuid=False), ForeignKey("hcps.id"), nullable=False)

    interaction_type = Column(SAEnum(InteractionType), default=InteractionType.meeting)
    occurred_at = Column(DateTime, default=datetime.utcnow)   # date+time of the visit/call itself
    attendees = Column(Text, nullable=True)          # JSON-encoded list of names

    notes = Column(Text, nullable=True)              # "Topics Discussed" free text (or raw chat text)
    summary = Column(Text, nullable=True)             # short AI/manual summary shown in history

    materials_shared = Column(Text, nullable=True)   # JSON-encoded list
    samples_provided = Column(Text, nullable=True)   # JSON-encoded list

    sentiment = Column(SAEnum(SentimentEnum), default=SentimentEnum.neutral)
    sentiment_score = Column(Float, nullable=True)

    outcomes = Column(Text, nullable=True)
    follow_up_actions = Column(Text, nullable=True)

    source = Column(String(20), default="form")       # "form" or "chat"
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    edit_history = Column(Text, nullable=True)        # JSON-encoded list of prior versions

    hcp = relationship("HCP", back_populates="interactions")


class FollowUp(Base):
    __tablename__ = "follow_ups"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    hcp_id = Column(UUID(as_uuid=False), ForeignKey("hcps.id"), nullable=False)
    interaction_id = Column(UUID(as_uuid=False), ForeignKey("interactions.id"), nullable=True)
    due_date = Column(DateTime, nullable=False)
    reason = Column(Text, nullable=True)
    completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    hcp = relationship("HCP", back_populates="follow_ups")


class AdverseEvent(Base):
    __tablename__ = "adverse_events"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    hcp_id = Column(UUID(as_uuid=False), ForeignKey("hcps.id"), nullable=False)
    interaction_id = Column(UUID(as_uuid=False), ForeignKey("interactions.id"), nullable=True)
    drug_name = Column(String(255), nullable=True)
    description = Column(Text, nullable=False)
    severity = Column(String(50), default="unknown")   # mild/moderate/severe/unknown
    reported_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(50), default="pending_review")

    hcp = relationship("HCP", back_populates="adverse_events")
