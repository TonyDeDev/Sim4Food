from sim.ingest import parse_csv_rows, validate_upload


def test_parses_plain_utf8():
    raw = "date,item_id,qty_sold,avg_price\n2026-09-20,classic_burger,12,9.50\n".encode("utf-8")
    assert parse_csv_rows(raw) == [
        {"date": "2026-09-20", "item_id": "classic_burger", "qty_sold": "12", "avg_price": "9.50"},
    ]


def test_strips_the_bom_excel_writes_for_utf8_csv():
    raw = "﻿date,item_id\n2026-09-20,classic_burger\n".encode("utf-8")
    assert list(parse_csv_rows(raw)[0].keys()) == ["date", "item_id"]  # not ["﻿date", ...]


def test_falls_back_to_cp1252_for_excels_plain_csv_export():
    """Excel's "CSV (Comma delimited)" export on Windows writes cp1252, not
    UTF-8. A curly quote, em dash, or accented letter - easy to pick up from
    autocorrect or a pasted dish name - is then a byte plain UTF-8 decoding
    rejects; this used to reach main.py's raw.decode("utf-8-sig") unguarded
    and crash the whole request with a 500 instead of a validation message.
    """
    text = "date,item_id,qty_sold,avg_price\n2026-09-20,today’s_special,4,11.00\n"
    raw = text.encode("cp1252")
    with_assertion_error = False
    try:
        raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        with_assertion_error = True
    assert with_assertion_error, "fixture must reproduce the original crash"

    rows = parse_csv_rows(raw)
    assert rows == [{"date": "2026-09-20", "item_id": "today’s_special", "qty_sold": "4", "avg_price": "11.00"}]


def test_falls_back_to_latin1_when_even_cp1252_rejects_the_byte():
    """cp1252 is not total: 0x81, 0x8D, 0x8F, 0x90 and 0x9D are undefined in
    it and still raise UnicodeDecodeError. This is the actual byte an upload
    hit in production (0x9D at a fixed position, wherever it came from) - the
    cp1252 fallback alone still 500'd on it. latin-1 maps all 256 byte
    values, so it is the true backstop, tried only once cp1252 has failed.
    """
    for bad_byte in (0x81, 0x8D, 0x8F, 0x90, 0x9D):
        raw = f"a,b\n1,x{chr(bad_byte)}y\n".encode("latin-1")
        for encoding in ("utf-8-sig", "cp1252"):
            try:
                raw.decode(encoding)
                raise AssertionError(f"fixture byte {bad_byte:#x} must reject both prior encodings")
            except UnicodeDecodeError:
                pass
        assert parse_csv_rows(raw) == [{"a": "1", "b": f"x{chr(bad_byte)}y"}]


def test_unreadable_upload_still_degrades_to_an_ordinary_validation_error():
    """latin-1 never raises, so a genuinely non-CSV upload (a spreadsheet or
    image dropped in by mistake) must still be caught by validate_upload's
    normal checks afterward, not crash."""
    png_header = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x01, 0x02])
    rows = parse_csv_rows(png_header)
    assert validate_upload("sales", rows)["status"] == "error"
