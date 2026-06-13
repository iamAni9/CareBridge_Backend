import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from routers import auth, assistance, volunteer, wellness, family

app = FastAPI(
    title="CareBridge API",
    description="One-Tap Assistance for elder care — volunteer matching with AI briefings",
    version="1.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:3000",
        os.getenv("FRONTEND_URL", "http://localhost:5173"),
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(assistance.router)
app.include_router(volunteer.router)
app.include_router(wellness.router)
app.include_router(family.router)


@app.get("/")
def health_check():
    return {"status": "ok", "service": "CareBridge API"}
