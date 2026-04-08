from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.advisors import router as advisors_router
from app.api.cion import router as cion_router
from app.api.fund import router as fund_router
from app.api.ingest import router as ingest_router
from app.api.platforms import router as platforms_router
from app.api.rias import router as rias_router
from app.api.signals import router as signals_router
from app.api.thirteenf import router as thirteenf_router
from app.config import settings

app = FastAPI(
    title="pcIQ API",
    description="Private credit distribution intelligence — EDGAR signal layer",
    version="0.1.0",
)

_origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(advisors_router)
app.include_router(signals_router)
app.include_router(fund_router)
app.include_router(cion_router)
app.include_router(ingest_router)
app.include_router(rias_router)
app.include_router(platforms_router)
app.include_router(thirteenf_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
