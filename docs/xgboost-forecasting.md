# XGBoost ingredient usage forecasting and ordering

## Purpose and scope

This document describes the XGBoost forecasting layer for SwarmStock and the order recommendation built on it.
It forecasts the theoretical usage of each ingredient for the target week from POS sales and recipes stored in Neon, and turns that forecast into an order per delivery day.
The V2 section right below is the current design.
The V1 sections after it are kept for the reasoning and the history of the numbers.
The audit that motivated V2 is in [xgboost-audit.md](internal/xgboost-audit.md).

Pipeline (V2):

```
sales -> dish x day matrix (stockout days censored, event days kept out of the baseline)
  -> rolling-origin backtest (retrain per week, champion check)
  -> XGBoost ratio model, blended 50/50 with the same-weekday baseline
  -> recursive forecast up to the target week, explicit deal and holiday lift
  -> Monte Carlo usage samples from out-of-sample residuals (P10 / P50 / P90, any quantile)
  -> newsvendor order per delivery day, pack rounding, projected stock
  -> savings vs the owner's habit and a replay against what they actually bought
```

The primary target is usage, not purchase quantity.
Historical purchases are not necessarily what the restaurant needed, so they are never a training target.

## V2: what changed and why

Each change was kept only if the rolling backtest on the demo data did not get worse.
Numbers are from `python -m sim.forecast_backtest --csv-dir data/demo` (6 origin weeks, 72 ingredient-weeks), scored on uncensored dish-days only.

| Change | Where | Why |
|---|---|---|
| Stockout days are censored | `dish_features.py` | A dish that normally sells and sold 0 on an open day ran out. That day is never a training target, and its baseline falls back to the dish's recent level x the restaurant's weekday index, so the forecast estimates demand instead of repeating the zero. In the demo, fish and chips sells out every Sunday. |
| Days before a dish's first sale are unknown | `dish_features.py` | A new dish no longer drags its own baseline down with pre-launch zeros. |
| Event days kept out of the normal baseline | `dish_features.py` | A deal weekend no longer inflates the same weekday for the next 4 weeks. |
| Explicit deal and holiday lift | `events_adjust.py` | With a handful of past event days, trees cannot learn a lift. The lift is the mean actual / baseline on past uncensored event days, shrunk toward 1 (`n / (n + 3)`) and scaled by discount. The owner's `expected_lift` wins when given. |
| Event and season features gated on data volume | `train_dish_xgb.select_features` | Event features need 30 event rows, `week_of_year` and `month` need 52 weeks. Before that they only let the model memorise. Deal features carry monotone constraints. |
| Refit after early stopping | `train_dish_xgb.fit` | Early stopping picks the tree count on the 2 newest weeks, then the model is refit on all weeks so the newest data shapes it. |
| 50/50 blend with the weekday baseline | `train_dish_xgb.predict_qty` | On 12 weeks the model alone (WAPE 0.067) lost to the baseline (0.061), and the equal-weight blend beat both (0.058). The weight is a fixed prior, not tuned on these weeks. |
| Champion check | `forecast_payload.py` | If the blend's backtest error is worse than the baseline's, the baseline is shipped and the UI says why. |
| Target week anchored to today | `forecast_payload._target`, `train_dish_xgb.forecast_weeks` | The forecast used to target the week after the data, which could already be over. It now targets the week after today and rolls forward recursively (up to 6 weeks). Older data is flagged as stale. |
| Monte Carlo bands | `uncertainty.py` | See below. |
| Backtest scored on uncensored days, capped to 12 origins | `forecast_backtest.py` | A stockout day's sales are not demand. The cap keeps a year of history under the 10 s rule. |
| Order recommendation | `recommend.py` | See below. |

### Accuracy (demo data, out of sample)

