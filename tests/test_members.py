import pytest

from core import members
from core.members import MembersLoadError, load_standard_members


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
