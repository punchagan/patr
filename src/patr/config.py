import re
import subprocess
import tomllib

from patr import state


def load_hugo_config():
    with open(state.REPO_ROOT / "hugo.toml", "rb") as f:
        return tomllib.load(f)


def load_newsletter_config():
    hugo = load_hugo_config()
    config = dict(hugo.get("params", {}).get("patr", {}))
    local_file = state.CONFIG_DIR / "config.toml"
    if local_file.exists():
        with open(local_file, "rb") as f:
            config.update(tomllib.load(f))
    return config


def save_hugo_patr_params(updates: dict):
    """Surgically write [params.patr] keys into hugo.toml."""
    hugo_toml = state.REPO_ROOT / "hugo.toml"
    text = hugo_toml.read_text()

    for key, value in updates.items():
        quoted = f'"{value}"'
        # Update existing key inside [params.patr] block
        pattern = (
            r"(\[params\.newsletter\][^\[]*?)(" + re.escape(key) + r'\s*=\s*"[^"]*")'
        )
        if re.search(pattern, text, re.DOTALL):
            text = re.sub(
                pattern,
                lambda m: m.group(1) + f"{key} = {quoted}",
                text,
                flags=re.DOTALL,
            )
        else:
            # Key doesn't exist — append to section or create section
            if "[params.patr]" in text:
                text = re.sub(
                    r"(\[params\.newsletter\])", f"\\1\n  {key} = {quoted}", text
                )
            else:
                text += f"\n[params.patr]\n  {key} = {quoted}\n"

    hugo_toml.write_text(text)


def find_hugo():
    import shutil
    local = state.REPO_ROOT / "hugo.sh"
    if local.exists():
        return str(local)
    for candidate in ("hugo", "hugo.sh"):
        if shutil.which(candidate):
            return candidate
    raise RuntimeError("Hugo not found. Install hugo or provide a hugo.sh in the repo root.")


def build_hugo(port: int) -> tuple[bool, str]:
    result = subprocess.run(
        [find_hugo(), "-D", f"--baseURL=http://127.0.0.1:{port}/"],
        cwd=state.REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result.returncode == 0, result.stderr
