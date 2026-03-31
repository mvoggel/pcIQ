from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.signals import router as signals_router

app = FastAPI(
    title="pcIQ API",
    description="Private credit distribution intelligence — EDGAR signal layer",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
    ],  # Next.js dev server (port varies if 3000 is taken)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(signals_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
