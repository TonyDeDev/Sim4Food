# XGBoost Forecasting Audit

How the XGBoost forecasting feature works today, what is solid, and what to fix, with the hackathon goal in mind.
The design reference is [xgboost-forecasting.md](xgboost-forecasting.md).
App-wide issues are in [report-to-fix.md](report-to-fix.md).

## How it works today

The Forecast tab's "Run forecast" button calls `POST /api/forecast` (`backend/app/main.py:101`).

1. `sim/dataset.load_frames` loads sales, recipe versions, ingredient versions, purchases, counts and events from Postgres into pandas.
2. `sim/forecast_payload.build_forecast_payload` drops the in-progress week, so a partial week is not read as a slow one.
3. `sim/dish_features.build_dish_matrix` builds one row per dish per day.
   The target is a ratio: `qty_sold / baseline`, where the baseline is the mean of the same weekday over the last up to 4 weeks, clipped to 0 to 3.
   There are 17 features: calendar, same-weekday lag ratios, 7 and 28 day mean ratios, dish trend, restaurant traffic, price vs history, and 5 event features.
4. `sim/forecast_backtest.rolling_backtest` retrains the model for every origin week using only earlier weeks, and records out-of-sample ingredient-week errors against three baselines.
5. `sim/train_dish_xgb.fit` trains the final model (weeks before the last 2 as train, the last 2 for early stopping), rows weighted by baseline size.
6. `train_dish_xgb.forecast_next_week` predicts each dish-day of the next week, then converts dishes to ingredient usage with the recipe line in force on each day (`sim/history.attach_recipes`).
7. Bands: `actual / predicted` ratios from the backtest are pooled across all ingredients, and conformal-corrected P10, P50 and P90 multipliers are applied to the point forecast.
8. The payload is stored in `simulation_runs` (`sim/forecast_store.py`) and shown in `src/components/ForecastOverview.jsx`.
   `GET /api/forecast` only reads the latest stored run and never trains.

Measured on the demo CSVs (12 weeks, 7 dishes, 12 ingredients):

| Metric | Value |
|---|---|
| Runtime of `build_forecast_payload` | 0.62 s |
| Out-of-sample origins | 6 weeks, 72 ingredient-weeks |
| WAPE: XGBoost / weekday baseline / 4-week mean / last week | 0.056 / 0.057 / 0.057 / 0.071 |
| P10-P90 coverage (target 0.80) | 0.683 (0.133 below, 0.183 above) |
| Forecast week | 2026-09-21 |

## What is solid

- Leakage rules are explicit and tested: same-weekday lags are at least 7 days back, weekly stats are shifted, and `test_no_leakage_from_current_or_future_days` mutates future sales and checks features do not move.
- The ratio target lets every dish teach the same lessons, which is the right call on thin data, and falls back to the baseline when there is no signal.
- Recipe and cost history are point-in-time, so editing a recipe never rewrites past usage.
- Bands use a finite-sample conformal rank, and coverage is measured on bands built only from earlier origins.
- `data_status` is honest about thin history, and training runs in a worker thread so the API stays responsive.
- The existing doc already reports that XGBoost only ties the baseline on 12 weeks, instead of overselling it.

## Findings

| # | Severity | Finding |
|---|---|---|
| X1 | Medium | Two pipelines, one unused |
| X2 | High | Final model never trains on the 2 most recent weeks |
| X3 | Medium | Calendar features act as a time index |
| X4 | High | Event features are effectively always 0 |
| X5 | High | Forecast horizon is fixed and can be in the past |
| X6 | High | Stockouts are learned as low demand |
| X7 | Medium | Bands are pooled and under-cover |
| X8 | Low | `point` and `p50` differ |
| X9 | High | No recommendation step after the forecast |
| X10 | Medium | Dish list comes from sales, not the menu |
| X11 | High | Two inputs crash the endpoint |
| X12 | Low | Rolling backtest cost grows with history |
| X13 | Low | Saved CLI models are never used |

### X1 Two pipelines, one unused