| Method | WAPE |
|---|---|
| Shipped: XGBoost 50/50 with weekday baseline, event lift | 0.058 |
| Same-weekday baseline (censor aware, event lift) | 0.061 |
| Raw same-weekday mean of the last 4 weeks | 0.061 |
| Same as last week | 0.073 |
| V1 dish model, re-scored on the same uncensored days | 0.060 |

### Bands: Monte Carlo from out-of-sample residuals

- For every backtest week and dish, `log(actual / predicted)` is split into a week effect (weighted mean over dishes, shared by every dish that week) and dish noise.
- Each of 1000 draws (fixed seed) samples a week effect and a dish noise per dish, multiplies the dish forecasts, and converts dishes to ingredients with the recipes.
  Ingredients that share dishes (beef patty and bun) move together, as they really do.
- A spread scale widens the draws around their median until P10 to P90 held 80% of past actuals.
  When scoring a week, the scale is fit only on earlier weeks, so the reported coverage is out of sample.
- The spread grows with `sqrt(weeks ahead)`, and dishes carrying an event lift get extra spread.

| Bands (same 48 ingredient-weeks) | Inside P10 to P90 | Relative interval score | Relative pinball |
|---|---|---|---|
| V1 pooled ratio | 0.646 | 0.563 | 0.035 |
| V2 Monte Carlo | 0.854 | 0.532 | 0.037 |

The interval score (lower is better) rewards bands that are both narrow and right.
V2 reaches the 80% target with a better interval score, while the median (pinball) is slightly worse.
With 4 to 6 scored weeks these numbers are noisy.
On the same data loaded from Neon, where dish ids are UUIDs and the random draws land differently, coverage was 0.77.

### Order recommendation

- Delivery days are read from the purchase history (weekdays with at least 15% of purchase rows, Monday and Thursday in the demo).
- Per ingredient, `Co` is the unit cost if perishable (shelf life 7 days or less), else a 10% carry cost.
  `Cu` is half the dish margin lost per unit short, weighted by the dishes that use the ingredient.
  The service level `q* = Cu / (Cu + Co)` is clipped to 0.5 to 0.95.
- The first delivery is firm: the `q*` quantile of that cycle's usage minus projected stock, rounded up to whole packs.
- Later deliveries adapt: the forecast for the rest of the week is scaled by half of the surprise seen so far, then topped up to its `q*` quantile.
- Projected stock at the target Monday is the latest count + purchases since - actual usage since - forecast usage for the gap days.
- Outcomes are simulated on the Monte Carlo samples: expected leftover, waste cost (perishables) and run-out risk.
- The same samples score the owner's habit (last week's usage x 1.25 minus stock, rounded to packs).
- `order_backtest` replays the backtest weeks delivery by delivery: our adaptive orders against what the owner actually bought, on estimated demand (sales, with stockout days filled by the forecast).

On the demo data (4 replayed weeks) our orders cut waste by 10% (offline CSVs) to 16% (Neon) against what the owner actually bought, with a little more lost margin, for net savings of $10 to $190 over the 4 weeks.
The demo owner already tops up mid-week, which is a strong baseline.
Committing the whole week on Monday lost to them, which is why the adaptive top-up exists.

### Payload (V2)

```
data:        weeks_of_history, first_week, last_week, target_week (= forecast_week), based_on_sales_through,
             gap_weeks, stale, method (xgboost_blend | weekday_baseline | baseline), method_reason, status, message
accuracy:    backtest_weeks, methods{xgboost, dish_baseline, naive_last_week, mean_4w}{mae, wape},
             band_coverage{inside_p10_p90, below_p10, above_p90, n, relative_interval_score, relative_pinball, target_inside},
             band_comparison{monte_carlo, pooled_ratio}, spread_scale, stockout_days_excluded
events:      [{name, type, start_date, end_date, discount_pct, lift_pct, lift_source}] overlapping the target week
savings:     delivery_days, weekly_expected_vs_habit, expected_waste_cost, habit_waste_cost,
             order_backtest{weeks, ours, actual, total_savings, weekly_savings, waste_reduction_pct, by_week[]}
ingredients: [{ ingredient_id, name, unit,
                history:  [{week, usage}],
                forecast: {week, point, p10, p50, p90, event_adjustment_pct},
                recommendation: {order_qty, deliveries[{day, qty, firm}], packs, pack_size, on_hand, service_level,
                                 perishable, expected_leftover, expected_waste_cost, stockout_risk,
                                 habit_order_qty, habit_stockout_risk, expected_savings},
                backtest: [{week, actual, predicted, p10, p90}] }]
```

