import json
from fastapi import APIRouter, HTTPException, Depends
from typing import List
from app.models import (
    CreateProjectRequest,
    UpdateProjectRequest,
    ProjectOut,
    MessageOut,
    AttachmentOut,
)
from app.auth import get_user_supabase, get_current_user

router = APIRouter(prefix="/conversations", tags=["projects"])


def _parse_catastro_json(raw) -> dict | None:
    """Safely parse catastro_data which may be a JSON string or already a dict."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            import json
            return json.loads(raw)
        except Exception:
            return None
    return None


def _project_from_row(conv: dict, messages: list | None = None) -> ProjectOut:
    """Build a ProjectOut from a conversations table row."""
    return ProjectOut(
        id=conv["id"],
        title=conv["title"],
        pinned=conv.get("pinned", False),
        created_at=conv["created_at"],
        address=conv.get("address"),
        municipio=conv.get("municipio"),
        building_type=conv.get("building_type"),
        main_materials=conv.get("main_materials", []),
        estimated_budget=conv.get("estimated_budget"),
        ordenanza=conv.get("ordenanza"),
        catastro_data=_parse_catastro_json(conv.get("catastro_data")),
        messages=messages or [],
    )


@router.get("/", response_model=List[ProjectOut])
async def list_projects(user=Depends(get_current_user)):
    """List all projects for the current user."""
    client = get_user_supabase(user["token"])
    try:
        result = client.table("conversations") \
            .select("*") \
            .eq("user_id", user["id"]) \
            .order("created_at", desc=True) \
            .execute()

        return [_project_from_row(conv) for conv in result.data]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=ProjectOut)
async def create_project(req: CreateProjectRequest, user=Depends(get_current_user)):
    """Create a new project with intake metadata."""
    client = get_user_supabase(user["token"])

    # Auto-generate title from building type + address if not provided
    title = req.title
    if not title:
        addr_short = req.address[:60] if req.address else "Sin dirección"
        title = f"{req.building_type} — {addr_short}"

    try:
        insert_data = {
            "user_id": user["id"],
            "title": title,
            "pinned": False,
            "address": req.address,
            "municipio": req.municipio,
            "building_type": req.building_type,
            "main_materials": req.main_materials,
            "estimated_budget": req.estimated_budget,
            "ordenanza": req.ordenanza,
        }
        # Store ref_catastral for the catastro lookup
        if req.ref_catastral:
            insert_data["catastro_data"] = json.dumps({
                "success": False,
                "ref_catastral_input": req.ref_catastral.strip().upper(),
                "error": "Pendiente de consulta",
            }, ensure_ascii=False)
        result = client.table("conversations").insert(insert_data).execute()

        return _project_from_row(result.data[0])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{conversation_id}", response_model=ProjectOut)
async def get_project(conversation_id: str, user=Depends(get_current_user)):
    """Get a project with its messages and attachments."""
    client = get_user_supabase(user["token"])
    try:
        conv_result = client.table("conversations") \
            .select("*") \
            .eq("id", conversation_id) \
            .eq("user_id", user["id"]) \
            .single() \
            .execute()

        msg_result = client.table("messages") \
            .select("*") \
            .eq("conversation_id", conversation_id) \
            .order("created_at") \
            .execute()

        msg_ids = [m["id"] for m in msg_result.data]
        attachments_by_message: dict[str, list[AttachmentOut]] = {mid: [] for mid in msg_ids}

        if msg_ids:
            attach_result = client.table("attachments") \
                .select("id, message_id, kind, filename, mime_type, size_bytes") \
                .in_("message_id", msg_ids) \
                .execute()
            for row in attach_result.data or []:
                attachments_by_message.setdefault(row["message_id"], []).append(
                    AttachmentOut(
                        id=row["id"],
                        kind=row["kind"],
                        filename=row["filename"],
                        mime_type=row["mime_type"],
                        size_bytes=row["size_bytes"],
                    )
                )

        messages = [
            MessageOut(
                role=msg["role"],
                content=msg["content"],
                sources=msg.get("sources", []),
                attachments=attachments_by_message.get(msg["id"], []),
                created_at=msg["created_at"],
            )
            for msg in msg_result.data
        ]

        return _project_from_row(conv_result.data, messages)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{conversation_id}", response_model=ProjectOut)
async def update_project(
    conversation_id: str,
    req: UpdateProjectRequest,
    user=Depends(get_current_user),
):
    """Update any project fields."""
    client = get_user_supabase(user["token"])
    updates = {}
    for field in ["title", "pinned", "address", "municipio", "building_type",
                   "main_materials", "estimated_budget", "ordenanza"]:
        val = getattr(req, field, None)
        if val is not None:
            updates[field] = val

    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")

    try:
        result = client.table("conversations") \
            .update(updates) \
            .eq("id", conversation_id) \
            .eq("user_id", user["id"]) \
            .execute()

        return _project_from_row(result.data[0])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{conversation_id}")
async def delete_project(conversation_id: str, user=Depends(get_current_user)):
    """Delete a project and its messages."""
    client = get_user_supabase(user["token"])
    try:
        client.table("messages") \
            .delete() \
            .eq("conversation_id", conversation_id) \
            .execute()

        client.table("conversations") \
            .delete() \
            .eq("id", conversation_id) \
            .eq("user_id", user["id"]) \
            .execute()

        return {"status": "deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