- Where: `backend/sim/features.py` and `backend/sim/train_xgb.py` (ingredient-week model, about 440 lines plus `tests/test_features.py`).
- What: the API only uses the dish-level model (`dish_features.py`, `train_dish_xgb.py`).
  The ingredient-level model is only reachable from its CLI, and its own doc says it lost to the baselines.
- Fix: move it under an `experimental` note in the docs or delete it, so nobody extends the wrong pipeline during the hackathon.

### X2 Final model never trains on the 2 most recent weeks

- Where: `backend/sim/forecast_payload.py:94`.
- What: the final model trains on weeks before the last 2, and the last 2 weeks are only used for early stopping.
  With 12 weeks of history, the two most informative weeks never shape the trees.
- Fix: keep the split to find `best_iteration`, then refit on all usable weeks with `n_estimators=best_iteration + 1` and no early stopping.
  Confirm with the rolling backtest that WAPE does not get worse.

### X3 Calendar features act as a time index

- Where: `backend/sim/dish_features.py:25-26` (`week_of_year`, `month`).
- What: with under a year of data, every week has a unique `week_of_year`.
  Trees can split on it as a proxy for "early vs late in the data", and a future week falls outside every value seen in training.
- Fix: drop `week_of_year` and `month` until there are 52+ weeks, keep `dow`.
  Re-run `python -m sim.forecast_backtest --csv-dir data/demo` to confirm.

### X4 Event features are effectively always 0

- Where: `backend/sim/dish_features.py:64-92`, `backend/sim/ingest.py` (no `events` upload type).
- What:
  - Events cannot be uploaded (report P0-6), so in Postgres the 5 event features are 0 for every row.
  - In the demo `events.csv`, `expected_lift` is empty for every row, so `event_expected_lift` is 0 even offline.
  - The history holds one deal and two holidays, which is not enough for trees to learn a lift.
  - The ratio target is clipped at 3 (`dish_features.py:46`), so a strong deal would be capped anyway.
- Why it matters: the pitch is about deals and holidays, and this model cannot react to them.
- Fix: do not rely on XGBoost to learn event lift.
  Forecast the normal week with XGBoost, and apply event effects on top: either the owner's `expected_lift` and a price elasticity for `discount_pct`, or the calibrated swarm.
  Keep the event features in the model so it can pick them up once enough history exists.

### X5 Forecast horizon is fixed and can be in the past

- Where: `backend/sim/train_dish_xgb.py:132-143`, `backend/sim/forecast_payload.py:63-77`.
- What: the forecast is always the week after the last complete sales week.
  If sales end on a Wednesday, the "next week" forecast is the current week, already half gone.
  On the demo data it is 2026-09-21, and the upcoming Oct 9-12 deal and holiday can never be forecast.
- Fix: take a `target_week` (default: the Monday after today).
  For gap weeks, roll the weekday baseline forward (use the forecast of week W as the history of week W+1), which the ratio setup supports naturally.
  Return the target week and the gap in the payload so the UI can say "forecast for Oct 12-18, based on sales through Sep 20".

### X6 Stockouts are learned as low demand

- Where: `backend/sim/dish_features.py:123-128` (sales are the target), noted in `backend/sim/explore.py:69` ("skip sold-out days (censored)").
- What: on a sold-out day, sales are lower than demand.
  The model learns that day as low demand, forecasts low, the owner orders low, and the stockout repeats.
- Fix: flag dish-days where an ingredient of the dish had a count of 0 (or where the owner marks a sell-out), and drop those rows from the training target or down-weight them.
  This also becomes a strong pitch point: "we forecast demand, not sales".

### X7 Bands are pooled and under-cover

- Where: `backend/sim/forecast_backtest.py:80-112`, `backend/sim/forecast_payload.py:103-104`.
- What:
  - One set of P10/P50/P90 multipliers is shared by every ingredient, so a stable staple gets the same relative spread as a volatile special.
  - Ingredients driven by the same dish (beef patty and brioche bun in the demo) get identical forecasts and bands.
  - Coverage is 0.683 against a 0.80 target, and the UI labels this number "Forecast confidence".
