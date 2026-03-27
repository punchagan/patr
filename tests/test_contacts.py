"""Tests for contact filtering and deduplication logic."""
from unittest.mock import MagicMock, patch
from patr.contacts import fetch_contacts, get_already_sent


def make_sheets_mock(rows):
    """Return a mock Google Sheets service that yields the given rows."""
    mock_service = MagicMock()
    mock_service.spreadsheets().values().get().execute.return_value = {"values": rows}
    return mock_service


# fetch_contacts — filtering

def test_fetch_contacts_includes_blank_send():
    rows = [["Name", "Email", "Send"], ["Alice", "alice@example.com", ""]]
    with patch("patr.contacts.build", return_value=make_sheets_mock(rows)):
        contacts = fetch_contacts("sheet_id", None)
    assert len(contacts) == 1
    assert contacts[0]["email"] == "alice@example.com"


def test_fetch_contacts_excludes_send_n():
    rows = [["Name", "Email", "Send"], ["Bob", "bob@example.com", "n"]]
    with patch("patr.contacts.build", return_value=make_sheets_mock(rows)):
        contacts = fetch_contacts("sheet_id", None)
    assert contacts == []


def test_fetch_contacts_excludes_send_no():
    rows = [["Name", "Email", "Send"], ["Bob", "bob@example.com", "no"]]
    with patch("patr.contacts.build", return_value=make_sheets_mock(rows)):
        contacts = fetch_contacts("sheet_id", None)
    assert contacts == []


def test_fetch_contacts_excludes_case_insensitive():
    rows = [
        ["Name", "Email", "Send"],
        ["Bob", "bob@example.com", "N"],
        ["Carol", "carol@example.com", "NO"],
    ]
    with patch("patr.contacts.build", return_value=make_sheets_mock(rows)):
        contacts = fetch_contacts("sheet_id", None)
    assert contacts == []


def test_fetch_contacts_includes_send_y():
    rows = [["Name", "Email", "Send"], ["Dave", "dave@example.com", "y"]]
    with patch("patr.contacts.build", return_value=make_sheets_mock(rows)):
        contacts = fetch_contacts("sheet_id", None)
    assert len(contacts) == 1


def test_fetch_contacts_excludes_missing_email():
    rows = [["Name", "Email", "Send"], ["Nobody", "", ""]]
    with patch("patr.contacts.build", return_value=make_sheets_mock(rows)):
        contacts = fetch_contacts("sheet_id", None)
    assert contacts == []


def test_fetch_contacts_trims_whitespace():
    rows = [["Name", "Email", "Send"], ["Eve", "  eve@example.com  ", ""]]
    with patch("patr.contacts.build", return_value=make_sheets_mock(rows)):
        contacts = fetch_contacts("sheet_id", None)
    assert contacts[0]["email"] == "eve@example.com"


def test_fetch_contacts_empty_sheet():
    rows = [["Name", "Email", "Send"]]
    with patch("patr.contacts.build", return_value=make_sheets_mock(rows)):
        contacts = fetch_contacts("sheet_id", None)
    assert contacts == []


def test_fetch_contacts_no_rows():
    with patch("patr.contacts.build", return_value=make_sheets_mock([])):
        contacts = fetch_contacts("sheet_id", None)
    assert contacts == []


def test_fetch_contacts_mixed():
    rows = [
        ["Name", "Email", "Send"],
        ["Alice", "alice@example.com", ""],
        ["Bob", "bob@example.com", "n"],
        ["Carol", "carol@example.com", "y"],
        ["Dave", "dave@example.com", "no"],
    ]
    with patch("patr.contacts.build", return_value=make_sheets_mock(rows)):
        contacts = fetch_contacts("sheet_id", None)
    emails = [c["email"] for c in contacts]
    assert "alice@example.com" in emails
    assert "carol@example.com" in emails
    assert "bob@example.com" not in emails
    assert "dave@example.com" not in emails


# get_already_sent — deduplication

def make_sent_log_mock(rows):
    mock_service = MagicMock()
    mock_service.spreadsheets().values().get().execute.return_value = {"values": rows}
    return mock_service


def test_get_already_sent_returns_emails_for_slug():
    rows = [
        ["email", "slug", "sent_at"],
        ["alice@example.com", "my-edition", "2024-01-01 10:00 UTC"],
    ]
    with patch("patr.contacts.build", return_value=make_sent_log_mock(rows)):
        sent = get_already_sent("sheet_id", None, "my-edition")
    assert "alice@example.com" in sent


def test_get_already_sent_excludes_other_slugs():
    rows = [
        ["email", "slug", "sent_at"],
        ["alice@example.com", "other-edition", "2024-01-01 10:00 UTC"],
    ]
    with patch("patr.contacts.build", return_value=make_sent_log_mock(rows)):
        sent = get_already_sent("sheet_id", None, "my-edition")
    assert "alice@example.com" not in sent


def test_get_already_sent_is_case_insensitive():
    rows = [
        ["email", "slug", "sent_at"],
        ["Alice@Example.COM", "my-edition", "2024-01-01 10:00 UTC"],
    ]
    with patch("patr.contacts.build", return_value=make_sent_log_mock(rows)):
        sent = get_already_sent("sheet_id", None, "my-edition")
    assert "alice@example.com" in sent


def test_get_already_sent_empty_log():
    rows = [["email", "slug", "sent_at"]]
    with patch("patr.contacts.build", return_value=make_sent_log_mock(rows)):
        sent = get_already_sent("sheet_id", None, "my-edition")
    assert sent == set()


def test_get_already_sent_returns_empty_on_api_error():
    mock_service = MagicMock()
    mock_service.spreadsheets().values().get().execute.side_effect = Exception("API error")
    with patch("patr.contacts.build", return_value=mock_service):
        sent = get_already_sent("sheet_id", None, "my-edition")
    assert sent == set()


def test_get_already_sent_multiple_slugs():
    rows = [
        ["email", "slug", "sent_at"],
        ["alice@example.com", "edition-1", "2024-01-01 10:00 UTC"],
        ["bob@example.com", "edition-2", "2024-01-02 10:00 UTC"],
        ["carol@example.com", "edition-1", "2024-01-01 11:00 UTC"],
    ]
    with patch("patr.contacts.build", return_value=make_sent_log_mock(rows)):
        sent = get_already_sent("sheet_id", None, "edition-1")
    assert "alice@example.com" in sent
    assert "carol@example.com" in sent
    assert "bob@example.com" not in sent
