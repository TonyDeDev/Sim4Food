# Report To Fix

Audit of the whole SwarmStock / Sim4Food app against the hackathon goal: a working, pitchable demo of "upload your data, see your waste, get next week's order, and test a deal before you run it".
The XGBoost forecasting layer has its own audit in [xgboost-audit.md](xgboost-audit.md).

## Scope and method

- Every backend (`backend/app`, `backend/sim`), frontend (`src/`) and schema (`db/`) file was read.
- `pytest` in `backend/`: 66 passed.
- `eslint`: 0 errors, 5 warnings (listed under P1).
- `build_forecast_payload` was run offline on the demo CSVs: 0.62 s, forecast week 2026-09-21, P10-P90 coverage 0.683.
- Google / Apple / email-link login is out of hackathon scope and is only listed as "hide for the demo".

Priority legend:

| Priority | Meaning |
|---|---|
| P0 | Breaks the demo, or is an MVP item CLAUDE.md marks as "never cut". |
| P1 | A real bug that gives wrong numbers or a 500, but has a workaround. |
| P2 | Polish and demo hygiene. |

## P0 - demo blockers and missing MVP

### P0-1 The swarm engine does not exist yet

- Where: `backend/sim/agents.py`, `calibrate.py`, `forecast.py`, `optimize.py`, `backtest.py`, `replay.py`.
- What: every function in these modules is a stub that raises `NotImplementedError`.
- Why it matters: the pitch is "multi-agent customer simulation plus Monte Carlo", and none of it has code behind it.
  The only working model is XGBoost.
- Fix: see the recommended build order at the end.
  The fastest honest story is XGBoost for the normal week, and a small vectorized swarm calibrated to it for deals and holidays.

### P0-2 `/api/simulate` and `/api/backtest` return 500

- Where: `backend/app/main.py:81` raises `NotImplementedError` directly, and `main.py:87` calls the stub `backtest.run_backtest`.
- Why it matters: any UI that calls them will show an error mid-demo.
- Fix: implement them, or return a clear 501 JSON body until they exist.

### P0-3 No order recommendation, no savings number, no backtest page

- Where: `forecast_payload.py` stops at usage bands, `optimize.recommend_order` is a stub, and there is no Backtest tab in `src/screens/Dashboard.jsx`.
- Why it matters: CLAUDE.md says "never cut recommendations, savings number, or backtest".
  Today the app forecasts usage but never says "order X".
- Fix:
  - Implement `optimize.recommend_order` on top of the existing XGBoost bands: critical ratio `q* = Cu / (Cu + Co)`, take the usage quantile at `q*`, subtract projected stock on hand, cap by shelf life, round up to `pack_size`.
  - Build the naive-vs-recommended backtest from the rolling backtest output already computed in `forecast_backtest.rolling_backtest`, pricing each week's over-order as waste and under-order as lost margin.
  - Add Recommendations and Backtest views to the Forecast tab.

### P0-4 Deployed app will fail auth on every backend call

- Where: `src/utils/api.js:15-19`, `src/app/api/auth/login/route.ts:28`.
- What: the session cookie is set by the Next.js origin (Vercel).
  The FastAPI backend is on a different host, so the browser will not send that cookie with `credentials: 'include'`.
  It only works locally because both sides are on `localhost`.
- Why it matters: every FastAPI route returns 401 on the deployed demo.
- Fix: proxy FastAPI through Next.js `rewrites` in `next.config.ts` (for example `/py/:path*` to the backend URL), point `API_URL` at the same origin, and set `secure: true` on the cookie in production.

### P0-5 Re-uploading a file duplicates the data

- Where: `backend/app/repository.py:241-338` (sales, purchases, inventory counts), no unique key on those tables in `db/schema.sql:98-131`.
- What: each upload appends rows.
  The "Replace" button in `src/components/RecordUploadCard.jsx:39` suggests the file is replaced, but it is added again.
- Why it matters: one extra click doubles revenue, usage, waste and the forecast.
  Very easy to hit during a live demo.
- Fix: write `upload_batch_id` on every row, and on upload delete the restaurant's existing rows in the uploaded file's date range before inserting (or add unique keys such as `(restaurant_id, menu_item_id, date)` and upsert).

### P0-6 Events cannot be entered

