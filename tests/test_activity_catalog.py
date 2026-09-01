import pytest

from core import activity_catalog
from core.activity_catalog import (
    ActivityCatalogError,
    get_activity_options,
    get_point_value,
    load_activity_catalog,
)
from core.sheets_client import SheetsError

RECORDS = [
    {"Activity Code": "P01", "Category": "Participation", "Activity Name": "Attending LO Meetings", "Points": 3},
    {"Activity Code": "P02", "Category": "Participation", "Activity Name": "Attending Trainings", "Points": 5},
]


def test_load_activity_catalog_success(monkeypatch):
    monkeypatch.setattr(activity_catalog.sheets_client, "read_all_records", lambda tab: RECORDS)
    assert load_activity_catalog() == RECORDS


def test_load_activity_catalog_raises_on_sheets_error(monkeypatch):
    def _raise(tab):
        raise SheetsError("boom")

    monkeypatch.setattr(activity_catalog.sheets_client, "read_all_records", _raise)
    with pytest.raises(ActivityCatalogError):
        load_activity_catalog()


def test_load_activity_catalog_empty_raises(monkeypatch):
    monkeypatch.setattr(activity_catalog.sheets_client, "read_all_records", lambda tab: [])
    with pytest.raises(ActivityCatalogError):
        load_activity_catalog()


def test_load_activity_catalog_missing_columns_raises(monkeypatch):
    monkeypatch.setattr(
        activity_catalog.sheets_client,
        "read_all_records",
        lambda tab: [{"Activity Name": "X"}],  # no Points column
    )
    with pytest.raises(ActivityCatalogError):
        load_activity_catalog()


def test_get_activity_options_dedupes_and_preserves_order():
    records = RECORDS + [{"Activity Name": "Attending LO Meetings", "Points": 3}]
    assert get_activity_options(records) == ["Attending LO Meetings", "Attending Trainings"]


def test_get_point_value_found_case_insensitive():
    assert get_point_value(RECORDS, "attending lo meetings") == 3.0


def test_get_point_value_not_found_raises():
    with pytest.raises(ActivityCatalogError):
        get_point_value(RECORDS, "Nonexistent Activity")


def test_get_point_value_non_numeric_raises():
    records = [{"Activity Name": "X", "Points": "not-a-number"}]
    with pytest.raises(ActivityCatalogError):
        get_point_value(records, "X")
