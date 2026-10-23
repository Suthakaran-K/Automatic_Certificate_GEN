import pandas as pd
from spreadsheet_service import normalize_type, valid_email, parse_spreadsheet

def test_certificate_type_variants():
    assert normalize_type("Participation Certificate") == "Participation"
    assert normalize_type("1st Prize") == "First Prize"
    assert normalize_type("First Prize") == "First Prize"
    assert normalize_type("2nd Prize") == "Second Prize"
    assert normalize_type("Second Prize") == "Second Prize"
    assert normalize_type("mystery") is None

def test_email_validation():
    assert valid_email("person@example.com")
    assert not valid_email("not-an-email")

def test_missing_columns(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("Name,Email\nA,a@example.com\n", encoding="utf-8")
    try:
        parse_spreadsheet(path)
        assert False, "Expected missing-column validation error"
    except ValueError as exc:
        assert "Missing required column" in str(exc)

def test_valid_and_invalid_rows(tmp_path):
    path = tmp_path / "participants.csv"
    path.write_text("Name,Email,Event Name,Certificate Type\nA,a@example.com,Event,Participation\nB,bad,Event,Unknown\n", encoding="utf-8")
    result = parse_spreadsheet(path)
    assert result["rows"][0]["valid"] is True
    assert result["rows"][1]["valid"] is False