- Where: `backend/sim/ingest.py:12-19` has no `events` type, `src/utils/api.js:6-13` has no events card, and there is no Planner page.
- What: the `events` table is only filled if someone inserts rows by hand.
- Why it matters:
  - The Home "Next event" tile is always "None planned".
  - Every XGBoost event feature is 0, so deals and holidays have no effect on the forecast.
  - The pitch's main differentiator ("what a deal or holiday will do to your stock") has no input.
- Fix: add an `events` upload type (mapping `items` external ids to `menu_items.id` UUIDs, since `events.items` is `UUID[]`) and a small Planner form.

### P0-7 No one-click demo load

- Where: `backend/app/main.py:35` (`/api/demo` only returns the CSVs as JSON).
- What: CLAUDE.md requires "keep the demo dataset loadable in one click", but loading the demo means uploading 6 CSVs in the right order by hand.
- Fix: add `POST /api/demo/seed?restaurant_id=` that feeds `backend/data/demo/*.csv` through `repository.persist_upload` in dependency order (ingredients, menu, recipes, sales, purchases, inventory counts, events), plus a "Load demo restaurant" button on the empty state.

### P0-8 Waste report has no page

- Where: `/api/waste` works (`backend/sim/waste.py`), but the frontend only shows one "Waste cost (last week)" tile.
- What: the MVP waste report (by ingredient, units and dollars, with trend) is not shown anywhere.
- Fix: a Waste tab with a per-ingredient table and a weekly trend chart from the existing endpoint.

### P0-9 What-If is a "Coming soon" stub

- Where: `src/components/WhatIfSimulation.jsx:49-60`.
- What: the slider and holiday toggle only show a "Coming soon" card.
- Fix: wire it to `/api/simulate` once P0-1 exists.
  Until then, hide the tab so the demo does not land on a placeholder.

### P0-10 The forecast is for a week that has already started (or passed)

- Where: `backend/sim/forecast_payload.py:63-77` and `train_dish_xgb.forecast_next_week`.
- What: the forecast always targets the week after the last complete sales week.
  On the demo data that is 2026-09-21, already almost over on 2026-09-27.
  The upcoming deal (Oct 9-11) and holiday (Oct 12) are out of reach.
- Why it matters: the Forecast tab labels it "Next week", and the most compelling demo scenario cannot be shown.
- Fix: anchor the target week to today (the next Monday), and roll the baseline forward for the gap weeks.
  See X5 in the XGBoost audit.

## P1 - bugs