`POST /api/forecast?restaurant_id=<uuid>&target_week=<YYYY-MM-DD>` (the target week is optional) runs it in about 3.5 s on the demo data from Neon.
The Snowflake Cortex summary and chat read this stored payload, see [snowflake-cortex.md](snowflake-cortex.md).

### Known limits

- 12 weeks is thin: the blend's edge over the baseline (0.058 vs 0.061) is within week-to-week noise.
- Residuals are one-week-ahead errors, so the `sqrt(weeks ahead)` widening for gap weeks is an assumption, not a measurement.
- A partial-day stockout (sold some, then ran out) is not detected, only zero-sale days are censored.
- The weekly simulation treats all perishable leftovers at the end of the week as waste, for both sides of every comparison.
- The ingredient-level model (`features.py`, `train_xgb.py`) is experimental and not used by the API.

## Code map

| File | Role |
|---|---|
| `backend/sim/dataset.py` | Async loader: pulls one restaurant's tables (including menu prices) from Postgres into pandas frames with string ids. |
| `backend/sim/dish_features.py` | Daily dish matrix: ratio target, censored stockout days, clean baselines, event flags (`build_dish_matrix`). |
| `backend/sim/train_dish_xgb.py` | Feature selection, fit with refit, blended prediction, recursive multi-week forecast, and a CLI for inspection. |
| `backend/sim/events_adjust.py` | Deal and holiday lift, estimated from history or taken from the owner. |
| `backend/sim/forecast_backtest.py` | Rolling-origin backtest at dish-day level, ingredient-week scoring, band comparison, and a CLI. |
| `backend/sim/uncertainty.py` | Monte Carlo usage samples, out-of-sample band scoring and calibration. |
| `backend/sim/recommend.py` | Newsvendor orders per delivery day, projected stock, habit comparison, order backtest. |
| `backend/sim/forecast_payload.py` | Builds the JSON payload for the frontend. |
| `backend/app/main.py` | `GET` and `POST /api/forecast`, protected by the session and ownership check. |
| `backend/sim/features.py`, `backend/sim/train_xgb.py` | Experimental ingredient-week model, not used by the API. |
| `backend/tests/test_dish_features.py`, `test_forecast_backtest.py`, `test_forecast_quality.py`, `test_forecast_payload.py` | Leakage, censoring, refit, lift, bands, recommendations and payload tests. |

## Training grain and target

- One row per `restaurant_id x ingredient_id x forecast_week`.
- Weeks run Monday to Sunday, the same convention as `sim/waste.py`.
- Target `next_week_usage` is the sum over the forecast week of `qty_sold x recipes.qty_per_serving`.
- Ingredients with no usage in a week get a target of 0, not a missing row.
- `recipes` has no unit column, so `qty_per_serving` is implicitly in the ingredient's own unit.
  No unit conversion exists in the schema or code, so none is applied.
  If a unit column is ever added, conversion to `ingredients.unit` must happen inside `weekly_usage`.

## Point-in-time rule

For a row with forecast week W, the cutoff is the Sunday that ends week W-1.
Features may only use data dated on or before the cutoff.

- Every lag and rolling feature is computed on a series shifted by one week.
- Inventory features use the latest `inventory_counts` row at or before the cutoff (an as-of lookup).
- `inventory_current` is never used for historical rows, because it holds today's stock.
- `customer_profiles` is not used, because it is a current snapshot and would leak the present into the past.
- Calendar and event features describe week W itself.
  This is allowed because holidays and planned deals are known ahead of the forecast week.
