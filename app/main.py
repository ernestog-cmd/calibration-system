import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.routers import (
    alerts,
    audit,
    auth,
    calibrations,
    certificates,
    equipment,
    reports,
    usage,
    users,
)
from app.services.bootstrap import create_first_admin, maybe_seed_demo_data
from app.services.scheduler import start_scheduler

logging.basicConfig(level=logging.INFO)

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_first_admin()
    maybe_seed_demo_data()
    scheduler = start_scheduler()
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Calibration System", lifespan=lifespan)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/ui/")


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(equipment.router)
app.include_router(calibrations.router)
app.include_router(certificates.router)
app.include_router(usage.router)
app.include_router(alerts.router)
app.include_router(reports.router)
app.include_router(audit.router)

# Mounted last so it never shadows an API route
app.mount("/ui", StaticFiles(directory=STATIC_DIR, html=True), name="ui")