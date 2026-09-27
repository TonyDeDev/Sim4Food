import asyncio
from datetime import date

from app import repository
from sim.ingest import validate_upload
from tests.test_repository_changes import FakeConn


class EventsConn(FakeConn):
    async def execute(self, sql, *args):
        self.executed.append((" ".join(sql.split()), [args]))


def event(**kw):
    return {
        "start_date": "2026-10-09", "end_date": "2026-10-11", "type": "deal", "name": "Pasta Special",
        "items": "burger, wrap", "discount_pct": "20", "expected_lift": "", **kw,
    }


def test_events_validate_type_dates_and_optional_columns():
    assert validate_upload("events", [event()])["status"] == "ok"
    assert validate_upload("events", [event(items="", discount_pct="", type="holiday")])["status"] == "ok"
    bad = validate_upload("events", [event(type="party"), event(end_date="2026-10-01")])
    assert bad["status"] == "error"
    assert "type must be holiday or deal" in bad["errors"][0]
    assert "end_date is before start_date" in bad["errors"][1]


def test_events_replace_the_list_and_map_items_to_menu_ids():
    conn = EventsConn()
    errors = asyncio.run(repository.insert_events(conn, "r1", [event(), event(name="Labour Day", type="Holiday", items="")]))
    assert errors == []
    assert conn.executed[0][0].startswith("DELETE FROM events")
    inserts = conn.writes("INSERT INTO events")
    assert inserts[0] == ("r1", "deal", "Pasta Special", date(2026, 10, 9), date(2026, 10, 11), ["m-burger", "m-wrap"], 0.2, None)
    assert inserts[1][1] == "holiday" and inserts[1][5] == []


def test_unknown_items_write_nothing():
    conn = EventsConn()
    errors = asyncio.run(repository.insert_events(conn, "r1", [event(items="burger, pizza")]))
    assert errors and "pizza" in errors[0]
    assert conn.executed == []