- Fix, in order:
  - Label it honestly in the UI (see report P2).
  - Scale the pooled ratio spread per dish by its same-weekday coefficient of variation (`wd_cv` is already a feature).
  - Build bands from dish-day errors, which are far more numerous, and propagate to ingredients.
  - Widen bands in event weeks.
  - Longer term, the swarm's Monte Carlo runs give a distribution directly.

### X8 `point` and `p50` differ

- Where: `backend/sim/forecast_payload.py:130-135`.
- What: `p50 = point x median(actual / predicted)`, so the two disagree (for example 319.61 vs 326.28 for beef patty).
  The UI shows `p50` with a fallback to `point`.
- Fix: show one number consistently.
  For ordering, neither is right: use the quantile at the newsvendor critical ratio (X9).

### X9 No recommendation step after the forecast

- Where: `backend/sim/optimize.py` (stub), `backend/sim/forecast_payload.py:7-8`.
- What: the forecast stops at usage.
  Order quantity, expected waste, stockout risk and savings, all MVP items, are missing.
- Fix: per ingredient,
  - `Cu` = lost margin per unit short (dish price minus food cost, spread over its ingredients), `Co` = unit cost of a wasted unit.
  - `q* = Cu / (Cu + Co)`, and demand at `q*` = `point x conformal_quantile(ratios, q*)` from the same backtest ratios.
  - Projected on hand at delivery = latest count + purchases since - forecast usage until delivery.
  - Order = `max(0, demand_at_q* - projected_on_hand)`, capped at `shelf_life_days x daily usage`, rounded up to `pack_size`.
  - Savings: replay the backtest weeks with the owner's rule (last week's usage x 1.25, rounded to pack) versus this rule, and price the waste and the shortfall.

### X10 Dish list comes from sales, not the menu

- Where: `backend/sim/dish_features.py:120`.
- What: dishes are taken from `sales`.
  A new dish with no sales yet gets no forecast, so its ingredients are under-forecast.
  A dish launched mid-history has zeros before launch, which drag its baseline down for up to 4 weeks.
- Fix: take dishes from `menu_items`, mark days before a dish's first sale as not on the menu (NaN, not 0), and let new dishes fall back to the owner's estimate or the category average.

### X11 Two inputs crash the endpoint

- Where: `backend/sim/forecast_payload.py:117` and `:159`.
- What: sales without recipes give an empty forecast, and `iloc[0]` raises.
  Less than one complete week of sales gives an empty week list, and `weeks[0]` raises.
  Both return 500 from `POST /api/forecast`.
- Fix: return the `weeks_of_history: 0` payload with a message such as "Upload recipes to turn dish sales into ingredient usage", and add tests for both.

### X12 Rolling backtest cost grows with history

- Where: `backend/sim/forecast_backtest.py:51`.
- What: the model is retrained once per origin week.
  It takes 0.62 s at 12 weeks, but a year of history means about 47 fits per click, pushing past the 10 s rule in CLAUDE.md.
- Fix: cap the backtest to the last 12 origins, or cache backtest rows per origin and only add new weeks.

### X13 Saved CLI models are never used

- Where: `backend/sim/train_xgb.py:89-91`, `backend/sim/train_dish_xgb.py:172-174` write to `backend/models/`.
- What: the API always retrains and never loads these files.
- Fix: say so in the docs, or drop the save step, so nobody expects the API to use a saved model.

## How XGBoost and  the swarm should fit together

For the pitch and for the remaining build time, give each part one job.

- XGBoost learns "your normal week" from history: the per-dish, per-day baseline with honest error bands.
- The swarm is calibrated so its normal week matches that XGBoost forecast, then answers what history cannot: a new deal, a holiday, word of mouth.
  This is the "situations with no history" advantage CLAUDE.md says to lead with.
- The newsvendor step turns either distribution into an order quantity, expected waste, stockout risk and savings.

Be honest in the pitch: on 12 weeks of data XGBoost ties the same-weekday baseline (WAPE 0.056 vs 0.057) and clearly beats "last week" (0.071).
Its value today is a leak-free pipeline that gets better as history grows.