- Events are not filtered by `events.created_at`.
  Historical events are typically loaded in bulk after the fact, so `created_at` would wrongly remove them.
  We assume the event table only holds events that were planned ahead of time.
- The test `test_no_leakage_from_current_or_future_data` mutates sales, purchases and counts dated in week W or later and asserts that every feature in row W is unchanged.

For inference, `include_next_week=True` adds one row per ingredient for the week after the last sales week.
Its target is NaN, and its features are built from history only.

## V1 features

| Feature | Source | Definition |
|---|---|---|
| `usage_lag_1w`, `_2w`, `_4w`, `_8w`, `_52w` | sales, recipes | Weekly ingredient usage k weeks before W. |
| `usage_mean_4w`, `usage_mean_8w` | sales, recipes | Mean usage over the last 4 or 8 weeks before W. |
| `usage_std_8w` | sales, recipes | Standard deviation over the last 8 weeks (needs 2 weeks). |
| `usage_trend_4w` | sales, recipes | Least squares slope over the last 4 weeks (needs 4 weeks). |
| `dish_demand_contribution` | sales, recipes | Share of last week's ingredient usage that came from the top dish. |
| `number_of_dishes_using_ingredient` | recipes | Count of menu items whose recipe uses the ingredient. Structural, not time varying. |
| `total_restaurant_sales_lag_1w` | sales | Total dishes sold in week W-1. |
| `purchase_qty_lag_1w` | purchases | Quantity purchased in week W-1. |
| `purchase_qty_mean_4w` | purchases | Mean weekly purchased quantity over the last 4 weeks. |
| `days_since_last_purchase` | purchases | Days from the last purchase to the cutoff. |
| `purchase_to_usage_ratio_4w` | purchases, sales | Purchased quantity divided by usage over the last 4 weeks (needs 4 weeks). |
| `current_qty_on_hand` | inventory_counts | Latest count at or before the cutoff. |
| `inventory_lag_1w` | inventory_counts | Latest count at or before the cutoff minus 7 days. |
| `inventory_to_usage_ratio` | inventory_counts, sales | `current_qty_on_hand / usage_mean_4w`, which equals weeks of inventory. |
| `inventory_variance_4w` | counts, purchases, sales | Actual count at cutoff minus (count 4 weeks earlier + purchases - theoretical usage). |
| `week_of_year`, `month` | calendar | ISO week and month of the Monday of W. |
| `holiday_flag`, `deal_flag` | events | 1 when a holiday or deal overlaps week W. |
| `ingredient_event_flag` | events, recipes | 1 when an event overlapping W lists a menu item whose recipe uses the ingredient. |
| `event_expected_lift` | events | Largest `expected_lift` among events affecting the ingredient in W. Holidays without an item list apply to all ingredients. |
| `unit_cost`, `pack_size`, `shelf_life_days` | ingredients (history rows) | Value in force at the Monday of W, from the change log. The next-week inference row uses the current value. |
| `unit_cost_change_pct_4w` | ingredients (history rows) | `unit_cost` at the Monday of W divided by `unit_cost` 28 days earlier, minus 1. 0 when nothing changed. |
| `days_since_price_change` | ingredients (history rows) | Days from the latest logged `unit_cost` change effective at or before the Monday of W. NaN when none. |
| `price_changed_recent_flag` | ingredients (history rows) | 1 when `days_since_price_change` is 14 or less. |
| `recipe_qty_per_dish_sum` | recipes (history rows) | Sum of `qty_per_serving` across the dishes using the ingredient, as in force at the Monday of W. |
| `days_since_recipe_change` | recipes (history rows) | Days from the latest logged recipe change for the ingredient effective at or before the Monday of W. NaN when none. |
| `recipe_change_flag_4w` | recipes (history rows) | 1 when `days_since_recipe_change` is 28 or less. |

