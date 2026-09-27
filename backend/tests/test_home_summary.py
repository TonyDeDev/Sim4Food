from datetime import date

from sim.home_summary import build_next_event, build_revenue, build_stock, build_waste, runway_days
from sim.waste import build_waste_report


def test_revenue_window_anchors_to_latest_sale_not_today():
    sales = [
        {"date": date(2026, 1, d), "qty_sold": 2.0, "avg_price": 10.0} for d in range(1, 15)
    ]
    out = build_revenue(sales)
    assert out["as_of"] == "2026-01-14"
    assert out["last7"] == 140.0  # days 8-14, 7 * 2 * 10
    assert out["prev7"] == 140.0  # days 1-7
    assert out["change_pct"] == 0.0
    assert len(out["daily"]) == 7


def test_revenue_change_pct_and_empty_case():
    assert build_revenue([]) == {"last7": 0.0, "prev7": 0.0, "change_pct": None, "daily": [], "as_of": None}

    sales = [
        {"date": date(2026, 1, 1), "qty_sold": 1.0, "avg_price": 100.0},
        {"date": date(2026, 1, 8), "qty_sold": 2.0, "avg_price": 100.0},
    ]
    out = build_revenue(sales)
    assert out["prev7"] == 100.0
    assert out["last7"] == 200.0
    assert out["change_pct"] == 100.0


def _waste_report():
    ingredients = [{"id": "i1", "external_id": "beef", "name": "Beef", "unit_cost": 10.0}]
    purchases = [
        {"ingredient_id": "i1", "date": date(2026, 6, 29), "qty": 10.0},
        {"ingredient_id": "i1", "date": date(2026, 7, 6), "qty": 5.0},
    ]
    consumption = [
        {"ingredient_id": "i1", "date": date(2026, 6, 29), "qty": 4.0},
        {"ingredient_id": "i1", "date": date(2026, 7, 6), "qty": 4.0},
    ]
    return build_waste_report(ingredients, purchases, [], consumption)


def test_waste_summary_uses_latest_week_and_names_top_ingredient():
    out = build_waste(_waste_report())
    assert out["week_start"] == "2026-07-06"
    assert out["last_week_cost"] == 10.0  # (5 - 4) * 10
    assert out["prev_week_cost"] == 60.0  # (10 - 4) * 10
    assert out["change_pct"] < 0
    assert out["top_ingredient"] == "Beef"


def test_waste_summary_empty():
    out = build_waste({"by_ingredient": []})
    assert out["last_week_cost"] == 0.0
    assert out["top_ingredient"] is None
    assert out["week_start"] is None


def test_runway_days_needs_both_qty_and_usage():
    assert runway_days({"qty_on_hand": 10, "avg_daily_consumption": 2}) == 5
    assert runway_days({"qty_on_hand": None, "avg_daily_consumption": 2}) is None
    assert runway_days({"qty_on_hand": 10, "avg_daily_consumption": 0}) is None


def test_stock_summary_flags_out_and_low_and_prices_value():
    report = {
        "ingredients": [
            {"ingredient_id": "a", "name": "A", "qty_on_hand": 0.0, "avg_daily_consumption": 1.0},
            {"ingredient_id": "b", "name": "B", "qty_on_hand": 2.0, "avg_daily_consumption": 1.0},  # 2 days left
            {"ingredient_id": "c", "name": "C", "qty_on_hand": 100.0, "avg_daily_consumption": 1.0},  # fine
            {"ingredient_id": "d", "name": "D", "qty_on_hand": None, "avg_daily_consumption": 0.0},  # unknown
        ],
        "summary": {"total": 4, "tracked": 3, "missing_count": 1},
    }
    out = build_stock(report, {"a": 5.0, "b": 2.0, "c": 1.0})
    assert out["out_count"] == 1
    assert out["low_count"] == 1
    assert out["stock_value"] == 0.0 * 5.0 + 2.0 * 2.0 + 100.0 * 1.0
    # A is fully out (0 days left), more urgent than B's 2 days.
    assert out["most_urgent"] == "A"
    assert out["most_urgent_days"] == 0.0


def test_next_event_picks_soonest_upcoming_and_ignores_past():
    today = date(2026, 6, 1)
    events = [
        {"type": "deal", "name": "Past deal", "start_date": date(2026, 5, 1), "end_date": date(2026, 5, 5),
         "discount_pct": 10.0, "expected_lift": 5.0},
        {"type": "holiday", "name": "Founders Day", "start_date": date(2026, 6, 10), "end_date": date(2026, 6, 10),
         "discount_pct": None, "expected_lift": None},
    ]
    out = build_next_event(events, today)
    assert out["name"] == "Founders Day"
    assert out["days_until"] == 9

    assert build_next_event([], today) is None
