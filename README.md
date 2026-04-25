# Mies

Asistente de arquitectura con IA. PGOU, CTE, LOE, BCCA y Catastro en una
sola conversación.

```
├── frontend/         Next.js 16 (App Router) + React 19 + Tailwind v4
├── backend/          FastAPI + async httpx + Anthropic + OpenAI
├── migrations/       SQL files you run once in Supabase's SQL editor
└── README.md         this file
```

## Stack

- **Frontend**: Next.js 16 (App Router), React 19, TypeScript, Tailwind v4,
  Lucide icons. Ships as a `standalone` server (≈200 MB Docker image).
- **Backend**: FastAPI + `AsyncAnthropic` + `AsyncOpenAI` + async httpx.
  Streams chat via Server-Sent Events. Uses Tesseract locally for OCR
  on scanned PDFs.
- **Database**: Supabase (Postgres 17) with `pgvector` (HNSW indexes)
  and Spanish full-text `tsvector` columns. 14 per-corpus tables: 12
  municipal PGOU tables + CTE + LOE.
- **RAG**: per-corpus `match_*` RPCs, strict municipio routing, Anthropic
  prompt caching on the stable system prefix.

---

## Deploying to Railway

> We deploy the two services into one Railway project, sharing the repo
> but each pointing at its own subdirectory as "root". Supabase stays
> where it is — it's already hosted.

### 0. Prereqs (one time)

- GitHub repo with this code pushed (private or public, your call).
- A Railway account with at least the **Developer** plan ($5/mo).
- A Supabase project already set up with migrations `001` through `004`
  run. Confirm with:
  ```sql
  select count(*) from information_schema.tables
   where table_schema = 'public' and table_name like 'pgou_%';
  -- expected: 12
  ```

### 1. Pre-flight cleanup

A couple of stale artefacts sit in the repo from earlier iterations —
remove them before the first commit so they don't end up on GitHub:

```bash
# Stale top-level requirements (the real one lives in backend/requirements.txt)
rm -f requirements.txt

# Empty experiment folder with its own .git — confuses `git add .`
rm -rf mies/
```

### 2. Push to GitHub

From the repo root:

```bash
git init
git add .
git commit -m "Initial commit — Mies"
git remote add origin git@github.com:<you>/mies.git
git push -u origin main
```

The root `.gitignore` already excludes `.env`, `venv/`, `node_modules/`,
`.next/`, `.DS_Store`, etc. Double-check that **no `.env` file** is in
the commit before pushing:

```bash
git ls-files | grep -E "\.env$" && echo "⚠️ .env is tracked — untrack it" || echo "clean"
```

### 3. Railway project + two services

1. On **railway.app**, create a new project → **Deploy from GitHub repo**.
   Pick your Mies repo.
2. Railway will offer to auto-detect services. Cancel that — we configure
   them explicitly.
3. **Add Service** → **GitHub Repo** → same repo. Name it `backend`.
   - Settings → **Root Directory**: `/backend`
   - Settings → **Watch Paths**: `/backend/**`
4. **Add Service** again → same repo. Name it `frontend`.
   - Settings → **Root Directory**: `/frontend`
   - Settings → **Watch Paths**: `/frontend/**`

Both services auto-detect `railway.toml` + `Dockerfile` in their root
directories and use those instead of the default Nixpacks builder. No
manual build command needed.

### 4. Environment variables

In each service, open **Variables** and set:

#### `backend` service

```
SUPABASE_URL=https://<your-ref>.supabase.co
SUPABASE_KEY=<supabase anon key>
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
FRONTEND_URL=${{frontend.RAILWAY_PUBLIC_DOMAIN}}
```

The `${{frontend.RAILWAY_PUBLIC_DOMAIN}}` syntax is a Railway
variable-reference — it resolves to the frontend service's public
domain (e.g. `mies-frontend-production.up.railway.app`) and updates
automatically if you rename. The backend's FastAPI CORS middleware
then whitelists exactly that origin.

