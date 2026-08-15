from core.pasted_names import parse_pasted_names


def test_splits_on_newlines():
    assert parse_pasted_names("John Doe\nJane Smith\n") == ["John Doe", "Jane Smith"]


def test_splits_on_commas():
    assert parse_pasted_names("John Doe, Jane Smith,Bob Nobody") == [
        "John Doe",
        "Jane Smith",
        "Bob Nobody",
    ]


def test_mixed_separators_and_blank_lines():
    text = "John Doe\n\n, Jane Smith ,\nBob Nobody\n"
    assert parse_pasted_names(text) == ["John Doe", "Jane Smith", "Bob Nobody"]


def test_empty_input():
    assert parse_pasted_names("") == []
    assert parse_pasted_names("   \n \n") == []
