# What every number on the Forecast tab means

This page explains each value the Forecast tab shows: what it measures, how it is calculated, and how to read it.
The technical design is in [xgboost-forecasting.md](xgboost-forecasting.md) and the AI setup in [snowflake-cortex.md](snowflake-cortex.md).
Payload field names are given in `code` so each number can be traced to `POST /api/forecast`.

Two words are used with a precise meaning throughout:

- **Usage** is theoretical ingredient usage: dishes sold x recipe quantity per serving.
- **Demand** is usage as it would have been without stockouts: on a day a dish sold out, the forecast fills in for the zero.

## Run bar

| Shown | Meaning |
|---|---|
| Last run | When the forecast was last computed (`run_at`). Every number on the tab comes from that run; new uploads only show up after "Re-run forecast". |
| Run forecast / Re-run forecast | Retrains the model on all uploaded data and stores a new run. It takes a few seconds. |

## Headline cards

### Order for the week of

- **Value:** the Monday to Sunday week the order is for (`data.target_week`), normally the week after today.
- **Sub-line:** the last day with uploaded sales (`data.based_on_sales_through`).
- If sales stop before this week, the weeks in between are forecast first and used as history (`data.gap_weeks`).
- If the sales are more than 6 weeks old, the forecast is for the week right after the data instead, and a "Your sales data is out of date" card appears (`data.stale`).

### Perishable leftovers vs your orders

- **Value:** how much less (or more) perishable stock would have been left over at the end of each week with our orders than with what was actually bought, over the replayed weeks (`savings.order_backtest.waste_reduction_pct`).
  - Formula: `1 - our leftover $ / your leftover $`.
  - Green with a minus sign means fewer leftovers with our orders; amber with a plus sign means more.
- **Sub-line:** the net result in dollars (`savings.order_backtest.total_savings`): leftovers saved minus any extra profit lost by running out, summed over the replayed weeks.
- Details per week are in "How our orders would have done" at the bottom.

### Forecast error

- **Value:** weighted absolute percentage error (WAPE) of our forecast on past weeks it had not seen (`accuracy.methods.xgboost.wape`).
  - Formula: sum of |actual usage - forecast| / sum of actual usage, over every ingredient and backtest week.
  - 5.8% means the forecast was off by 5.8% of the real usage on average, weighted by volume. Lower is better.
- **Sub-line:** the same error for two simple rules, so the number has something to compare against:
  - same-weekday average: each dish's average for that weekday over the last 4 weeks (`dish_baseline`);
  - repeating last week: last week's usage again (`naive_last_week`).
- Days a dish sold out are left out of this score for every method, because sales on those days are not demand.

### Range hit rate

- **Value:** how often the actual weekly usage landed inside our likely range (P10 to P90) on past weeks (`accuracy.band_coverage.inside_p10_p90`).
- **Target:** 80% (`target_inside`). By design, about 1 week in 10 lands below the range and 1 in 10 above it.
- Much lower than 80% means the ranges are too narrow (overconfident); much higher means they are too wide.
- Every past week is scored with a range built only from weeks before it, so this is an honest out-of-sample number.
  With 4 to 6 scored weeks it is noisy: a few points either way is not meaningful.

## Status cards

| Card | When it shows | Meaning |
|---|---|---|
| Still learning | Under 8 weeks of sales (`data.status = learning`) | Treat numbers as rough; upload older sales. |
| Getting sharper | 8 to 25 weeks | Good enough to act on, better with more history. |
| (none) | 26 weeks or more | Established. |
| Your sales data is out of date | Sales more than 6 weeks old (`data.stale`) | The order is for the week after the data, not next week. |
| Footer line | Always on the card | How the forecast was made (`data.method_reason`): XGBoost blended 50/50 with the same-weekday average, or the average alone when it has been more accurate on this restaurant's history. |

### Events this week

Shown when a deal or holiday overlaps the target week (`events`).

- **Lift %:** how much the forecast for the dishes the event covers was raised or lowered (`lift_pct`).
- **Source:** "your estimate" when the upload gave an expected lift, otherwise "learned from your past events" (the average jump on past events of the same kind, pulled toward no change when there are few of them).
- "No past events like it yet" means no lift was applied, because there was nothing to learn from and no estimate was given.

## Overview and chat (Snowflake Cortex)

