from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.auth import get_current_user, get_user_supabase
from app.services.files import decode_bytea

router = APIRouter(prefix="/attachments", tags=["attachments"])


@router.get("/{attachment_id}")
async def download_attachment(
    attachment_id: str,
    user=Depends(get_current_user),
):
    """
    Return an attachment as a raw file download. RLS guarantees the
    caller can only read their own attachments.
    """
    client = get_user_supabase(user["token"])
    try:
        result = (
            client.table("attachments")
            .select("filename, mime_type, data")
            .eq("id", attachment_id)
            .single()
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Attachment not found: {e}")

    row = result.data
    if not row:
        raise HTTPException(status_code=404, detail="Attachment not found")

    try:
        file_bytes = decode_bytea(row["data"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not decode file: {e}")

    filename = row["filename"]
    mime_type = row["mime_type"]

    return Response(
        content=file_bytes,
        media_type=mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(file_bytes)),
        },
    )
