from fastapi import FastAPI

from app.routers import auth

app = FastAPI(title="Calibration System")

app.include_router(auth.router)