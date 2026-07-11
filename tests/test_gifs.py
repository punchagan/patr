"""Tests for resolving and downloading GIFs pasted from Tenor/Giphy links."""

from unittest.mock import MagicMock, patch

from patr import gifs

# --- _is_allowed_host ---


def test_is_allowed_host_true_for_tenor() -> None:
    assert gifs._is_allowed_host("https://tenor.com/view/cat-123") is True


def test_is_allowed_host_true_for_tenor_subdomain() -> None:
    assert gifs._is_allowed_host("https://media.tenor.com/abc.gif") is True


def test_is_allowed_host_true_for_giphy() -> None:
    assert gifs._is_allowed_host("https://giphy.com/gifs/cat-123") is True


def test_is_allowed_host_false_for_other_domain() -> None:
    assert gifs._is_allowed_host("https://evil.com/cat.gif") is False


def test_is_allowed_host_false_for_lookalike_domain() -> None:
    assert gifs._is_allowed_host("https://eviltenor.com/cat.gif") is False


# --- resolve_media_url ---


def test_resolve_media_url_returns_direct_media_unchanged() -> None:
    with patch("urllib.request.urlopen") as mock_urlopen:
        result = gifs.resolve_media_url("https://media.tenor.com/abc.gif")
    assert result == "https://media.tenor.com/abc.gif"
    mock_urlopen.assert_not_called()


def test_resolve_media_url_none_for_disallowed_host() -> None:
    with patch("urllib.request.urlopen") as mock_urlopen:
        result = gifs.resolve_media_url("https://evil.com/cat.gif")
    assert result is None
    mock_urlopen.assert_not_called()


def _mock_html_response(html: str) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.read.return_value = html.encode()
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False
    return mock_resp


def test_resolve_media_url_scrapes_og_image_from_share_page() -> None:
    html = '<html><head><meta property="og:image" content="https://media.tenor.com/xyz.gif"></head></html>'
    with patch("urllib.request.urlopen", return_value=_mock_html_response(html)):
        result = gifs.resolve_media_url("https://tenor.com/view/cat-123")
    assert result == "https://media.tenor.com/xyz.gif"


def test_resolve_media_url_none_when_og_image_missing() -> None:
    html = "<html><head></head></html>"
    with patch("urllib.request.urlopen", return_value=_mock_html_response(html)):
        result = gifs.resolve_media_url("https://tenor.com/view/cat-123")
    assert result is None


def test_resolve_media_url_none_on_fetch_failure() -> None:
    with patch("urllib.request.urlopen", side_effect=OSError("offline")):
        result = gifs.resolve_media_url("https://tenor.com/view/cat-123")
    assert result is None


def test_resolve_media_url_none_when_og_image_is_disallowed_host() -> None:
    html = '<html><head><meta property="og:image" content="https://evil.com/xyz.gif"></head></html>'
    with patch("urllib.request.urlopen", return_value=_mock_html_response(html)):
        result = gifs.resolve_media_url("https://tenor.com/view/cat-123")
    assert result is None


# --- download_gif ---


def test_download_gif_none_when_media_url_cannot_be_resolved(tmp_path) -> None:
    with patch("patr.gifs.resolve_media_url", return_value=None):
        result = gifs.download_gif("https://evil.com/cat.gif", tmp_path)
    assert result is None
    assert list(tmp_path.glob("*.gif")) == []


def test_download_gif_saves_file_and_returns_filename(tmp_path) -> None:
    body = b"GIF89a-fake-bytes"
    mock_resp = MagicMock()
    mock_resp.read.return_value = body
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False
    with (
        patch(
            "patr.gifs.resolve_media_url",
            return_value="https://media.tenor.com/xyz.gif",
        ),
        patch("urllib.request.urlopen", return_value=mock_resp),
    ):
        filename = gifs.download_gif("https://tenor.com/view/cat-123", tmp_path)
    assert filename is not None
    assert filename.endswith(".gif")
    saved = tmp_path / filename
    assert saved.exists()
    assert saved.read_bytes() == body


def test_download_gif_none_on_download_failure(tmp_path) -> None:
    with (
        patch(
            "patr.gifs.resolve_media_url",
            return_value="https://media.tenor.com/xyz.gif",
        ),
        patch("urllib.request.urlopen", side_effect=OSError("offline")),
    ):
        result = gifs.download_gif("https://tenor.com/view/cat-123", tmp_path)
    assert result is None
