"""The /api/upload response's `status` is what the record cards believe.

A file can pass column validation and still persist nothing - recipes naming a
dish or an ingredient whose own file has not been uploaded yet resolve to no
row. Those failures are per row, and the endpoint has to fold them into
`status`, or the card shows the file as accepted while the database has none of
it and the forecast goes on asking for the same file.
"""
import pytest
from fastapi.testclient import TestClient

from app import main, repository
from app.auth import get_current_user_id
from app.main import app


@pytest.fixture
def api(monkeypatch):
    async def owns_it(restaurant_id, user_id):
        return None

    monkeypatch.setattr(main, "verify_restaurant_owner", owns_it)
    monkeypatch.setattr(main.db, "get_pool", lambda: None)
    app.dependency_overrides[get_current_user_id] = lambda: "u1"
    yield TestClient(app)
    app.dependency_overrides.clear()


def upload(api, file_type, body, name="f.csv"):
    return api.post(
        "/api/upload",
        params={"restaurant_id": "r1", "file_type": file_type},
        files={"file": (name, body, "text/csv")},
    )


def fake_persist(monkeypatch, errors):
    async def persist(pool, restaurant_id, file_type, file_name, rows):
        return {"batch_id": "b1", "errors": list(errors)}

    monkeypatch.setattr(repository, "persist_upload", persist)


RECIPES = b"item_id,ingredient_id,qty_per_serving\nburger,beef,0.2\n"


def test_unresolved_rows_make_the_upload_an_error(api, monkeypatch):
    fake_persist(monkeypatch, ["unknown item_id (upload menu first): burger"])
    body = upload(api, "recipes", RECIPES).json()
    assert body["status"] == "error"
    # The client shows errors[0], so it has to name the file to upload first.
    assert body["errors"] == ["unknown item_id (upload menu first): burger"]


def test_a_fully_stored_upload_is_still_ok(api, monkeypatch):
    fake_persist(monkeypatch, [])
    body = upload(api, "recipes", RECIPES).json()
    assert body["status"] == "ok" and body["errors"] == [] and body["row_count"] == 1


def test_column_validation_still_fails_before_anything_is_written(api, monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("must not persist a file that failed validation")

    monkeypatch.setattr(repository, "persist_upload", explode)
    body = upload(api, "recipes", b"item_id,ingredient_id,qty_per_serving\nburger,beef,nope\n").json()
    assert body["status"] == "error"
    assert "qty_per_serving is not numeric" in body["errors"][0]
