from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


# ── Auth ──
class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str
    colegiado_number: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    user_id: str
    email: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UserProfile(BaseModel):
    id: str
    email: str
    name: str
    colegiado_number: Optional[str] = None
    created_at: Optional[str] = None


# ── Projects (stored in conversations table) ──
class CreateProjectRequest(BaseModel):
    title: Optional[str] = None
    address: str
    municipio: str  # mandatory — used by the PGOU resolver + Claude context
    ref_catastral: str
    building_type: Optional[str] = None
    main_materials: List[str] = []
    estimated_budget: Optional[float] = None
    ordenanza: Optional[str] = None


class UpdateProjectRequest(BaseModel):
    title: Optional[str] = None
    pinned: Optional[bool] = None
    address: Optional[str] = None
    municipio: Optional[str] = None
    building_type: Optional[str] = None
    main_materials: Optional[List[str]] = None
    estimated_budget: Optional[float] = None
    ordenanza: Optional[str] = None


class AttachmentOut(BaseModel):
    id: str
    kind: str
    filename: str
    mime_type: str
    size_bytes: int


class MessageOut(BaseModel):
    role: str
    content: str
    sources: Optional[List[dict]] = []
    attachments: Optional[List[AttachmentOut]] = []
    created_at: Optional[str] = None


class ProjectOut(BaseModel):
    id: str
    title: str
    pinned: bool = False
    created_at: str
    address: Optional[str] = None
    municipio: Optional[str] = None
    building_type: Optional[str] = None
    main_materials: Optional[List[str]] = []
    estimated_budget: Optional[float] = None
    ordenanza: Optional[str] = None
    catastro_data: Optional[dict] = None
    messages: Optional[List[MessageOut]] = []


# ── Chat ──
class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    conversation_id: str
    sources: List[dict] = []
    attachments: List[AttachmentOut] = []
    # Source indicators the frontend should light up for this turn — subset
    # of {"catastro", "pgou", "cte", "bcca"}.
    tools_used: List[str] = []
