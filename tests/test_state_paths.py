"""Tests for OS-specific default CONFIG_DIR/BACKUPS_DIR selection.

These exercise the branching logic directly (rather than relying on
actually running on Windows) by monkeypatching sys.platform and the
environment. Path objects here are constructed with whatever pathlib
flavour the *test-running* OS provides — that's fine, since we're only
testing that the function branches and joins components correctly, not
real Windows path-splitting semantics.
"""

import sys
from pathlib import Path

from patr import state


def test_config_dir_on_posix(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(Path, "home", lambda: Path("/home/user"))
    assert state._default_config_dir() == Path("/home/user/.config/patr")


def test_backups_dir_on_posix(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(Path, "home", lambda: Path("/home/user"))
    assert state._default_backups_dir() == Path("/home/user/.local/share/patr/backups")


def test_config_dir_on_windows_uses_localappdata(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", "C:\\Users\\you\\AppData\\Local")
    assert (
        state._default_config_dir()
        == Path("C:\\Users\\you\\AppData\\Local") / "patr" / "config"
    )


def test_backups_dir_on_windows_uses_localappdata(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", "C:\\Users\\you\\AppData\\Local")
    assert (
        state._default_backups_dir()
        == Path("C:\\Users\\you\\AppData\\Local") / "patr" / "backups"
    )


def test_config_dir_on_windows_falls_back_without_localappdata(monkeypatch) -> None:
    """LOCALAPPDATA is always set on real Windows, but fall back sanely if
    it's ever missing (e.g. a stripped-down CI environment)."""
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(Path, "home", lambda: Path("C:\\Users\\you"))
    assert (
        state._default_config_dir()
        == Path("C:\\Users\\you") / "AppData" / "Local" / "patr" / "config"
    )
