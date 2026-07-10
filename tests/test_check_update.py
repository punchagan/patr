"""Tests for GET /api/check-update."""

from unittest.mock import patch

import pytest
from patr import server


@pytest.fixture
def client():
    server.app.config["TESTING"] = True
    server.app.config["PORT"] = 5000
    with server.app.test_client() as c:
        yield c


def test_check_update_reports_available(client) -> None:
    with patch(
        "patr.server.check_for_update",
        return_value={"update_available": True, "local": "old", "latest": "new"},
    ):
        r = client.get("/api/check-update")
    assert r.status_code == 200
    assert r.get_json() == {
        "update_available": True,
        "local": "old",
        "latest": "new",
    }


def test_check_update_reports_up_to_date(client) -> None:
    with patch(
        "patr.server.check_for_update",
        return_value={"update_available": False, "local": "same", "latest": "same"},
    ):
        r = client.get("/api/check-update")
    assert r.status_code == 200
    assert r.get_json()["update_available"] is False