`inventory_variance_4w` is deliberately not called waste.
It also contains count errors, unrecorded usage and transfers.

## Deferred features

These were in the original feature list and are left out of V1:

- Extra lags and rolling stats: `usage_lag_3w`, `_12w`, `usage_mean_2w`, `_12w`, min, max, median, trend 8w, `usage_vs_mean_*`.
- Dish-level POS features beyond the top dish share: per-dish lags, means, std, trend, top 3 share.
- Recipe features: min, max and weighted `qty_per_serving`, `total_historical_recipe_demand`.
- Restaurant-wide activity: extra sales lags and means, growth rates, active menu item count.
- Price features from `avg_price`: lags, means, `price_change_pct`, `discount_proxy`.
- Extra purchase, inventory and variance features: lags, frequency, unit cost trends, inventory change, count frequency, `inventory_variance_pct`, `inventory_variance_std_8w`.
- Day-of-week usage from the previous week (`last_week_monday_usage` and so on).
- Event timing: `days_to_event`, `days_since_event`, `event_days`, `event_count`, `event_discount_pct`.
- Customer profile features: only after profile snapshots are versioned by date.
- `pack_size / average_weekly_usage`, `ingredient_age_risk`.

## Not possible with the current schema

- Supplier features (lead time, minimum order, reliability, fill rate, delivery delay), because no supplier data exists.
- Order-level features (transaction count, basket size, dine-in versus takeout, lunch versus dinner), because `sales` has no order id or time of day.
- Exact discounts, because `sales` only has `avg_price`.

## Data limitations and NaN handling

- The demo restaurant has 12 weeks of data and 12 ingredients, about 144 rows before lags.
  After dropping weeks without a previous week there are 132 rows.
- `usage_lag_52w` is always missing, and `usage_lag_8w` is missing for most rows.
  XGBoost handles missing values natively, so these stay as NaN and are never filled with 0.
- Purchases, counts and events tables may be empty.
  Empty purchases or counts produce NaN features (missing data is not the same as zero).
  Empty events produce all zero event features.
- The upload API has no handler for `events` or `customer_profile`, so Neon may not contain events.
  The demo `events.csv` uses external ids such as `chicken_wrap`, while `events.items` is `UUID[]`.
  Confirm what is actually stored before relying on `ingredient_event_flag`.

## Split, model and metrics

Chronological split by forecast week:

- Test: the last 2 usable weeks (the same 2 held-out weeks as the project backtest).
- Validation: the 2 weeks before that, used for early stopping.
- Train: all earlier weeks.
- Rows without `usage_lag_1w` or without a target are dropped before splitting.

Model: `XGBRegressor`, squared error, small and heavily regularized because data is thin.
`max_depth=3`, `min_child_weight=3`, `learning_rate=0.05`, up to 300 trees with early stopping after 20 rounds, `subsample=0.8`, `colsample_bytree=0.8`, `reg_lambda=5`, fixed `random_state=42`.

Metrics on the test weeks are MAE and WAPE (sum of absolute error divided by sum of actuals), compared with two baselines: last week's usage, and the 4 week mean.

First result on the demo CSVs (offline, same data as Neon sample data):

| Model | MAE | WAPE |
|---|---|---|
| xgboost | 7.43 | 0.062 |
| naive last week | 6.20 | 0.052 |
| 4 week mean | 6.09 | 0.051 |

On 12 weeks of data the baselines beat XGBoost.
That is expected with about 7 training weeks, and it means the model should not be shipped to users yet.
The value of this pass is a leak-free pipeline that improves as history accumulates.

## Dish-level daily model (V1b)

The ingredient-level model above has only about 132 rows on 12 weeks of data.
The dish-level model predicts what actually drives usage, the number of each dish sold per day, and converts to ingredients afterwards.
`usage = sum over dishes and days of predicted qty x recipes.qty_per_serving`.
This is exact for theoretical usage, so nothing is lost by modelling dishes.

