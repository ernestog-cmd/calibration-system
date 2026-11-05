from fastapi import FastAPI

from app.routers import audit, auth, calibrations, equipment, usage, users

app = FastAPI(title="Calibration System")

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(equipment.router)
app.include_router(calibrations.router)
app.include_router(usage.router)
app.include_router(audit.router)