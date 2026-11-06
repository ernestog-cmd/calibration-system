import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

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
from app.services.scheduler import start_scheduler

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = start_scheduler()
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Calibration System", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(equipment.router)
app.include_router(calibrations.router)
app.include_router(certificates.router)
app.include_router(usage.router)
app.include_router(alerts.router)
app.include_router(reports.router)
app.include_router(audit.router)