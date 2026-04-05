"""Tests for config.py — save_hugo_patr_params, hugo_mode, load_hugo_config."""

import tomllib

import pytest
from patr import state
from patr.config import hugo_mode, load_hugo_config, load_newsletter_config, save_hugo_patr_params


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


# hugo_mode and load_hugo_config


def test_hugo_mode_false_without_hugo_toml(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(state, "REPO_ROOT", tmp_path)
    assert hugo_mode() is False


def test_hugo_mode_true_with_hugo_toml(tmp_path, monkeypatch) -> None:
    (tmp_path / "hugo.toml").write_text('baseURL = "https://example.com"\n')
    monkeypatch.setattr(state, "REPO_ROOT", tmp_path)
    assert hugo_mode() is True


def test_load_hugo_config_returns_empty_when_absent(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(state, "REPO_ROOT", tmp_path)
    assert load_hugo_config() == {}


def test_load_newsletter_config_email_only_default_in_hugo_free(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(state, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(state, "CONFIG_DIR", tmp_path / "config")
    cfg = load_newsletter_config()
    assert cfg["email_only"] is True


def test_load_newsletter_config_no_email_only_default_in_hugo_mode(tmp_path, monkeypatch) -> None:
    (tmp_path / "hugo.toml").write_text("[params.patr]\n")
    monkeypatch.setattr(state, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(state, "CONFIG_DIR", tmp_path / "config")
    cfg = load_newsletter_config()
    assert "email_only" not in cfg


def test_load_newsletter_config_reads_patr_toml_in_hugo_free(tmp_path, monkeypatch) -> None:
    (tmp_path / "patr.toml").write_text('name = "My NL"\n')
    monkeypatch.setattr(state, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(state, "CONFIG_DIR", tmp_path / "config")
    cfg = load_newsletter_config()
    assert cfg["name"] == "My NL"
    assert cfg["email_only"] is True  # default still applies


def test_save_hugo_patr_params_writes_patr_toml_in_hugo_free(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(state, "REPO_ROOT", tmp_path)
    save_hugo_patr_params({"name": "My NL"})
    assert (tmp_path / "patr.toml").exists()
    assert "My NL" in (tmp_path / "patr.toml").read_text()


def test_save_hugo_patr_params_writes_booleans_correctly_in_hugo_free(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(state, "REPO_ROOT", tmp_path)
    save_hugo_patr_params({"email_only": True})
    with open(tmp_path / "patr.toml", "rb") as f:
        data = tomllib.load(f)
    assert data["email_only"] is True  # bool, not string "True"


def test_load_newsletter_config_email_only_always_true_in_hugo_free(tmp_path, monkeypatch) -> None:
    """email_only is always True in hugo-free mode regardless of patr.toml."""
    (tmp_path / "patr.toml").write_text("email_only = false\n")
    monkeypatch.setattr(state, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(state, "CONFIG_DIR", tmp_path / "config")
    cfg = load_newsletter_config()
    assert cfg["email_only"] is True


def test_save_hugo_patr_params_preserves_existing_patr_toml(tmp_path, monkeypatch) -> None:
    (tmp_path / "patr.toml").write_text('name = "Old"\n')
    monkeypatch.setattr(state, "REPO_ROOT", tmp_path)
    save_hugo_patr_params({"email_only": False})
    with open(tmp_path / "patr.toml", "rb") as f:
        data = tomllib.load(f)
    assert data["name"] == "Old"
    assert data["email_only"] is False
