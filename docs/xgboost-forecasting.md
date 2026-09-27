# XGBoost ingredient usage forecasting

## Purpose and scope

This document describes the V1 XGBoost forecasting layer for SwarmStock.
It predicts next week's theoretical usage of each ingredient from POS sales and recipes stored in Neon.
The prediction is the input to the purchase recommendation step, which is not part of this work.

Pipeline:

```
sales -> menu_items -> recipes -> ingredients
  -> daily theoretical ingredient usage
  -> weekly point-in-time features
  -> XGBoost
  -> next-week ingredient usage
  -> (later) inventory + purchases + pack size -> purchase recommendation
```

The primary target is usage, not purchase quantity.
Historical purchases are not necessarily what the restaurant needed, so they are used as features only.

## Code map

| File | Role |
|---|---|
| `backend/sim/dataset.py` | Async loader: pulls one restaurant's tables from Postgres into pandas frames with string ids. |
| `backend/sim/features.py` | Pure pandas point-in-time feature matrix (`build_feature_matrix`). |
| `backend/sim/train_xgb.py` | CLI: build matrix, chronological split, fit, report metrics against baselines, save model. |
| `backend/sim/dish_features.py` | Daily dish-level point-in-time matrix with a ratio target (`build_dish_matrix`). |
| `backend/sim/train_dish_xgb.py` | CLI: train the dish-level model, convert to ingredient usage, evaluate, print next week forecast. |
| `backend/tests/test_features.py` | Unit tests for the ingredient-level matrix, including leakage tests. |
| `backend/sim/forecast_backtest.py` | CLI: rolling-origin backtest, residual P10/P50/P90 bands, coverage check, next week forecast with bands. |
| `backend/sim/forecast_payload.py` | Builds the JSON payload for the frontend: history, forecast with bands, backtest, data status. |
| `backend/app/main.py` | Adds `GET /api/forecast?restaurant_id=<uuid>`, protected by the same session and ownership check as the other routes. |
| `backend/tests/test_dish_features.py` | Unit tests for the dish-level matrix, including leakage tests. |
| `backend/tests/test_forecast_backtest.py` | Unit tests for bands, coverage and leakage in the rolling backtest. |

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
| `unit_cost`, `pack_size`, `shelf_life_days` | ingredients | Static ingredient attributes. |

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

## Dish-level daily model (V1b, preferred)

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

## Rolling backtest and P10 to P90 bands

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

## Frontend payload and data status

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
