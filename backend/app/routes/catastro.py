import json
from fastapi import APIRouter, Depends, HTTPException
from app.auth import get_current_user, get_user_supabase
from app.services.catastro import lookup_by_ref

router = APIRouter(prefix="/catastro", tags=["catastro"])


@router.get("/lookup")
async def catastro_lookup(
    ref_catastral: str,
    user=Depends(get_current_user),
):
    """Look up a property by its referencia catastral."""
    if not ref_catastral.strip() or len(ref_catastral.strip()) < 14:
        raise HTTPException(status_code=400, detail="Se requiere una referencia catastral de al menos 14 caracteres.")
    return await lookup_by_ref(ref_catastral)


@router.post("/lookup-and-save/{project_id}")
async def catastro_lookup_and_save(
    project_id: str,
    user=Depends(get_current_user),
):
    """Fetch catastro data for a project's ref catastral and save it."""
    client = get_user_supabase(user["token"])

    try:
        proj = (
            client.table("conversations")
            .select("catastro_data")
            .eq("id", project_id)
            .eq("user_id", user["id"])
            .single()
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Proyecto no encontrado: {e}")

    # Get the ref catastral — stored on creation
    ref = ""
    existing = proj.data.get("catastro_data")
    if isinstance(existing, str):
        try:
            existing = json.loads(existing)
        except Exception:
            existing = None
    if isinstance(existing, dict):
        ref = existing.get("ref_catastral_input", "")

    if not ref or len(ref) < 14:
        raise HTTPException(status_code=400, detail="El proyecto no tiene referencia catastral.")

    result = await lookup_by_ref(ref)
    result["ref_catastral_input"] = ref  # preserve the user's original input

    try:
        client.table("conversations").update(
            {"catastro_data": json.dumps(result, ensure_ascii=False)}
        ).eq("id", project_id).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al guardar: {e}")

    return result
