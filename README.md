# SwarmStock

Helps independent restaurants cut food waste: upload your sales and invoices, see what you're wasting, and get a next-week order recommendation per ingredient. See `CLAUDE.md` for the full pitch, data model, and API contract.

## Stack

- **Frontend:** Next.js (App Router) + React, plain CSS design system (no Tailwind despite what older docs may say) - `src/`
- **Backend:** Python/FastAPI, XGBoost forecasting, Postgres via `asyncpg` - `backend/`
- **Database:** one shared Neon Postgres instance for the whole team (not local Postgres, no Docker needed)

## Prerequisites

- **Node.js 20+** (a recent LTS). This project pins Next.js 16, which is unusually new - an older Node can fail to run it.
- **Python 3.11+**
- **Git**

No Docker, no native build toolchain (no Visual Studio Build Tools / `node-gyp`) - password hashing uses Node's built-in `crypto`, and the Python dependencies all ship prebuilt wheels.

## First-time setup

1. Clone the repo.
2. **Frontend deps:** `npm install` in the repo root.
3. **Backend deps** (from the repo root):
   ```
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r backend\requirements.txt -r backend\requirements-dev.txt
   ```
4. **Environment files** - copy `.env.example` → `.env` (repo root) and `backend/.env.example` → `backend/.env`. Both need the same Neon `POSTGRES_URL`. **This is a real secret and is gitignored** - ask a teammate for it, do not commit it.
5. Everyone points at the same shared Neon database, so no schema setup is needed on your end - it already exists. If you and a teammate are both testing at once, you'll see each other's test data (same shared DB).

## Running it (two terminals, both from the repo root)

**Frontend:**
```
npm run dev
```
Opens on `http://localhost:3000`.

**Backend** (from `backend/`, venv activated):
```
cd backend
$env:PYTHONPATH = "."   # PowerShell; use `export PYTHONPATH=.` on macOS/Linux
python -m uvicorn app.main:app --reload --port 8000
```
Serves on `http://localhost:8000`.

Leave both terminals open while developing - closing either one kills that server, and `net::ERR_CONNECTION_REFUSED` in the browser almost always means the backend terminal got closed.

`--reload` needs `PYTHONPATH=.` set on Windows, or its auto-restart subprocess fails with `ModuleNotFoundError: No module named 'app'` (a Windows + `multiprocessing` spawn quirk). It also runs as two OS processes (a supervisor and a worker) - stop it with Ctrl+C in its terminal, not by force-killing one PID, or the other can be left holding the port.

## Tests

```
cd backend
python -m pytest
```

## Learn More (Next.js defaults)

- [Next.js Documentation](https://nextjs.org/docs)
- [Learn Next.js](https://nextjs.org/learn)
