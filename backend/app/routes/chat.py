import json
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.auth import get_current_user, get_user_supabase
from app.models import AttachmentOut, ChatResponse
from app.services.ai import AIService
from app.services.files import (
    ALLOWED_MIME_TYPES,
    MAX_FILE_BYTES,
    MAX_FILES_PER_MESSAGE,
    build_claude_content_blocks,
    decode_bytea,
    encode_bytes_for_bytea,
)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/")
async def send_message(
    message: str = Form(...),
    conversation_id: Optional[str] = Form(None),
    files: List[UploadFile] = File(default_factory=list),
    stream: bool = Form(False),
    user=Depends(get_current_user),
):
    """
    Send a message (and optionally attached files) to Claude. If the
    assistant calls the `create_document` tool, the generated document
    is persisted and returned as a downloadable attachment.
    """
    client = get_user_supabase(user["token"])

    # ── Validate attachments ─────────────────────────────────────
    if len(files) > MAX_FILES_PER_MESSAGE:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_FILES_PER_MESSAGE} files per message.",
        )

    file_payloads: list[tuple[str, str, bytes]] = []
    for f in files:
        if not f or not f.filename:
            continue
        raw = await f.read()
        if len(raw) > MAX_FILE_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"File '{f.filename}' exceeds the {MAX_FILE_BYTES // (1024*1024)} MB limit.",
            )
        mime = (f.content_type or "").lower()
        if mime not in ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"File type '{mime or 'unknown'}' for '{f.filename}' is "
                    "not supported. Allowed: PDF, TXT, MD, PNG, JPG."
                ),
            )
        file_payloads.append((f.filename, mime, raw))

    try:
        # ── Require an existing project ─────────────────────────
        if not conversation_id:
            raise HTTPException(
                status_code=400,
                detail="conversation_id is required. Create a project first.",
            )

        conv_result = (
            client.table("conversations")
            .select("*")
            .eq("id", conversation_id)
            .eq("user_id", user["id"])
            .single()
            .execute()
        )
        conversation_id = conv_result.data["id"]

        # Extract project metadata for the system prompt
        import json as _json
        raw_catastro = conv_result.data.get("catastro_data")
        catastro_parsed = None
        if raw_catastro:
            if isinstance(raw_catastro, dict):
                catastro_parsed = raw_catastro
            elif isinstance(raw_catastro, str):
                try:
                    catastro_parsed = _json.loads(raw_catastro)
                except Exception:
                    pass

        project_metadata = {
            "address": conv_result.data.get("address"),
            "municipio": conv_result.data.get("municipio"),
            "building_type": conv_result.data.get("building_type"),
            "main_materials": conv_result.data.get("main_materials", []),
            "estimated_budget": conv_result.data.get("estimated_budget"),
            "ordenanza": conv_result.data.get("ordenanza"),
            "catastro_data": catastro_parsed,
        }

        # ── Save the user's message first so we can attach files ──
        user_msg_insert = (
            client.table("messages")
            .insert(
                {
                    "conversation_id": conversation_id,
                    "role": "user",
                    "content": message,
                    "sources": [],
                }
            )
            .execute()
        )
        user_message_id = user_msg_insert.data[0]["id"]

        # Create the AI service early so we can reuse it for attachment
        # uploads to Anthropic's Files API (so they get a file_id on save
        # and every future turn can reference them cheaply).
        ai_service = AIService(client)

        # Persist user-side attachments (input files). For each one that
        # the Files API supports (PDFs + images), we also upload to
        # Anthropic and store the returned file_id. We run the Supabase
        # insert + Anthropic upload concurrently — both average ~0.5-1.5s
        # and they're independent.
        import asyncio as _asyncio

        async def _persist_and_upload(
            filename: str, mime: str, raw: bytes
        ) -> tuple[dict, Optional[str]]:
            insert_coro = _asyncio.to_thread(
                lambda: client.table("attachments")
                .insert({
                    "message_id": user_message_id,
                    "user_id": user["id"],
                    "kind": "input",
                    "filename": filename,
                    "mime_type": mime,
                    "size_bytes": len(raw),
                    "data": encode_bytes_for_bytea(raw),
                })
                .execute()
            )
            upload_coro = ai_service.upload_attachment(filename, mime, raw)
            ins_result, file_id = await _asyncio.gather(insert_coro, upload_coro)
            attachment_row = ins_result.data[0]
            # Patch the row with the Anthropic file_id (if we got one)
            # so subsequent turns find it via the history select below.
            if file_id:
                await _asyncio.to_thread(
                    lambda: client.table("attachments")
                    .update({"anthropic_file_id": file_id})
                    .eq("id", attachment_row["id"])
                    .execute()
                )
            return attachment_row, file_id

        input_attachment_rows: list[AttachmentOut] = []
        # Parallel file_ids list mirrors file_payloads order — passed into
        # build_claude_content_blocks below so the CURRENT turn references
        # uploads by file_id.
        current_turn_file_ids: list[Optional[str]] = []
        if file_payloads:
            results = await _asyncio.gather(*(
                _persist_and_upload(fn, mm, rw) for fn, mm, rw in file_payloads
            ))
            for row, file_id in results:
                current_turn_file_ids.append(file_id)
                input_attachment_rows.append(
                    AttachmentOut(
                        id=row["id"],
                        kind="input",
                        filename=row["filename"],
                        mime_type=row["mime_type"],
                        size_bytes=row["size_bytes"],
                    )
                )

        # ── Gather conversation history ─────────────────────────
        #
        # IMPORTANT: Claude has no memory between requests — the only
        # thing it "remembers" about earlier attachments is what we put
        # into the `messages` array on THIS request. That means we have
        # to rebuild every prior user turn the same way we build the
        # current one: fetch the attachment bytes back out of the DB
        # and stitch them into the user content as image / text blocks.
        # Otherwise Claude will say things like "I don't have access to
        # previous files" on the second turn.
        msg_result = (
            client.table("messages")
            .select("id, role, content, created_at")
            .eq("conversation_id", conversation_id)
            .order("created_at")
            .execute()
        )
        # Drop the user message we JUST inserted — its content will be
        # passed separately below using the freshly-uploaded file_payloads.
        history_rows = msg_result.data[:-1]
        history_msg_ids = [m["id"] for m in history_rows]

        # Fetch all INPUT attachments for every historical message in
        # one query. We pull `anthropic_file_id` too so we can reference
        # uploads by id on follow-up turns (saves ~15-25k input tokens
        # per PDF + the ~3-8s base64 re-encode cost).
        attachments_by_msg: dict[
            str, list[tuple[str, str, bytes, Optional[str]]]
        ] = {}
        if history_msg_ids:
            att_rows = (
                client.table("attachments")
                .select(
                    "message_id, filename, mime_type, data, anthropic_file_id"
                )
                .in_("message_id", history_msg_ids)
                .eq("kind", "input")
                .execute()
            )
            for row in att_rows.data or []:
                # If we already have a file_id for this attachment, we
                # don't need to decode the bytea at all — Claude will
                # reference it by id. Saves the decode on every turn.
                file_id = row.get("anthropic_file_id")
                if file_id:
                    raw = b""  # placeholder — not sent to Claude
                else:
                    try:
                        raw = decode_bytea(row["data"])
                    except Exception:
                        continue
                attachments_by_msg.setdefault(row["message_id"], []).append(
                    (row["filename"], row["mime_type"], raw, file_id)
                )

        history: list[dict] = []
        for m in history_rows:
            if m["role"] == "user":
                msg_files = attachments_by_msg.get(m["id"], [])
                if msg_files:
                    # Rebuild the same image/text block shape Claude saw
                    # on the turn that originally uploaded these files —
                    # referencing by file_id where available.
                    files_only = [(fn, mm, rw) for fn, mm, rw, _ in msg_files]
                    ids_only = [fid for _, _, _, fid in msg_files]
                    history.append(
                        {
                            "role": "user",
                            "content": build_claude_content_blocks(
                                m["content"], files_only, file_ids=ids_only,
                            ),
                        }
                    )
                else:
                    history.append({"role": "user", "content": m["content"]})
            else:
                # Assistant messages never carry input attachments; their
                # generated-document outputs are not re-fed to Claude.
                history.append({"role": "assistant", "content": m["content"]})

        # ── Get user profile for personalisation ────────────────
        profile_result = (
            client.table("profiles")
            .select("*")
            .eq("id", user["id"])
            .single()
            .execute()
        )
        user_profile = profile_result.data

        # ── Build Claude content blocks (text + files) ──────────
        # current_turn_file_ids was populated above during the parallel
        # Supabase insert + Anthropic upload.
        content_blocks = build_claude_content_blocks(
            message, file_payloads, file_ids=current_turn_file_ids,
        )

        # ── Helper: save assistant message + any generated documents
        # Runs once the model's final turn is in hand. Accepts a
        # chat_stream "final" event OR the dict from chat().
        async def _persist_assistant_output(result: dict) -> tuple[str, list[AttachmentOut]]:
            assistant_text = (result.get("response") or "").strip()
            if not assistant_text:
                if result.get("documents"):
                    assistant_text = "(Generated a document — see attachment below.)"
                else:
                    assistant_text = "(No response.)"

            assistant_msg_insert = (
                client.table("messages")
                .insert(
                    {
                        "conversation_id": conversation_id,
                        "role": "assistant",
                        "content": assistant_text,
                        "sources": result.get("sources", []),
                    }
                )
                .execute()
            )
            assistant_message_id = assistant_msg_insert.data[0]["id"]

            generated_attachment_rows: list[AttachmentOut] = []
            for doc in result.get("documents", []):
                ins = (
                    client.table("attachments")
                    .insert(
                        {
                            "message_id": assistant_message_id,
                            "user_id": user["id"],
                            "kind": "generated",
                            "filename": doc["filename"],
                            "mime_type": doc["mime_type"],
                            "size_bytes": doc["size_bytes"],
                            "data": encode_bytes_for_bytea(doc["data"]),
                        }
                    )
                    .execute()
                )
                row = ins.data[0]
                generated_attachment_rows.append(
                    AttachmentOut(
                        id=row["id"],
                        kind="generated",
                        filename=row["filename"],
                        mime_type=row["mime_type"],
                        size_bytes=row["size_bytes"],
                    )
                )
            return assistant_text, generated_attachment_rows

        # ── Streaming path: SSE with text_delta + tool_call + done events
        if stream:
            async def sse_gen():
                try:
                    async for event in ai_service.chat_stream(
                        message=content_blocks,
                        conversation_history=history,
                        user_profile=user_profile,
                        project_metadata=project_metadata,
                    ):
                        etype = event.get("type")
                        if etype == "final":
                            # Save to DB first so the "done" event can
                            # carry the persisted attachment rows + the
                            # real assistant message text.
                            assistant_text, generated_rows = (
                                await _persist_assistant_output(event)
                            )
                            done_payload = {
                                "type": "done",
                                "conversation_id": conversation_id,
                                "response": assistant_text,
                                "sources": event.get("sources", []),
                                "tools_used": event.get("tools_used", []),
                                "attachments": [
                                    r.model_dump() for r in generated_rows
                                ],
                            }
                            yield (
                                "data: "
                                + json.dumps(done_payload, ensure_ascii=False)
                                + "\n\n"
                            )
                        else:
                            yield (
                                "data: "
                                + json.dumps(event, ensure_ascii=False)
                                + "\n\n"
                            )
                except Exception as e:
                    yield (
                        "data: "
                        + json.dumps({"type": "error", "message": str(e)})
                        + "\n\n"
                    )

            return StreamingResponse(
                sse_gen(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache, no-transform",
                    "X-Accel-Buffering": "no",  # nginx: don't buffer SSE
                },
            )

        # ── Non-streaming path (legacy): return ChatResponse JSON
        result = await ai_service.chat(
            message=content_blocks,
            conversation_history=history,
            user_profile=user_profile,
            project_metadata=project_metadata,
        )
        assistant_text, generated_attachment_rows = (
            await _persist_assistant_output(result)
        )
        return ChatResponse(
            response=assistant_text,
            conversation_id=conversation_id,
            sources=result.get("sources", []),
            attachments=generated_attachment_rows,
            tools_used=result.get("tools_used", []),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
