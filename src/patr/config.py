import shutil
import subprocess
import tomllib

import tomlkit
from patr import state


def hugo_mode() -> bool:
    """Return True if the current repo is a Hugo site (hugo.toml present)."""
    return (state.REPO_ROOT / "hugo.toml").exists()


def git_mode() -> bool:
    """Return True if git is installed and REPO_ROOT is inside a git repository."""
    if not shutil.which("git"):
        return False
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=state.REPO_ROOT,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def load_hugo_config() -> dict:
    """Load hugo.toml as a dict. Returns {} when hugo.toml is absent (hugo-free mode)."""
    hugo_toml = state.REPO_ROOT / "hugo.toml"
    if not hugo_toml.exists():
        return {}
    with open(hugo_toml, "rb") as f:
        return tomllib.load(f)


def load_newsletter_config() -> dict:
    """Load newsletter config from hugo.toml [params.patr] and ~/.config/patr/config.toml.

    In hugo-free mode (no hugo.toml), defaults email_only to True unless
    explicitly overridden in config.toml.
    """
    if hugo_mode():
        hugo = load_hugo_config()
        config = dict(hugo.get("params", {}).get("patr", {}))
    else:
        config = {}
        patr_toml = state.REPO_ROOT / "patr.toml"
        if patr_toml.exists():
            with open(patr_toml, "rb") as f:
                config.update(tomllib.load(f))
        config["email_only"] = True  # always True in hugo-free mode
    local_file = state.CONFIG_DIR / "config.toml"
    if local_file.exists():
        with open(local_file, "rb") as f:
            config.update(tomllib.load(f))
    return config


def save_hugo_patr_params(updates: dict) -> None:
    """Write patr settings, preserving comments and formatting.

    In Hugo mode: writes to hugo.toml [params.patr].
    In hugo-free mode: writes to patr.toml in the repo root.
    """
    if hugo_mode():
        hugo_toml = state.REPO_ROOT / "hugo.toml"
        doc = tomlkit.parse(hugo_toml.read_text())
        params = doc.setdefault("params", tomlkit.table())
        patr = params.setdefault("patr", tomlkit.table())
        for key, value in updates.items():
            patr[key] = value
        hugo_toml.write_text(tomlkit.dumps(doc))
    else:
        patr_toml = state.REPO_ROOT / "patr.toml"
        doc = (
            tomlkit.parse(patr_toml.read_text())
            if patr_toml.exists()
            else tomlkit.document()
        )
        for key, value in updates.items():
            doc[key] = value
        patr_toml.write_text(tomlkit.dumps(doc))


def find_hugo():
    local = state.REPO_ROOT / "hugo.sh"
    if local.exists():
        return str(local)
    for candidate in ("hugo", "hugo.sh"):
        if shutil.which(candidate):
            return candidate
    return None


def build_hugo(port: int) -> tuple[bool, str]:
    hugo = find_hugo()
    if hugo is None:
        return (
            False,
            "Hugo not found. Install hugo or provide a hugo.sh in the repo root.",
        )
    result = subprocess.run(
        [hugo, "-D", f"--baseURL=http://127.0.0.1:{port}/"],
        cwd=state.REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return result.returncode == 0, result.stderr
