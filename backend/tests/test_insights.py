import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import insights
from app.auth import get_current_user_id
from app.cortex import CortexClient, CortexError, clean
from app.main import app

RUN = {
    "run_at": "2026-09-27T10:00:00+00:00",
    "forecast": {
        "data": {"target_week": "2026-09-28", "weeks_of_history": 12, "message": "Based on 12 weeks.",
                 "method_reason": "XGBoost blended 50/50 with the same-weekday average.",
                 "based_on_sales_through": "2026-09-20"},
        "accuracy": {"methods": {"xgboost": {"wape": 0.058}, "dish_baseline": {"wape": 0.061}, "naive_last_week": {"wape": 0.073}},
                     "band_coverage": {"inside_p10_p90": 0.85, "target_inside": 0.8}, "backtest_weeks": 6},
        "savings": {"delivery_days": ["Monday", "Thursday"], "weekly_expected_vs_habit": 120.5,
                    "order_backtest": {"weeks": 4, "ours": {"waste_cost": 90.0, "lost_margin": 5.0},
                                       "actual": {"waste_cost": 100.0, "lost_margin": 1.0},
                                       "waste_reduction_pct": 10.0, "total_savings": 6.0}},
        "events": [],
        "ingredients": [{
            "name": "Chicken breast", "unit": "kg",
            "history": [{"week": "2026-09-07", "usage": 70.1}, {"week": "2026-09-14", "usage": 66.1}],
            "forecast": {"p10": 57.0, "p50": 73.3, "p90": 96.6, "event_adjustment_pct": 0.0},
            "recommendation": {"order_qty": 85.0, "deliveries": [{"day": "Monday", "qty": 35.0, "firm": True},
                                                                 {"day": "Thursday", "qty": 50.0, "firm": False}],
                               "packs": 17, "pack_size": 5.0, "on_hand": 0.0, "perishable": True,
                               "stockout_risk": 0.1, "expected_waste_cost": 40.0, "habit_order_qty": 85.0,
                               "habit_stockout_risk": 0.25},
        }],
    },
}


def mock_client(handler) -> CortexClient:
    return CortexClient(account="guvzzec_ss98777", token="pat-123", model="claude-sonnet-4-5",
                        transport=httpx.MockTransport(handler))


def test_request_shape_and_account_url():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["Authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "Order 85 kg — fine."}}]})

    text = asyncio.run(mock_client(handler).complete([{"role": "user", "content": "hi"}]))
    assert seen["url"] == "https://guvzzec-ss98777.snowflakecomputing.com/api/v2/cortex/v1/chat/completions"
    assert seen["auth"] == "Bearer pat-123"
    assert seen["body"]["model"] == "claude-sonnet-4-5" and seen["body"]["stream"] is False
    assert text == "Order 85 kg  -  fine."  # em dashes never reach the owner


def test_streaming_yields_text_deltas():
    sse = (
        'data: {"choices":[{"delta":{"content":"Order "}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"85 kg."}}]}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(request):
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})

    async def collect():
        deltas = await mock_client(handler).open_stream([{"role": "user", "content": "hi"}])
        return "".join([d async for d in deltas])

    assert asyncio.run(collect()) == "Order 85 kg."


@pytest.mark.parametrize("status,needle", [(401, "access token"), (403, "CORTEX_USER"), (400, "CROSS_REGION")])
def test_errors_are_explained(status, needle):
    client = mock_client(lambda r: httpx.Response(status, text="unknown model claude"))
    with pytest.raises(CortexError) as err:
        asyncio.run(client.complete([{"role": "user", "content": "hi"}]))
    assert needle in err.value.message


def test_context_holds_only_the_run_numbers():
    ctx = insights.build_context(RUN, "Millbrook Cafe")
    chicken = ctx["ingredients"][0]
    assert ctx["restaurant"] == "Millbrook Cafe" and ctx["target_week_start"] == "2026-09-28"
    assert chicken["last_week_usage"] == 66.1 and chicken["order"]["deliveries"][1] == {"day": "Thursday", "qty": 50.0}
    assert ctx["accuracy"]["range_hit_rate"] == 0.85
    assert ctx["savings"]["order_backtest"]["waste_reduction_pct"] == 10.0


def test_chat_history_is_trimmed_and_must_end_with_the_owner():
    history = [insights.ChatMessage(role="user" if i % 2 == 0 else "assistant", content=f"m{i}") for i in range(15)]
    messages = insights.chat_messages({"x": 1}, history)
    assert messages[0]["role"] == "system" and "CONTEXT:" in messages[0]["content"]
    assert len(messages) == 1 + insights.MAX_TURNS and messages[-1]["content"] == "m14"
    with pytest.raises(Exception):
        insights.chat_messages({"x": 1}, history[:-1])


@pytest.fixture
def api(monkeypatch):
    async def owner(restaurant_id, user_id):
        return None

    async def latest(restaurant_id):
        return RUN, "Millbrook Cafe"

    monkeypatch.setattr(insights, "verify_restaurant_owner", owner)
    monkeypatch.setattr(insights, "_latest", latest)
    app.dependency_overrides[get_current_user_id] = lambda: "u1"
    insights._summary_cache.clear()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_summary_needs_configuration(api, monkeypatch):
    monkeypatch.setattr(insights, "CortexClient", lambda: CortexClient(account="", token=""))
    r = api.post("/api/insights/summary", params={"restaurant_id": "r1"})
    assert r.status_code == 503 and "SNOWFLAKE_PAT" in r.json()["detail"]


def test_summary_is_generated_then_cached(api, monkeypatch):
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "Order 85 kg of chicken."}}]})

    monkeypatch.setattr(insights, "CortexClient", lambda: mock_client(handler))
    first = api.post("/api/insights/summary", params={"restaurant_id": "r1"}).json()
    second = api.post("/api/insights/summary", params={"restaurant_id": "r1"}).json()
    assert first["summary"] == "Order 85 kg of chicken." and not first["cached"] and second["cached"]
    assert len(calls) == 1 and "Chicken breast" in calls[0]["messages"][0]["content"]


def test_chat_streams_the_answer(api, monkeypatch):
    sse = 'data: {"choices":[{"delta":{"content":"Because Friday is busy."}}]}\n\ndata: [DONE]\n\n'
    monkeypatch.setattr(insights, "CortexClient", lambda: mock_client(lambda r: httpx.Response(200, text=sse)))
    r = api.post(
        "/api/insights/chat", params={"restaurant_id": "r1"},
        json={"messages": [{"role": "user", "content": "Why so much chicken?"}]},
    )
    assert r.status_code == 200 and r.text == "Because Friday is busy."


def test_chat_surfaces_cortex_errors(api, monkeypatch):
    monkeypatch.setattr(insights, "CortexClient", lambda: mock_client(lambda r: httpx.Response(403, text="denied")))
    r = api.post("/api/insights/chat", params={"restaurant_id": "r1"}, json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 502 and "CORTEX_USER" in r.json()["detail"]


def test_clean_replaces_dashes():
    assert clean("a—b–c") == "a - b-c"