### Grain and rows

- One row per `menu_item x day`, grouped in forecast weeks (Monday to Sunday).
- With 12 weeks and 7 dishes there are 588 rows, about 490 usable after the first week (no history).
- Every row of week W is a forecast made at the same cutoff, the Sunday ending week W-1.
- Days with no sales row up to the last sales date count as 0 sold.
  Days after the last sales date are unobserved (NaN), never zero, so a partial last week is not treated as a slow week.

### Ratio target

Instead of predicting raw servings, the model predicts a ratio to a baseline.

```
baseline_qty = mean of the same weekday over the last (up to) 4 weeks
ratio        = qty_sold / baseline_qty            (clipped to 0 to 3)
prediction   = baseline_qty x predicted_ratio
```

- All dishes share one scale (about 1.0), so every dish teaches the same lessons and the few rows go further.
- The model only learns corrections to the baseline (deals, trends, traffic).
  With no signal it predicts a ratio of 1 and lands on the baseline.
- Rows are weighted by baseline size, so the ratio loss tracks absolute error in servings and big dishes count more.
- Rows with a zero baseline are not trained on and are predicted as 0.
- The baseline uses only lags of 7 days or more, so it is always available at the cutoff.

### Dish features

| Feature | Definition |
|---|---|
| `dow`, `week_of_year`, `month` | Calendar of the forecast day. |
| `wd_lag_1w_ratio`, `wd_lag_2w_ratio`, `wd_lag_4w_ratio` | Same weekday k weeks earlier divided by the baseline. |
| `wd_cv` | Standard deviation of the available same weekday values divided by the baseline (needs 2 weeks). |
| `mean_7d_ratio`, `mean_28d_ratio` | Average daily quantity over the previous 7 or 28 days, divided by the baseline. |
| `dish_trend_ratio` | 7 day average divided by 28 day average. |
| `restaurant_traffic_ratio` | Total dishes sold last week divided by the mean of the last 4 weeks. |
| `price_vs_hist_4w` | Last week's mean `avg_price` divided by the 4 week mean, a discount proxy from history only. |
| `holiday_flag`, `deal_flag` | A holiday or deal covers the forecast day. |
| `dish_event_flag` | An event lists this dish in `events.items`. |
| `event_discount_pct`, `event_expected_lift` | Largest values among events listing this dish. Holidays without items apply their lift to all dishes. |

Inventory and purchase features are deliberately left out of this model.
They describe ordering behaviour, not customer demand, and they were the top features of the ingredient-level model only because the demo owner buys by a fixed rule.

### Leakage rule

- Same weekday lags are at least 7 days back, so they fall on or before the cutoff.
- Weekly statistics are shifted one week, and partial or unobserved weeks are NaN.
- Only calendar and event features look at the forecast day itself.
- `test_no_leakage_from_current_or_future_days` multiplies all sales from week W onward by 7 and asserts that every feature and baseline in week W is unchanged.

### Split and metrics

The split is the same as before: last 2 weeks test, the 2 before that validation with early stopping, the rest train.
Predictions are converted to ingredient usage and compared per ingredient and week with:

- `dish_baseline_only`: the ratio fixed at 1, the floor the model must beat.
- `naive_last_week`: last week's ingredient usage.
- `mean_4w`: mean of the last 4 weeks of ingredient usage.

`dish_baseline_only` equals `mean_4w` whenever 4 weeks of history exist, because the sum of same weekday means is the mean of the weekly totals.

First result on the demo CSVs (ingredient-week level, test weeks 2026-09-07 and 2026-09-14):

| Model | MAE | WAPE |
|---|---|---|
| dish level XGBoost, ratio target | 4.58 | 0.038 |
| dish baseline only | 6.09 | 0.051 |
| naive last week | 6.20 | 0.052 |
| 4 week mean | 6.09 | 0.051 |

This single split looked good, but it turned out to be a lucky pair of weeks.
The rolling backtest below is the number to trust.

