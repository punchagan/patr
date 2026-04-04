"""End-to-end tests using Playwright. Require Chromium or Chrome installed.

Run with:  uv run pytest -m e2e
Skip with: uv run pytest -m "not e2e"
"""
import threading
from pathlib import Path

import pytest

import patr.server as patr_server
from patr import state

pytestmark = pytest.mark.e2e


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def repo(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("e2e_repo")
    (tmp / "hugo.toml").write_text(
        '[params.patr]\nname = "E2E Newsletter"\n\nbaseURL = "http://example.com/"\ntitle = "Test"\n'
    )
    nl = tmp / "content" / "newsletter"
    nl.mkdir(parents=True)
    (nl / "_index.md").write_text("---\ntitle: Newsletter\n---\n")
    footer = nl / "footer"
    footer.mkdir()
    (footer / "index.md").write_text(
        "---\ntitle: Footer\n_build:\n  render: never\n  list: never\n---\n\nTest footer.\n"
    )
    state.REPO_ROOT = tmp
    state.CONTENT_DIR = nl
    state.PATR_ROOT = Path(patr_server.__file__).parent
    return tmp


@pytest.fixture(scope="session")
def base_url(repo):
    from werkzeug.serving import make_server
    srv = make_server("127.0.0.1", 0, patr_server.app)
    port = srv.server_address[1]
    patr_server.app.config["PORT"] = port
    patr_server.app.config["TESTING"] = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}"
    srv.shutdown()


@pytest.fixture(scope="session")
def browser(base_url):
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    br = None
    for channel in ("chromium", "chrome", "msedge"):
        try:
            br = pw.chromium.launch(channel=channel)
            break
        except Exception:
            continue
    if br is None:
        pw.stop()
        pytest.skip("No usable browser for E2E tests")
    yield br
    br.close()
    pw.stop()


@pytest.fixture(scope="session")
def context(browser):
    ctx = browser.new_context()
    ctx.set_default_timeout(8000)
    yield ctx
    ctx.close()


@pytest.fixture
def page(context, base_url):
    p = context.new_page()
    p.goto(base_url)
    p.wait_for_selector(".sidebar")
    yield p
    p.close()


@pytest.fixture
def edition(page, request):
    """Create an edition via the UI and select it, yielding its slug."""
    title = f"E2E {request.node.name}"
    page.locator(".sidebar-header button", has_text="+").click()
    page.locator("input[placeholder='e.g. Spring Edition']").fill(title)
    page.locator("button.btn-primary", has_text="Create").click()
    page.locator(f".edition-item:has-text('{title}')").click()
    page.wait_for_selector(".cm-content")
    # Derive slug the same way the server does
    import re
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    yield slug


REPO_ROOT = Path(__file__).parent.parent


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_screenshot(context, base_url):
    """Capture a screenshot of the app in a realistic state for the README."""
    p = context.new_page()
    p.set_viewport_size({"width": 1280, "height": 800})
    try:
        p.goto(base_url)
        p.wait_for_selector(".sidebar")
        # Create an edition
        p.locator(".sidebar-header button", has_text="+").click()
        p.locator("input[placeholder='e.g. Spring Edition']").fill("April 2025")
        p.locator("button.btn-primary", has_text="Create").click()
        p.locator(".edition-item:has-text('April 2025')").click()
        p.wait_for_selector(".cm-content")
        # Fill in title and body
        p.locator(".editor-title-input").fill("Hello from Patr")
        p.locator(".cm-content").click()
        p.locator(".cm-content").press_sequentially(
            "Writing newsletters should be simple. Patr keeps everything local — "
            "your words, your git history, your Gmail."
        )
        p.wait_for_function("document.querySelector('.cm-content').textContent.length > 10")
        out = REPO_ROOT / "screenshots" / "editor.png"
        out.parent.mkdir(exist_ok=True)
        p.screenshot(path=str(out))
    finally:
        p.close()
    assert (REPO_ROOT / "screenshots" / "editor.png").exists()


def test_screenshot_email_preview(context, base_url):
    """Capture a screenshot of the email preview for the README."""
    import re
    p = context.new_page()
    p.set_viewport_size({"width": 700, "height": 900})
    try:
        p.goto(base_url)
        p.wait_for_selector(".sidebar")
        p.locator(".sidebar-header button", has_text="+").click()
        p.locator("input[placeholder='e.g. Spring Edition']").fill("Spring 2025")
        p.locator("button.btn-primary", has_text="Create").click()
        p.locator(".edition-item:has-text('Spring 2025')").click()
        p.wait_for_selector(".cm-content")
        p.locator(".editor-title-input").fill("Welcome to Spring")
        p.locator(".cm-content").click()
        p.locator(".cm-content").press_sequentially(
            "Spring is here. Here's what's happening this month.\n\n"
            "## Highlights\n\n"
            "- New features shipping this month\n"
            "- Community roundup\n"
            "- Upcoming events\n\n"
            "We hope you enjoy this edition. More details below."
        )
        p.wait_for_function(
            "document.querySelector('.editor-save-status')?.textContent === 'Saved'",
            timeout=5000,
        )
        slug = re.sub(r"[^a-z0-9]+", "-", "spring 2025")
        p.goto(f"{base_url}/preview/{slug}/email")
        p.wait_for_load_state("networkidle")
        out = REPO_ROOT / "screenshots" / "email-preview.png"
        p.screenshot(path=str(out), full_page=True)
    finally:
        p.close()
    assert (REPO_ROOT / "screenshots" / "email-preview.png").exists()


