# SwarmStock — Product Plan

## Executive summary

SwarmStock helps independent restaurants cut food waste.
Upload your sales and invoices.
We show what you're wasting, what to order next week, and what a deal or holiday will do to your stock before you run it.

It is a 24-hour hackathon project built by a 2-person team.
The core mechanism is a multi-agent customer simulation combined with Monte Carlo demand estimation, driving a per-ingredient order recommendation.

## Problem

Independent restaurants order ingredients using rules of thumb, most commonly "order what we used last week, plus a margin."
This works reasonably well for a normal week, but breaks down whenever something unusual happens: a new promotional deal, a local holiday, or word-of-mouth attention with no sales history to draw on.
The owner either over-orders and wastes perishable stock, or under-orders and runs out mid-service.
Neither failure mode is visible to the owner in real time — waste is rarely tracked directly, and the cost of a stockout (a lost sale, an unhappy customer) is invisible on a spreadsheet.

## Solution

SwarmStock turns data the owner already has into a forward-looking order recommendation, in six steps:

1. The owner provides data they already have: POS sales, supplier purchases, recipes, and optionally stock counts.
2. Waste is **calculated**, not entered: `waste = start stock + purchases - end stock - (dishes sold x recipe qty)`.
3. A swarm of rule-based customer agents is calibrated to match the restaurant's own historical sales.
4. The upcoming week is simulated 200-500 times (Monte Carlo) to produce a demand distribution per ingredient.
5. An order quantity per ingredient is chosen using the newsvendor rule, adjusted for stock on hand, shelf life, and supplier pack size.
6. An animated restaurant view showcases the swarm while the simulation runs, so the recommendation doesn't arrive as an unexplained number.

## Why a swarm, not a forecast

A plain statistical forecast extrapolates from history — it has nothing to say about a situation with no precedent.
SwarmStock's advantage is that it handles **situations with no history**: a new deal, an upcoming holiday, or word-of-mouth buzz.
Because the simulation models individual customer decisions (visit, dish choice, price sensitivity, social influence from friends who visited recently), the owner can toggle a deal or holiday on and immediately see a plausible demand shift, without waiting for it to actually happen first.
This is the lead argument of the pitch: not "we forecast better," but "we still work when there's nothing to forecast from."

## User & journey

**Persona:** an independent restaurant owner-operator who already has POS sales exports and supplier invoices, but no formal inventory or demand planning tool.
They are time-constrained, not a data analyst, and want a number they can act on before placing next week's order.

**Journey**, following the six planned pages:

1. **Setup** — enter ingredients, menu, and recipes (dish templates speed this up so it isn't a blank form).
2. **Upload** — upload sales CSV, purchases CSV, and optionally inventory counts; get validation messages if something looks wrong.
3. **Waste** — see weekly waste in units and dollars, by ingredient, with a trend line. This is the "aha" moment — waste they didn't know they had.
4. **Planner** — add an upcoming holiday or a deal (which items, what discount).
5. **Results** — watch the animated simulation run, then see per-ingredient order quantity, a P10-P90 range, expected waste, stockout risk, and savings versus their current ordering habit. A deal-percent slider and holiday toggle re-run the simulation live.
6. **Backtest** — see naive ordering versus SwarmStock's recommendation compared on two held-out weeks of real history, so the recommendation isn't just a promise.

## MVP feature list

- **Setup:** ingredients, menu, recipes (dish templates to speed entry).
- **Upload:** sales CSV, purchases CSV, optional inventory counts; validation messages.
- **Waste report:** weekly waste in units and dollars, by ingredient, with trend.
- **Planner:** add upcoming holidays and deals (items, discount %).
- **Simulation showcase:** animated view of the restaurant door and dining room with customers entering, ordering, and leaving at fast-forward speed, alongside a run counter and a live-filling demand histogram. Stockouts are visible (customer leaves unhappy).
- **Recommendations:** per ingredient — order qty, P10-P90 range, expected waste, stockout risk, savings vs. current habit.
- **Scenarios:** deal % slider and holiday toggle re-run the simulation.
- **Backtest:** naive ordering vs. SwarmStock on 2 held-out weeks.

## Stretch goals

Only pursued after the MVP above fully works:

- LLM-generated plain-English explanation of recommendations.
- LLM-assisted invoice parsing (skip manual purchase entry).
- Customer mix defined from a plain-English description instead of manual segment entry.

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

## Cut order if behind schedule

If time runs short, cut in this order: stretch goals, then animation (keep the run counter and histogram, drop the full showcase), then the friend network, then automatic calibration (hand-tune instead), then the shelf-life cap.
Recommendations, the savings number, and the backtest are never cut — they are the demo.

## Roadmap beyond the hackathon

Everything below is explicitly out of scope for the MVP and not committed to — it is a directional sketch of what a real product would eventually need, not a promise:

- **Real accounts and authentication** — today's login/signup flow is a client-side demo facade with no password check; a real product needs actual auth.
- **Multiple restaurant locations per account** — the MVP assumes one restaurant.
- **Live POS integration** — the MVP works from uploaded CSV exports, not a live data feed.
- **Supplier ordering** — the MVP recommends a quantity; it doesn't place or track an actual order with a supplier.

## Risks

- **Calibration accuracy with sparse history** — a 12-week demo dataset is thin for calibrating agent behavior with confidence; hand-tuning may be needed if automatic calibration doesn't converge in time (see cut order above).
- **Demo dataset realism** — the generated dataset needs to look like a real restaurant's data (including its one past holiday and one past deal) for the backtest and deal/holiday scenarios to be persuasive.
- **Hosting an ephemeral Python backend during a live demo** — the FastAPI backend runs on a host separate from the Vercel-hosted frontend; a mid-demo redeploy or restart could lose in-memory state or uploaded files, so the demo run-through should avoid redeploying once the pitch starts.
