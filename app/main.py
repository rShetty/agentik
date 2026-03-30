"""Agentik API — FastAPI application entry point."""
from fastapi import FastAPI

from app.database import Base, engine
from app.routers.agents import router as agents_router
from app.routers.lifecycle import router as lifecycle_router

# Create tables (for development / test without Alembic)
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Agentik",
    description="Generic agentic platform API — manage agents, skills, and runs.",
    version="0.1.0",
)

app.include_router(agents_router)
app.include_router(lifecycle_router)


@app.get("/healthz", tags=["system"])
def health() -> dict:
    return {"status": "ok"}
