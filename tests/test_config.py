"""Tests for save_hugo_patr_params in config.py."""

import pytest
from patr import state
from patr.config import save_hugo_patr_params


@pytest.fixture
def hugo_toml(tmp_path, monkeypatch):
    path = tmp_path / "hugo.toml"
    monkeypatch.setattr(state, "REPO_ROOT", tmp_path)
    return path


def test_creates_section_when_absent(hugo_toml) -> None:
    hugo_toml.write_text('baseURL = "https://example.com"\n')
    save_hugo_patr_params({"name": "My Newsletter"})
    text = hugo_toml.read_text()
    assert "[params.patr]" in text
    assert 'name = "My Newsletter"' in text


def test_adds_key_to_existing_section(hugo_toml) -> None:
    hugo_toml.write_text('[params.patr]\n  existing = "val"\n')
    save_hugo_patr_params({"name": "My Newsletter"})
    text = hugo_toml.read_text()
    assert 'existing = "val"' in text
    assert 'name = "My Newsletter"' in text


def test_updates_existing_key(hugo_toml) -> None:
    hugo_toml.write_text('[params.patr]\n  name = "Old Name"\n')
    save_hugo_patr_params({"name": "New Name"})
    text = hugo_toml.read_text()
    assert 'name = "New Name"' in text
    assert "Old Name" not in text


def test_preserves_comments(hugo_toml) -> None:
    hugo_toml.write_text(
        '# site config\nbaseURL = "https://example.com"\n\n[params.patr]\n  # patr settings\n  name = "Old"\n'
    )
    save_hugo_patr_params({"name": "New"})
    text = hugo_toml.read_text()
    assert "# site config" in text
    assert "# patr settings" in text


def test_preserves_other_keys_in_section(hugo_toml) -> None:
    hugo_toml.write_text('[params.patr]\n  name = "Old"\n  other = "keep"\n')
    save_hugo_patr_params({"name": "New"})
    text = hugo_toml.read_text()
    assert 'other = "keep"' in text


def test_saves_multiple_keys_at_once(hugo_toml) -> None:
    hugo_toml.write_text("[params.patr]\n")
    save_hugo_patr_params({"name": "NL", "sheet_id": "abc123"})
    text = hugo_toml.read_text()
    assert 'name = "NL"' in text
    assert 'sheet_id = "abc123"' in text
