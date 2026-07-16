from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.session import Base, engine
from app.models import models  # noqa: F401 - ensures models are registered before create_all
from app.routers import hcps, interactions, chat, followups, adverse_events, assist

app = FastAPI(
    title="AI-First HCP CRM API",
    description="Backend for the Log Interaction Screen: structured form + LangGraph chat agent.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    from app.db.seed import seed_doctors
    seed_doctors()


@app.get("/")
def root():
    return {"status": "ok", "service": "hcp-crm-backend"}


@app.get("/api/health")
def health():
    return {"status": "healthy"}


app.include_router(hcps.router)
app.include_router(interactions.router)
app.include_router(chat.router)
app.include_router(followups.router)
app.include_router(adverse_events.router)
app.include_router(assist.router)