def test_app_loads(page):
    assert page.locator(".sidebar").is_visible()
    assert page.locator(".main").is_visible()
    assert page.locator(".empty-state").is_visible()


def test_create_edition(page):
    page.locator(".sidebar-header button", has_text="+").click()
    page.locator("input[placeholder='e.g. Spring Edition']").fill("My E2E Edition")
    page.locator("button.btn-primary", has_text="Create").click()
    page.wait_for_selector(".edition-item:has-text('My E2E Edition')")


def test_edition_select_shows_editor(page, edition):
    assert page.locator(".editor-title-input").is_visible()
    assert page.locator(".cm-content").is_visible()
    assert page.locator(".editor-toolbar").is_visible()


def test_autosave(page, edition, base_url):
    editor = page.locator(".cm-content")
    editor.click()
    page.wait_for_function("document.activeElement.classList.contains('cm-content')")
    editor.press_sequentially("Hello autosave")
    # Wait for text to appear in DOM, then for autosave to fire
    page.wait_for_function("document.querySelector('.cm-content').textContent.includes('Hello autosave')")
    page.wait_for_function("document.querySelector('.editor-save-status')?.textContent === 'Saved'", timeout=5000)
    content = page.request.get(f"{base_url}/api/edition/{edition}/content").json()
    assert "Hello autosave" in content["body"]


def test_toolbar_bold(page, edition):
    page.locator(".cm-content").click()
    page.wait_for_function("document.activeElement.classList.contains('cm-content')")
    page.locator(".editor-toolbar-btn", has_text="B").click()
    # Toolbar dispatches synchronously to CodeMirror — check DOM directly
    page.wait_for_function("document.querySelector('.cm-content').textContent.includes('**')")


def test_toolbar_italic(page, edition):
    page.locator(".cm-content").click()
    page.wait_for_function("document.activeElement.classList.contains('cm-content')")
    page.locator(".editor-toolbar-btn em", has_text="I").click()
    page.wait_for_function("document.querySelector('.cm-content').textContent.includes('*')")


def test_mode_switch_split(page, edition):
    page.locator("button.btn-toggle", has_text="Split").click()
    page.wait_for_selector(".split-preview")
    assert page.locator(".editor-pane").is_visible()


def test_mode_switch_preview_email(page, edition):
    page.locator("button.btn-toggle", has_text="Preview Email").click()
    assert page.locator(".full-preview").is_visible()
    assert page.locator("a", has_text="Download PDF").is_visible()


def test_focus_mode(page, edition):
    # Enter focus mode
    page.locator("button[title*='Focus mode']").click()
    assert not page.locator(".sidebar").is_visible()
    assert not page.locator(".action-bar").is_visible()
    assert not page.locator(".editor-title-input").is_visible()
    # Exit with Escape
    page.keyboard.press("Escape")
    page.wait_for_selector(".sidebar")
    assert page.locator(".sidebar").is_visible()


def test_footer_editing(page):
    page.locator(".edition-item.footer-item").click()
    page.wait_for_selector(".cm-content")
    assert page.locator(".cm-content").is_visible()
    # Title and intro fields should not appear for footer
    assert not page.locator(".editor-title-input").is_visible()


def test_mode_stored_in_hash(page, edition, base_url):
    # Write mode: hash has no suffix
    assert page.evaluate("location.hash") == f"#{edition}"

    # Split mode
    page.locator(".btn-toggle", has_text="Split").click()
    assert page.evaluate("location.hash") == f"#{edition}/split"

    # Preview Email
    page.locator(".btn-toggle", has_text="Preview Email").click()
    assert page.evaluate("location.hash") == f"#{edition}/email"

    # Preview Web
    page.locator(".btn-toggle", has_text="Preview Web").click()
    assert page.evaluate("location.hash") == f"#{edition}/web"

    # Back to Write
    page.locator(".btn-toggle", has_text="Write").click()
    assert page.evaluate("location.hash") == f"#{edition}"


def test_hash_restores_mode(context, edition, base_url):
    # Use fresh pages so React initializes from the hash (not a hash-change on existing page)
    p = context.new_page()
    try:
        p.goto(f"{base_url}/#{edition}/email")
        p.wait_for_selector(".full-preview")
        assert p.locator(".btn-toggle.active", has_text="Preview Email").is_visible()
    finally:
        p.close()

    p = context.new_page()
    try:
        p.goto(f"{base_url}/#{edition}/split")
        p.wait_for_selector(".cm-content")
        p.wait_for_selector(".preview-frame")
        assert p.locator(".btn-toggle.active", has_text="Split").is_visible()
    finally:
        p.close()