## Rolling backtest and P10 to P90 bands (V1, superseded by the V2 bands above)

`sim/forecast_backtest.py` retrains the dish-level model for every origin week T using only earlier weeks (early stopping on the 2 weeks just before T), forecasts week T, and converts to ingredient usage.
With 12 weeks of data this gives 6 out-of-sample origins and 72 ingredient-weeks.

Accuracy on the demo CSVs across all origins:

| Model | MAE | WAPE |
|---|---|---|
| dish level XGBoost, ratio target | 6.78 | 0.056 |
| dish baseline only (same weekday mean) | 6.96 | 0.057 |
| naive last week | 8.61 | 0.071 |
| 4 week mean | 6.96 | 0.057 |

Reading this honestly:

- XGBoost beats last week's usage clearly and ties the same weekday baseline (0.056 versus 0.057).
- On single weeks it wins some and loses some, so on 12 weeks of data it has not yet shown a reliable edge over its own baseline.
- The demo data has no events in most origin weeks, which is where the model is meant to add value.

### Bands

The forecast is a single number, so uncertainty is added from past errors.

- For each out-of-sample forecast, compute `actual / predicted`.
- Pool these ratios across ingredients (too few per ingredient) and take the 10th, 50th and 90th percentiles.
- Percentiles use a finite-sample (split conformal) rank: `ceil((n + 1) q)` for upper and `floor((n + 1) q)` for lower quantiles, falling back to the sample max or min when n is small.
  A plain percentile of few errors is too narrow on new data, and this correction widens it.
- Multiply a new forecast by those three multipliers to get P10, P50 and P90.
- Errors are relative, so an ingredient used in large quantities gets a proportionally larger band.

Coverage check, where each week's bands use only errors from earlier origins (ideal: 0.80 inside, 0.10 below, 0.10 above):

| Bands | Inside P10 to P90 | Below P10 | Above P90 | Points |
|---|---|---|---|---|
| Plain percentiles | 0.583 | 0.150 | 0.267 | 60 |
| Conformal corrected | 0.683 | 0.133 | 0.183 | 60 |

The correction helps (58% to 68%) but is still under 80%.
Per week the coverage swings from 58% to 92%.
That is because errors are strongly correlated inside a week: a busy week runs high for every ingredient at once, and ingredients like beef patty and bun share the same driver dish.
The 60 points are therefore closer to 5 independent weeks, and the coverage estimate itself is noisy.

The bands are a working first version.
They should not be shown to owners as calibrated until they are re-checked on more weeks.

Ideas to improve coverage, in order:

- Get more history, so bands come from more independent weeks.
- Calibrate bands from dish-day errors, where there are far more independent points, and propagate them to ingredients.
- Widen the bands for weeks with events or holidays, where errors are larger.

## Frontend payload and data status (V1, see the V2 payload above)

`GET /api/forecast?restaurant_id=<restaurants.id>` returns everything a forecast page needs in one response.
Like the other routes it needs a signed in session cookie, and the restaurant must belong to the signed in user (401, 403 or 404 otherwise).
`restaurant_id` is the restaurant UUID, since names are only unique per owner.
It takes under a second on the demo data.
Training runs in a worker thread so it does not block the API event loop.

```
data:        weeks_of_history, first_week, last_week, forecast_week, method, status, message
accuracy:    backtest_weeks, methods{xgboost, dish_baseline, naive_last_week, mean_4w}{mae, wape},
             band_coverage{inside_p10_p90, below_p10, above_p90, n, target_inside}
ingredients: [{ ingredient_id, name, unit,
                history:  [{week, usage}],
                forecast: {week, point, p10, p50, p90},
                backtest: [{week, actual, predicted, p10, p90}] }]
```

- The in-progress week is dropped, so a partial week is never read as a slow week.
  The forecast is for the first week after the last complete week.
