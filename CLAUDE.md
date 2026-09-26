# SwarmStock (working name)

24-hour hackathon project, 2-person team. Helps independent restaurants cut food waste by recommending how much of each ingredient to order, using a multi-agent customer simulation plus Monte Carlo.

**Pitch:** Upload your sales and invoices. We show what you're wasting, what to order next week, and what a deal or holiday will do to your stock before you run it.

## Core concept

1. Owner provides data they already have: POS sales, supplier purchases, recipes, optional stock counts.
2. Waste is **calculated**, not entered: `waste = start stock + purchases - end stock - (dishes sold x recipe qty)`.
3. A swarm of rule-based customer agents is calibrated to match historical sales.
4. The upcoming week is simulated 200-500 times (Monte Carlo) to get a demand distribution per ingredient.
5. Order quantity per ingredient is chosen with the newsvendor rule, adjusted for stock on hand, shelf life, and pack size.
6. An animated restaurant view showcases the swarm while the simulation runs.

The swarm's advantage over plain forecasting: it handles **situations with no history** (new deals, holidays, word of mouth). Lead with this in the pitch.

## MVP features (must work for demo)

- **Setup:** ingredients, menu, recipes (dish templates to speed entry).
- **Upload:** sales CSV, purchases CSV, optional inventory counts; validation messages.
- **Waste report:** weekly waste in units and $, by ingredient, with trend.
- **Planner:** add upcoming holidays and deals (items, discount %).
- **Simulation showcase:** animated view of the restaurant door and dining room with customers entering, ordering, and leaving at fast-forward speed, alongside a run counter and a live-filling demand histogram. Stockouts are visible (customer leaves unhappy).
- **Recommendations:** per ingredient: order qty, P10-P90 range, expected waste, stockout risk, savings vs. current habit.
- **Scenarios:** deal % slider and holiday toggle re-run the simulation.
- **Backtest:** naive ordering vs. SwarmStock on 2 held-out weeks.

**Stretch (only after MVP works):** LLM explanation of recommendations; LLM invoice parsing; customer mix from a plain-English description.

**Out of scope:** accounts, multiple locations, live POS integration, supplier ordering.

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Python 3.11, FastAPI, Uvicorn |
| Simulation | NumPy (vectorized agents), pandas; NetworkX optional for the friend network |
| Frontend | React + Vite + TypeScript, Tailwind CSS |
| Charts | Recharts (or Chart.js) |
| Animation | HTML Canvas with `requestAnimationFrame` |
| LLM (stretch) | Claude API |
| Storage | Files only (CSV/JSON); no database |

## Repo structure

```
backend/
  app/main.py          FastAPI routes
  sim/generator.py     demo restaurant dataset + hidden true demand
  sim/ingest.py        load + validate uploads
  sim/waste.py         historical waste and $ loss
  sim/agents.py        agent traits, friend network, daily decisions
  sim/calibrate.py     tune params to match history
  sim/forecast.py      Monte Carlo -> ingredient demand distributions
  sim/optimize.py      newsvendor, shelf-life cap, pack rounding
  sim/backtest.py      naive vs. recommended on held-out weeks
  sim/replay.py        event log of one representative run for the animation
  data/demo/           generated demo files
frontend/
  src/pages/           Setup, Upload, Waste, Planner, Results, Backtest
  src/components/      SimView (animation), charts, tables
```

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

**Demo dataset:** 1 restaurant, 12 weeks, 6-8 dishes, 10-12 ingredients, one past holiday and one past deal, a mix of perishable and long-life ingredients. Purchases come from a naive owner rule ("last week's usage x 1.25", rounded to pack size). Last 2 weeks held out for backtest.

## Model summary

- **Agents:** segment, price sensitivity, category preferences, budget, friends.
- **Visit decision:** base rate x weekday x holiday x deal x social factor (share of friends who visited recently).
- **Dish choice:** softmax over `preference - price_sensitivity * price + deal_bonus`.
- **Stockout:** agent takes next choice or leaves; record lost sale.
- **Calibration:** match total sales (base visit rate), dish mix (preferences), deal lift (from past deal).
- **Newsvendor:** order at demand percentile `Cu / (Cu + Co)`; Cu = lost margin per unit short, Co = cost per unit wasted.

## API

| Method | Route | Returns |
|---|---|---|
| GET | `/api/demo` | loads demo dataset |
| POST | `/api/upload` | validation result |
| GET | `/api/waste` | waste by ingredient and week |
| POST | `/api/simulate` | recommendations, per-run demand results, replay event log |
| GET | `/api/backtest` | naive vs. recommended comparison |

## Conventions

- Rule-based agents only; never one LLM call per agent.
- Vectorize with NumPy. Full `/api/simulate` must finish in **under 10 seconds**.
- Fixed random seeds for reproducible demos.
- Money rounded to 2 decimals; quantities in the ingredient's unit.
- Animation only replays simulation output; it never affects results.
- Keep the demo dataset loadable in one click.

## Team split

- **Person A (engine):** agents, calibration, forecast, optimizer, backtest, replay log.
- **Person B (product):** generator, ingestion, all frontend pages, charts, animation, pitch.
- Agree on data files and API responses in hour 1.

## Milestones

| Hour | Milestone |
|---|---|
| 2 | Schema + API contract agreed; repo scaffolded |
| 6 | Demo dataset generated; simulation produces dish sales |
| 10 | End-to-end: upload -> recommendations (ugly is fine) |
| 18 | Calibration, events, backtest, all MVP screens |
| 21 | Animation showcase, polish, stretch goals |
| 22 | Code freeze |
| 24 | Pitch rehearsed twice; backup demo video recorded |

**Cut order if behind:** stretch goals -> animation (keep counter + histogram) -> friend network -> automatic calibration (hand-tune) -> shelf-life cap. Never cut recommendations, savings number, or backtest.

<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