| # | Where | Problem | Fix |
|---|---|---|---|
| P1-1 | `backend/app/repository.py:392-399` | A file with some bad rows is marked `failed`, but the good rows are still committed. The upload card then shows "No file uploaded" while data is partly in, and a retry duplicates it (P0-5). | Raise inside the transaction so the whole file rolls back, or add a `partial` status and show it. |
| P1-2 | `backend/app/repository.py:321` | `inventory_current` only changes on inventory counts. Purchases and sales after the count never move it, so "On hand" and runway on Home are stale. CLAUDE.md says it tracks running stock. | Compute on hand as last count + purchases since - theoretical usage since. |
| P1-3 | `backend/app/repository.py:311` | Uploaded counts are stored with `source='computed'`. | Use `'manual'` for uploaded counts. |
| P1-4 | `backend/app/main.py:47` | Upload decodes as UTF-8 only. A CSV saved from Excel in cp1252 raises and returns 500. No file size limit. | Try UTF-8, fall back to cp1252, return a validation error on failure. Cap the upload size. |
| P1-5 | `backend/sim/ingest.py:81` | A missing or misspelled header gives one "missing required value" error per row. Duplicate `(date, item_id)` sales rows are not flagged. | Check headers once before the row loop. Flag duplicate keys for sales, purchases and counts. |
| P1-6 | `backend/sim/forecast_payload.py:117` and `:159` | `POST /api/forecast` returns 500 when there are sales but no recipes (`iloc[0]` on an empty forecast), and when there is less than one complete week (`weeks[0]` on an empty list). | Return the `weeks_of_history: 0` payload with a message in both cases. |
| P1-7 | `src/components/BusinessDetailsPanel.jsx:22` | Editing a business only updates React state. There is no PATCH route, so the change is gone after reload. | Add `PATCH /api/restaurants/[id]` in Next.js and call it. |
| P1-8 | `backend/sim/waste.py:101` | Waste is clipped at 0, which hides negative variance (count errors, unrecorded usage). With no counts, the fallback treats any stock build-up as waste. | Report negative variance as "unexplained shortfall". Label weeks without counts as estimated. |
| P1-9 | `backend/sim/home_summary.py:154-155` | `compute_waste` and `compute_inventory` each reload consumption, so Home runs the same heavy queries twice per request. | Load consumption once and pass it to both pure builders. |
| P1-10 | `eslint.config.mjs` | ESLint lints `backend/.venv` (3 warnings from scikit-learn's bundled JS). | Add `backend/.venv/**` to `globalIgnores`. |
| P1-11 | `src/screens/Dashboard.jsx:42` | `react-hooks/exhaustive-deps` warning for `onUpdateBusiness`. | Wrap the handler in `useCallback` in `App.jsx` and add it to the dependency list. |
| P1-12 | `src/app/layout.tsx:18` | Google Fonts `<link>` warning. | Load the fonts with `next/font/google`. |

## P2 - polish and demo hygiene

- Login and signup show Google, Apple and email-link buttons, a "Forgot password?" link and a "Stay signed in" checkbox that do nothing (`src/screens/Login.jsx:51`, `:65-73`, `:86-109`).
  Out of scope to build, but hide them for the demo, since a judge clicking a dead button hurts the pitch.
- The UI says "Sim4Food" (`src/app/layout.tsx:7`) while the pitch and API say "SwarmStock".
  Pick one name.
- Home says "add one in the Planner" (`src/components/InventoryOverview.jsx:182`), but no Planner exists.
- The Forecast tab shows "Forecast confidence 68%" (`src/components/ForecastOverview.jsx:80-85`).
  That number is P10-P90 band coverage against an 80% target, not confidence.
  Relabel it "Range hit rate (target 80%)".
- CLAUDE.md says Tailwind v4 and Recharts, while README says plain CSS and no chart library is installed.
  Align the docs with what is actually used.
- `simulation_runs` stores forecast runs with `scenario_params '{}'` (`backend/sim/forecast_store.py:30`).
  Once `/api/simulate` writes to the same table, add a `kind` column so the forecast tab does not read a simulation run.
- For after the hackathon: session tokens are stored in plain text in `sessions`, and login has no rate limit.

## Recommended build order for the remaining hours

1. Same-origin proxy and secure cookie (P0-4), so the deployed demo works at all.
2. Upload idempotency (P0-5, P1-1), events upload (P0-6), and the demo seed button (P0-7).
3. Recommendations, savings and backtest from the XGBoost bands (P0-3), with the target week anchored to today (P0-10).
4. Waste page (P0-8).
5. A minimal vectorized swarm for What-If, calibrated so its normal week matches the XGBoost forecast, with deal price sensitivity and holiday multipliers on top (P0-1, P0-2, P0-9).
   Then the animation, which only replays that output.
6. Remaining P1 bugs, then P2 polish.

## Status on branch snowflake-llm-gen

| # | Status | Notes |
|---|---|---|
| P0-3 | Fixed | Order recommendations, savings and a backtest replay are on the Forecast tab (see [xgboost-forecasting.md](xgboost-forecasting.md)). `/api/backtest` itself is still the simulation team's stub. |
| P0-6 | Fixed | Events upload ("Deals and holidays" card); the Home "Next event" tile now fills. A Planner form is still to do. |
| P0-10 | Fixed | The forecast targets the week after today. |
| P1-6 | Fixed | No recipes or under one full week return a message. |
| P1-10 | Fixed | ESLint ignores `backend/.venv`. |
| P1-11 | Fixed | `handleUpdateBusiness` is a stable callback and listed as a dependency. |
| P1-12 | Fixed | Documented lint exception: the root App Router layout loads the fonts for every page. |
| P2 | Partly fixed | "Forecast confidence" is now "Range hit rate"; the Home tile no longer points to a missing Planner; tab buttons lost their browser-default borders; the sidebar email truncates. |
| New | Added | Snowflake Cortex order summary and chat, see [snowflake-cortex.md](snowflake-cortex.md). |

Not touched here (owned by the simulation work or out of this branch's scope): P0-1, P0-2, P0-4, P0-5, P0-7, P0-8, P0-9 and the other P1 items.
