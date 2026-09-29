# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# SwarmStock (working name)

24-hour hackathon project, 2-person team.
Helps independent restaurants cut food waste by recommending how much of each ingredient to order, using a multi-agent customer simulation plus Monte Carlo.

**Pitch:** Upload your sales and invoices.
We show what you're wasting, what to order next week, and what a deal or holiday will do to your stock before you run it.

## Commands

Run everything from the repo root unless noted.
Two servers are needed for the full app: Next.js on :3000 and FastAPI on :8000.

```
npm install
npm run dev            # frontend, http://localhost:3000
npm run build
npm run lint           # eslint (no frontend test runner exists)

# backend (venv: python -m venv .venv; pip install -r backend/requirements.txt -r backend/requirements-dev.txt)
cd backend
$env:PYTHONPATH = "."  # PowerShell; required on Windows for --reload
python -m uvicorn app.main:app --reload --port 8000
python -m pytest                              # all backend tests
python -m pytest tests/test_ingest.py -k name # single file / test
```

Setup details live in `README.md`.
Copy `.env.example` to `.env` and `backend/.env.example` to `backend/.env`.
Both need the same Neon `POSTGRES_URL` (gitignored, never commit it).

## Architecture

**Same-origin proxy.**
The browser only talks to `/py/*`.
`next.config.ts` rewrites that to `BACKEND_URL` (FastAPI) server-to-server, so the httpOnly `session` cookie reaches the backend everywhere.
Frontend code uses `API_URL = '/py'` from `src/utils/api.js`.
Next.js `src/app/api/*` handles only auth (`login`, `signup`, `logout`, `session`), `restaurants`, and health checks.

**Auth.**
Opaque session token in a `sessions` table in the shared Postgres.
Next.js creates it (`src/lib/session.ts`, `src/lib/password.ts` using Node `crypto`).
FastAPI validates it with one query (`backend/app/auth.py`: `get_current_user_id`, `verify_restaurant_owner`).
No JWTs.

**Frontend is a client-side SPA inside Next.**
`src/app/page.tsx` renders `src/App.jsx` (plain JSX, plain CSS, no Tailwind, no charting library).
Screens are in `src/screens/`, widgets in `src/components/`.
The animation is split into `SimView.jsx`, `simViewEngine.js`, `simViewDraw.js`, and `pixelFont.js`, and only replays backend output.
`DESIGN.md` is the style reference for the UI.

**Backend (`backend/`).**
`app/` is the web layer: `main.py` routes, `repository.py` and `db.py` (asyncpg pool), `insights.py` and `cortex.py` (LLM chat via Snowflake Cortex, see `docs/snowflake-cortex.md`), `guardrails.py`, `page_context.py`.
`sim/` is the engine, imported by `app/main.py` as the top-level `sim` package, so the working directory must be `backend/`.
Data flow: `ingest` validates uploads, then `dataset.load_frames` builds pandas frames, then `waste`, `inventory`, `features`, `forecast` (XGBoost, models in `backend/models/`), `uncertainty`, `optimize` (newsvendor), `recommend`, `backtest`, `replay`.
`forecast_store`, `forecast_payload`, and `home_summary` persist and shape results for the API.
Training scripts: `train_xgb.py`, `train_dish_xgb.py`.
See `docs/xgboost-forecasting.md`, `docs/internal/xgboost-audit.md` and `docs/forecast-values.md` for forecasting decisions.

**Actual forecasting differs from the original swarm-only plan.**
XGBoost models are used alongside the rule-based agent simulation (`agents.py`, `calibrate.py`).
Check the docs before assuming which path a given endpoint uses.

**Database.**
`db/schema.sql` plus `db/migrations/`.
Rows are versioned (see `001_versioned_rows.sql` and `backend/tests/test_repository_changes.py`).

**Deployment.**
Frontend on Vercel, backend on Render (`render.yaml`, rootDir `backend`, health check `/openapi.json`, Python 3.12).
The backend has no `/api/health`, only the Next.js side does.

## API (FastAPI, via `/py`)

`GET /api/demo`, `POST /api/upload`, `GET /api/uploads`, `GET /api/waste`, `GET /api/inventory`, `GET /api/menu`, `GET /api/home-summary`, `POST /api/simulate`, `GET /api/backtest`, `GET|POST /api/forecast`, plus the router in `app/insights.py`.
`backend/app/main.py` is the source of truth.

## Data files

| File | Columns |
|---|---|
| `ingredients.csv` | ingredient_id, name, unit, unit_cost, pack_size, shelf_life_days |
| `menu.csv` | item_id, name, price, category |
| `recipes.csv` | item_id, ingredient_id, qty_per_serving |
| `sales.csv` | date, item_id, qty_sold, avg_price |
| `purchases.csv` | date, ingredient_id, qty, unit_cost, total |
| `inventory_counts.csv` (optional) | date, ingredient_id, qty_on_hand |
| `events.csv` | start_date, end_date, type (holiday/deal), name, items, discount_pct, expected_lift |
| `customer_profile.json` (optional) | daily_customers_estimate, busy_days, segments[name, share, price_sensitivity, likes] |
| `true_demand.csv` (hidden, demo only) | date, item_id, demand |

Demo dataset: `backend/data/demo/` and `data/restaurant_demo_data.xlsx`.
1 restaurant, 12 weeks, one past holiday and one past deal, naive owner ordering rule ("last week's usage x 1.25", rounded to pack size).
Last 2 weeks held out for backtest.

## Model summary

- **Waste** is calculated, not entered: `start stock + purchases - end stock - (dishes sold x recipe qty)`.
- **Agents:** segment, price sensitivity, category preferences, budget, friends.
- **Visit decision:** base rate x weekday x holiday x deal x social factor.
- **Dish choice:** softmax over `preference - price_sensitivity * price + deal_bonus`.
- **Stockout:** agent takes next choice or leaves; record lost sale.
- **Newsvendor:** order at demand percentile `Cu / (Cu + Co)`; Cu = lost margin per unit short, Co = cost per unit wasted.
- The swarm's advantage over plain forecasting is handling situations with no history (new deals, holidays, word of mouth).

## Conventions

- Rule-based agents only; never one LLM call per agent.
- Vectorize with NumPy. Full `/api/simulate` must finish in under 10 seconds.
- Fixed random seeds for reproducible demos.
- Money rounded to 2 decimals; quantities in the ingredient's unit.
- Animation only replays simulation output; it never affects results.
- Keep the demo dataset loadable in one click.
- LLM output must not contain em or en dashes (see `EM_DASH` handling in `app/cortex.py`).
- Out of scope: multiple locations, live POS integration, supplier ordering.

## Environment variables

- `POSTGRES_URL`: Neon connection string, used by both Next.js and FastAPI.
  Backend falls back to discrete `POSTGRES_*` vars when unset (`backend/app/config.py`).
- `BACKEND_URL`: read only by `next.config.ts`; also set in Vercel.
- `CORS_ORIGINS`: backend only, local-dev convenience.
- `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_PAT`, `CORTEX_MODEL`: backend LLM chat.

# This is NOT the Next.js you know

This version has breaking changes - APIs, conventions, and file structure may all differ from your training data.
Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code.
Heed deprecation notices.

This block is written and re-added by `next dev` - verify at `node_modules/next/dist/server/lib/generate-agent-files.js`.
Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