- **Overview** explains the current run in words: **Summary** is 3 to 5 short bullets, **Detailed** is two paragraphs.
- **Ask** (the button in the bottom-right corner, on every tab) answers questions about the data on the tab you are on; on this tab, the current run.
- Both are written by Snowflake Cortex from the numbers on this tab only, and are told not to invent any.
  They never change the forecast or the order.
- If a statement looks off, the tables below are the source of truth.

## What to order (one row per ingredient)

| Column | Meaning | Field |
|---|---|---|
| Ingredient | Name. An amber "+N% event" chip means a deal or holiday raised the forecast by N% (a minus sign means lowered). | `forecast.event_adjustment_pct` |
| Trend | Actual weekly usage over the history, oldest to newest. | `history[].usage` |
| Likely use | Bold: the middle forecast for the target week (P50). Below: the likely range, P10 to P90. Usage falls inside this range about 8 weeks in 10. Without enough history for a range, only the point forecast is shown. | `forecast.p50`, `p10`, `p90`, `point` |
| On hand Mon | Stock expected on the Monday the week starts: last stock count + purchases since - usage since - forecast usage for any days without sales data. Never below 0. "No count" means the ingredient was never counted, so 0 is assumed. | `recommendation.on_hand` |
| Order | Bold: total to order for the week, in whole packs. Below: the number of packs, then the split per delivery day. The first day (dark) is firm, order it now. Later days (grey) are a plan: re-check stock on the day, because the plan assumes the first days sell as forecast. | `recommendation.order_qty`, `packs`, `pack_size`, `deliveries` |
| vs usual | Our order minus the owner's usual rule, last week's usage x 1.25 minus stock, rounded up to packs per delivery. "Same" when equal. Amber is more than usual, green is less. | `order_qty - habit_order_qty` |
| Run-out risk | Chance of running out at some point in the week with our order, from 1000 simulated weeks. Green under 10%, amber 10% to 25%, red 25% or more. | `recommendation.stockout_risk` |
| Leftover risk | Expected dollar value of this perishable still on the shelf at the end of the week, at risk of spoiling. "Keeps" for long-life ingredients (shelf life over 7 days), whose leftovers are used the next week. | `recommendation.expected_waste_cost` |

### Why the order is not simply the likely use

- **Service level.** Each ingredient is ordered to a service level set by its costs (`recommendation.service_level`, between 50% and 95%).
  - Running out of an ingredient loses the profit on the dishes that need it.
  - Buying too much of a perishable loses its cost.
  - When running out costs much more than a leftover (cheap buns in an expensive burger), the order aims high in the range.
  - When they cost about the same (expensive fish), it aims near the middle.
- **Packs.** Orders are rounded up to whole packs, so they can land a little above P90 (for example 36 L of cream in packs of 4 against a likely use of 17 to 35 L).
- **Stock on hand.** Stock already on the shelf is subtracted.

## How our orders would have done

The last weeks of the backtest, replayed delivery by delivery on the real sales and stock counts.

| Column | Meaning |
|---|---|
| Week of | Monday of the replayed week. |
| Your leftovers | Dollar value of perishable stock still on hand at the end of the week with what was actually bought (the purchases file). |
| Our leftovers | The same with our orders: firm first delivery, later deliveries adjusted to how the first days actually sold. Green when lower than yours. |
| Your lost profit / Our lost profit | Profit lost from running out: units short x the dish profit per unit of that ingredient, assuming half the guests who miss a dish order something else. |
| Total | Sum over the replayed weeks. The headline card's net figure is (your leftovers + your lost profit) - (our leftovers + our lost profit). |

Both sides start each week from the same real stock count and face the same demand.
On sold-out days the demand is the forecast, not the zero sales.

## Leftovers here vs "Waste cost" on the Home tab

They are different measurements and will not match.

| | Home tab: Waste cost | Forecast tab: Leftovers |
|---|---|---|
| What it is | Stock that disappeared without being sold: start count + purchases - end count - usage. | Perishable stock still on the shelf at the end of a week. |
| Source | Measured from real stock counts. | Simulated replay of a week with a given set of orders. |
| Used for | What was actually lost. | Comparing two ordering strategies on equal terms. |

Leftovers are a leading indicator: perishable stock left at the end of a week is what tends to become next week's waste.
