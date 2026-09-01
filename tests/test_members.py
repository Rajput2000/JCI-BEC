import pytest

from core import members
from core.members import (
    MembersLoadError,
    load_member_directory_records,
    load_standard_members,
)
from core.sheets_client import SheetsError


@pytest.fixture(autouse=True)
def _sheets_unavailable(monkeypatch):
    """Forces Sheets 'not configured' by default so the CSV/secrets-focused
    tests below are deterministic regardless of whatever real
    service_account.json / GOOGLE_SHEET_ID happen to exist on the machine
    running these tests. Tests that specifically exercise the Sheets-first
    path override this with their own monkeypatch."""

    def _raise(*args, **kwargs):
        raise SheetsError("not configured (test)")

    monkeypatch.setattr(members.sheets_client, "read_all_records", _raise)


def test_valid_csv(tmp_path):
    csv_path = tmp_path / "members.csv"
    csv_path.write_text("name\nAda Lovelace\nAlan Turing\nAda Lovelace\n")
    names = load_standard_members(csv_path)
    assert names == ["Ada Lovelace", "Alan Turing"]  # duplicates dropped, order kept


def test_missing_file(tmp_path):
    with pytest.raises(MembersLoadError):
        load_standard_members(tmp_path / "does_not_exist.csv")


def test_empty_csv(tmp_path):
    csv_path = tmp_path / "members.csv"
    csv_path.write_text("name\n")
    with pytest.raises(MembersLoadError):
        load_standard_members(csv_path)


def test_missing_name_column(tmp_path):
    csv_path = tmp_path / "members.csv"
    csv_path.write_text("full_name\nAda Lovelace\n")
    with pytest.raises(MembersLoadError):
        load_standard_members(csv_path)


def test_reads_from_streamlit_secrets_when_present(monkeypatch, tmp_path):
    # Simulates a Streamlit Community Cloud deployment: secrets are set, so
    # the roster should come from there even if a (wrong) file path is given.
    monkeypatch.setattr(
        members.st,
        "secrets",
        {"data": {"standard_members_csv": "name\nAda Lovelace\nAlan Turing\n"}},
    )
    names = load_standard_members(tmp_path / "does_not_exist.csv")
    assert names == ["Ada Lovelace", "Alan Turing"]


def test_falls_back_to_file_when_no_secrets(monkeypatch, tmp_path):
    monkeypatch.setattr(members.st, "secrets", {})
    csv_path = tmp_path / "members.csv"
    csv_path.write_text("name\nAda Lovelace\n")
    names = load_standard_members(csv_path)
    assert names == ["Ada Lovelace"]


def test_reads_from_sheets_when_configured(monkeypatch, tmp_path):
    # Sheets should take priority even when secrets/file would give
    # different data — it's the primary source now.
    monkeypatch.setattr(
        members.sheets_client,
        "read_all_records",
        lambda tab: [{"Member Code": "001", "Member Name": "Ada Lovelace", "Location": "Lagos"}],
    )
    csv_path = tmp_path / "members.csv"
    csv_path.write_text("name\nSomeone Else\n")
    names = load_standard_members(csv_path)
    assert names == ["Ada Lovelace"]


def test_falls_back_to_secrets_when_sheets_unavailable(monkeypatch):
    # The autouse fixture already makes Sheets raise; this makes the
    # fallback explicit rather than just implied by the other CSV tests.
    monkeypatch.setattr(
        members.st,
        "secrets",
        {"data": {"standard_members_csv": "name\nAda Lovelace\n"}},
    )
    names = load_standard_members()
    assert names == ["Ada Lovelace"]


def test_load_member_directory_records_success(monkeypatch):
    records = [
        {"Member Code": "001", "Member Name": "Ada Lovelace", "Location": "Lagos", "Family Unit": "JCI Sen. X"},
    ]
    monkeypatch.setattr(members.sheets_client, "read_all_records", lambda tab: records)
    assert load_member_directory_records() == records


def test_load_member_directory_records_raises_on_sheets_error(monkeypatch):
    def _raise(tab):
        raise SheetsError("boom")

    monkeypatch.setattr(members.sheets_client, "read_all_records", _raise)
    with pytest.raises(MembersLoadError):
        load_member_directory_records()


def test_load_member_directory_records_missing_columns_raises(monkeypatch):
    monkeypatch.setattr(
        members.sheets_client,
        "read_all_records",
        lambda tab: [{"Member Name": "Ada Lovelace"}],  # no Location/Family Unit
    )
    with pytest.raises(MembersLoadError):
        load_member_directory_records()


def test_load_member_directory_records_empty_raises(monkeypatch):
    monkeypatch.setattr(members.sheets_client, "read_all_records", lambda tab: [])
    with pytest.raises(MembersLoadError):
        load_member_directory_records()
