# 45Labs backend

FastAPI + Supabase + Anthropic Claude Sonnet 4.5.

## Running in development

```bash
cd backend
source venv/bin/activate
./venv/bin/uvicorn main:app --port 8000 --log-level info --reload
```

## Running in production (recommended)

Use multiple workers so concurrent chats don't queue behind each other.
With the async refactor, each worker is non-blocking within itself
(every I/O in the chat pipeline is `async` / `await`), but each worker
process is still a single event loop — CPU-bound work (`json.loads`,
tokenisation, XML parsing for Catastro responses) blocks it while it
runs.

Rule of thumb: **one worker per CPU core**, capped at 4–8 for a
mid-sized deploy. More workers won't hurt; fewer means chat requests
serialize during heavy turns.

```bash
./venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

If you're deploying behind a systemd unit, nginx, or a PaaS runner,
wire the worker count through that layer instead of baking it into the
command.

## Latency profile (after the 2026-04 refactor)

| Operation                       | Before  | After     |
| ------------------------------- | ------- | --------- |
| Catastro WFS lookup (4 calls)   | 8–20 s  | 2–5 s     |
| `search_normativa` (both corpora) | 1–2 s | 300–500 ms |
| Attached PDF on turn 2          | 3–8 s   | ~0 s (file_id) |
| First token visible to user     | 20–40 s | **1–3 s** |

Everything routes through the streaming endpoint (`POST /chat/` with
`stream=true`) which emits Server-Sent Events. The non-streaming
response shape is still returned by the same endpoint when `stream`
isn't set, so legacy clients keep working.
