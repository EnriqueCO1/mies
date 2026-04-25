from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routes import auth, conversations, chat, attachments, catastro

app = FastAPI(
    title="45Labs API",
    description="IB Study Assistant API",
    version="1.0.0"
)

# CORS — allow frontend to talk to backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(auth.router, prefix="/api")
app.include_router(conversations.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(attachments.router, prefix="/api")
app.include_router(catastro.router, prefix="/api")


@app.get("/")
async def root():
    return {"status": "ok", "service": "45Labs API"}


@app.get("/api/health")
async def health():
    return {"status": "healthy"}
