from fastapi import FastAPI

from app.routers import auth, users

app = FastAPI(title="Calibration System")

app.include_router(auth.router)
app.include_router(users.router)