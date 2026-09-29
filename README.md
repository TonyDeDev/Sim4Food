# Sim4Food

Helps independent restaurants cut food waste.
Upload your sales and purchase records, see what you are wasting, and get a next-week order recommendation per ingredient.
A what-if view shows what a deal or holiday will do to your stock before you run it.

- **Live app:** https://sim4food.vercel.app
- **Devpost:** https://devpost.com/software/sim4food

## Inspiration

Food waste is a huge problem in Fredericton, New Brunswick.
With restaurant owners having an 83% chance to shut down within the first year, anything that helps them save on costs gives them an advantage in today's cutthroat market.

## What it does

Our web application helps business owners cut food waste costs with prediction technology that combines XGBoost forecasting with Monte Carlo simulation and agent-based modeling.
The simulation creates customers with their own generated personalities that interact with the chosen restaurant.
Users can see how different events affect inventory, the foods bought, and a person's willingness to eat at the establishment.
Owners can then analyze the results and adjust operations to optimize performance.

1. **Bring the data you already have:** ingredients, menu, recipes, POS sales, supplier purchases, and optional stock counts.
2. **See your waste:** waste is calculated from stock, purchases and sales, not entered by hand.
   It is shown weekly, in units and dollars, by ingredient.
3. **Get next week's order:** a forecast with a P10 to P90 range gives an order quantity per ingredient, adjusted for stock on hand, shelf life and pack size.
4. **Test a deal or holiday:** the What If tab re-runs the simulation for a discount or holiday before you commit.
5. **Ask questions:** an optional AI assistant, built on Snowflake Cortex, explains the forecast and your records in plain English.

## Challenges we ran into

We wanted agent-based modeling to simulate customer behavior, but were unsure which scenarios would be most effective.
We wanted scenarios that work alongside the XGBoost model without artificially or inaccurately altering the underlying data.

## Accomplishments we are proud of

- An operable project within 24 hours that could realistically be used by an average business owner.
- Networking with fellow programmers.
- Learning new coding styles.
- Our first hackathon.

## What we learned

- Agent-based modeling and XGBoost with Monte Carlo to simulate people interacting in specified scenarios.
- Working efficiently under pressure in a time-limited space.
- Using Snowflake to build an AI chatbot that users can interact with.
- Using Claude as a development tool.

## What's next

We have not ruled out turning this into a startup that helps local Fredericton businesses.
Many of the cafes and restaurants have been here for a long time, and we want to help them stay open for years to come.

## Try it

Use the live app at https://sim4food.vercel.app.
If it is down or you want to test your own changes, run it locally with the steps below.
The app always talks to whichever backend `BACKEND_URL` points at, so local runs use your own backend and database and never touch the live one.

## How we built it

- **Frontend:** Next.js (App Router) and React, plain CSS, in `src/`.
- **Backend:** Python, FastAPI, XGBoost forecasting, Postgres via `asyncpg`, in `backend/`.
- **Database:** PostgreSQL on Neon. Schema in `db/schema.sql`.
- **Optional AI assistant:** Snowflake Cortex, see `docs/snowflake-cortex.md`.
- **Hosting (optional):** frontend on Vercel, backend on Render.

See `CLAUDE.md` for the architecture and conventions.

## Run it locally (fallback)

The steps below run the whole app on your own machine.
They take about 10 minutes.

### Prerequisites

- Node.js 20 or newer.
- Python 3.11 or newer.
- A free Neon Postgres project (https://neon.tech).
- Git.

### 1. Install dependencies

Frontend, from the repo root:

```
npm install
```

Backend, from the repo root:

```
cd backend
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cd ..
```

In PowerShell, activate with `.venv\Scripts\Activate.ps1`.
In Command Prompt, use `.venv\Scripts\activate.bat`.

### 2. Create the database

In your Neon project, open the SQL editor and run the contents of `db/schema.sql`.
`db/migrations/` only matters for databases created before a migration existed, a fresh database already has those changes.

### 3. Configure environment variables

Copy `.env.example` to `.env`, and `backend/.env.example` to `backend/.env`.
Paste your Neon connection string (Neon dashboard, Connection Details) into `POSTGRES_URL` in both files.
Leave `BACKEND_URL=http://localhost:8000` in the root `.env`.
The Snowflake variables in `backend/.env` are optional, the app works without them.
These files are gitignored, never commit them.

### 4. Start both servers

Use two terminals.

Terminal 1, from the repo root:

```
npm run dev
```

Terminal 2, from `backend/` with the virtualenv active:

```
cd backend
$env:PYTHONPATH = "."           # PowerShell
set PYTHONPATH=.                # Command Prompt
export PYTHONPATH=.             # macOS/Linux
python -m uvicorn app.main:app --reload --port 8000
```

Open http://localhost:3000, create an account on the sign-up page, then load the demo data from the app.

### Troubleshooting

- **Pages show a 404 or `ERR_CONNECTION_REFUSED`:** the backend is not running, or `BACKEND_URL` in `.env` is not `http://localhost:8000`.
  Restart `npm run dev` after changing `.env`, Next.js reads it only at startup.
- **`ModuleNotFoundError: No module named 'app'`:** run uvicorn from `backend/` with `PYTHONPATH` set.
- **`No module named uvicorn`:** the virtualenv is not active.
- **Database errors:** check `POSTGRES_URL` in both `.env` files, and that `db/schema.sql` was run.
  `http://localhost:3000/api/db-health` should return `"connected": true`.

Stop a server with Ctrl+C in its terminal.

## Host your own copy (optional)

You do not need this to try the app.
If you have Vercel and Render accounts, you can deploy your own copy.
The frontend and backend deploy separately, because the Python backend does not fit Vercel's function time limits.

1. **Backend on Render:** create a Blueprint from this repo, `render.yaml` defines the service (root directory `backend`).
   Set `POSTGRES_URL` to your Neon connection string.
   `SNOWFLAKE_ACCOUNT` and `SNOWFLAKE_PAT` are optional.
   Check that `https://<your-service>.onrender.com/openapi.json` loads.
   On the free plan the service sleeps, so the first request can take about a minute.
2. **Frontend on Vercel:** import the repo and set two environment variables.
   - `POSTGRES_URL`: the same Neon connection string.
   - `BACKEND_URL`: the Render URL from step 1, for example `https://<your-service>.onrender.com`.
     Do not use the Vercel address here, or every API call comes back as a 404.
3. Redeploy after changing environment variables, Next.js reads `BACKEND_URL` when it builds.

## Tests and lint

```
cd backend
python -m pytest
```

```
npm run lint
```

## Docs

- `docs/xgboost-forecasting.md` and `docs/forecast-values.md`: how the forecast works.
- `docs/snowflake-cortex.md`: optional AI assistant setup.
- `docs/internal/`: audit notes.