> **Gotcha**: Railway's `RAILWAY_PUBLIC_DOMAIN` is the bare host
> (no protocol). FastAPI CORS wants a full URL. If CORS fails on
> first deploy, change `FRONTEND_URL` to `https://${{frontend.RAILWAY_PUBLIC_DOMAIN}}`.

#### `frontend` service

```
NEXT_PUBLIC_API_URL=https://${{backend.RAILWAY_PUBLIC_DOMAIN}}/api
```

`NEXT_PUBLIC_*` values are baked into the client bundle at **build**
time, not runtime — `frontend/railway.toml` declares this value as a
`buildArg` so Railway passes it to the Docker build stage. Any time
you change it, Railway has to rebuild the frontend image.

### 5. Trigger the first deploy

Push any commit (or click "Deploy" in the Railway UI). The first build
takes 3-5 minutes on the backend (Tesseract + Python deps) and 2-3
minutes on the frontend (Next build).

When both services go green:

- **Backend** should answer `GET /` with `{"status": "ok"}`.
- **Frontend** should render the landing page; check the Network tab
  and confirm requests to `/api/*` hit the backend's `RAILWAY_PUBLIC_DOMAIN`.

### 6. Custom domain (optional)

Railway → service → **Settings** → **Domains** → add. Works with any
DNS provider; Railway issues a Let's Encrypt cert automatically.

If you add a custom domain to the frontend, remember to update the
backend's `FRONTEND_URL` to match, otherwise CORS blocks the browser.

---

## What does NOT run on Railway

- **Indexing scripts** (`backend/scripts/index_*.py`) — run these
  locally against production Supabase. They consume ~300 MB of RAM
  during OCR and hit OpenAI embeddings heavily; Railway isn't a good
  place for one-shot batch jobs.
- **Tesseract language packs** other than Spanish — the Dockerfile
  installs `tesseract-ocr-spa`. If you add Catalan / English corpora
  later, add the matching `tesseract-ocr-<lang>` line.

---

## Local development

### Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Copy and fill in real values
cp .env.example .env

# Spanish Tesseract is needed for OCR fallback
brew install tesseract tesseract-lang

uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install

cp .env.example .env.local
# NEXT_PUBLIC_API_URL=http://localhost:8000/api

npm run dev
```

---

## Architecture notes

- **Streaming**: chat POSTs to `/api/chat/` with `stream=true` and
  reads the SSE response in `lib/api.ts::sendMessageStream`. The
  backend yields `text_delta`, `tool_call`, and `done` events.
- **Prompt caching**: system prompt is split into a stable prefix
  (cache-controlled) and a volatile tail (project/user context) so
  mutations don't invalidate the cache.
- **Files API**: user-attached PDFs/images upload to Anthropic on
  first message turn and reuse `file_id` on every follow-up. Saves
  15-25k input tokens per attachment per turn.
- **Strict municipio routing**: `search_normativa` only searches the
  PGOU table of the project's municipio. If the municipio isn't
  covered, the search returns zero and Claude tells the user
  explicitly — no mixing ordenanzas across towns.

---

## Costs (realistic, low traffic)

- Railway: ~$10-20/month (Developer plan base + 2 always-on services)
- Supabase: $0 (free tier until ~500 MB DB / 50 k MAU)
- OpenAI embeddings: ~$0.03 per full re-index of all 14 tables
- Anthropic chat: usage-based, depends on user load

---

## Running migrations

All SQL migrations live in `backend/migrations/` and are numbered.
Run them in order in the Supabase SQL editor. They're idempotent
(`create if not exists`, `drop policy if exists`, etc.) so re-running
is safe.

```
001_split_documents.sql          — original per-corpus table split
002_attachments_anthropic_file_id — Files API column
003_more_pgou_plus_loe            — 6 PGOUs + LOE
004_more_pgou                     — 4 more PGOUs (Rincón, Vélez, Antequera, Alhaurín)
```