- `p10` and `p90` in a backtest row are null for the first origin, which has no earlier errors to build a band from.
- With fewer than 3 usable weeks the model cannot train.
  `method` is then `baseline` (same weekday average), `accuracy` is null and the bands are null.
  This is a necessity for tiny data, not an accuracy based fallback.
- The payload is strict JSON: no NaN, and every missing number is null.

### Data status ("learning mode")

`data.status` and `data.message` tell the UI how much history the forecast rests on.
It is only a label and never changes the forecast.

| Weeks of history | `status` | Meaning |
|---|---|---|
| under 8 | `learning` | Rough estimates, upload older sales. |
| 8 to 25 | `improving` | Getting sharper, upload older sales to unlock seasonal and holiday patterns. |
| 26 or more | `established` | No warning. |

The UI can also compare `band_coverage.inside_p10_p90` with `target_inside` (0.80) to say whether the ranges have been validated.

Not in the payload yet: order quantity, expected waste, stockout risk and savings.
They need the recommendation step (stock on hand, newsvendor rule, shelf life cap, pack rounding).

## How to run

From `backend/`:

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt -r requirements-dev.txt
.venv\Scripts\python -m pytest
.venv\Scripts\python -m sim.train_xgb --restaurant-id "<restaurants.id>"        # ingredient level (V1)
.venv\Scripts\python -m sim.train_dish_xgb --restaurant-id "<restaurants.id>"   # dish level, ratio target (V1b)
.venv\Scripts\python -m sim.forecast_backtest --restaurant-id "<restaurants.id>" # rolling backtest and bands
.venv\Scripts\python -m sim.forecast_backtest --csv-dir data/demo               # same, offline from demo CSVs
```

- `POSTGRES_URL` must be set in `backend/.env` (Neon connection string, never committed).
- Trained models are written to `backend/models/` (`usage_xgb.json` and `dish_ratio_xgb.json`), which is gitignored.

## How to extend

- Add a feature by building a weekly wide frame (index week, columns ingredient), shifting it so W is excluded, and adding it to `frames` and `FEATURE_COLUMNS` in `features.py`.
  Then add a hand-computed test, and check the leakage test still passes.
- When more history exists (26+ weeks), enable the deferred long lags and revisit hyperparameters.
- Purchase recommendation should consume the predicted usage together with `inventory_current`, shelf life and pack size.
  Using `inventory_current` at recommendation time is correct, because that is the live state, unlike in historical training rows.

## Row history and point-in-time lookups

`ingredients` and `recipes` keep their own history, there is no separate log table (see `db/migrations/001_versioned_rows.sql`).
Each row has `valid_from` and `valid_to`, and was in force for `valid_from <= t < valid_to`.
The first version starts at 1900-01-01 so it covers all earlier history.

- **recipes:** a changed quantity ends the current row (`valid_to` set) and adds a new row (`valid_from` = the change time). Removing an ingredient from a dish only ends its row. `valid_to IS NULL` is the current line.
- **ingredients:** when `unit`, `unit_cost`, `pack_size` or `shelf_life_days` change, a copy of the old values is inserted with `valid_to` set and `current_id` pointing at the current row, and the current row is updated in place with the new `valid_from`. The current row (`current_id IS NULL`) keeps its id, so purchases, counts and recipes keep pointing at it. Always filter `current_id IS NULL` when you want the current ingredients.
- **Uploads:** the change time is the upload time, or the optional `effective_date` column (YYYY-MM-DD) in the ingredients and recipes CSVs. An `effective_date` earlier than the row's last change is rejected. Identical re-uploads write nothing. A dish in a recipes upload is treated as fully specified, so ingredients missing from it are ended.

`sim/history.py` turns these rows into "value in force at time T" lookups.
Historical usage (the training target), waste quantity and waste dollars use the recipe and price in force at the time, so an edit never rewrites past weeks.
The forecast for the upcoming week always uses the current values.
Menu prices are not versioned because `sales.avg_price` already records the price at the time of each sale.
