"""End-to-end tests using Playwright. Require Chromium or Chrome installed.

Run with:  uv run pytest -m e2e
Skip with: uv run pytest -m "not e2e"
"""

import threading
from pathlib import Path

import patr.server as patr_server
import pytest
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

    srv = make_server("127.0.0.1", 0, patr_server.app, threaded=True)
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


_SCREENSHOT_BODY = """\
Patr makes writing newsletters simple — your words stay local, \
your history lives in git, and sending happens via Gmail.

![A quiet writing space](writing.png)

## What's in this edition

- **Writing**: distraction-free editor with markdown syntax highlighting
- **Previewing**: split view or full email/web preview
- **Sending**: one click to reach your list via Gmail

Thanks for reading. Reply any time — I'd love to hear from you.
"""


@pytest.fixture(scope="session")
def screenshot_edition(repo, context, base_url):
    """Set up the 'April 2025' edition with rich content for README screenshots."""
    p = context.new_page()
    try:
        p.goto(base_url)
        p.wait_for_selector(".sidebar")
        p.locator(".sidebar-header button", has_text="+").click()
        p.locator("input[placeholder='e.g. Spring Edition']").fill("April 2025")
        p.locator("button.btn-primary", has_text="Create").click()
        p.wait_for_selector(".edition-item:has-text('April 2025')")
    finally:
        p.close()
    slug = "april-2025"
    edition_dir = state.CONTENT_DIR / slug
    (edition_dir / "index.md").write_text(
        "---\ntitle: Hello from Patr\ndate: 2025-04-01\ndraft: true\n---\n\n"
        + _SCREENSHOT_BODY
    )
    yield slug


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.screenshots
def test_screenshot(screenshot_edition, context, base_url) -> None:
    """Capture a screenshot of the editor for the README."""
    p = context.new_page()
    p.set_viewport_size({"width": 1280, "height": 800})
    try:
        p.goto(base_url)
        p.wait_for_selector(".sidebar")
        p.locator(".edition-item:has-text('Hello from Patr')").click()
        p.wait_for_selector(".cm-content")
        out = REPO_ROOT / "screenshots" / "editor.png"
        out.parent.mkdir(exist_ok=True)
        p.screenshot(path=str(out))
    finally:
        p.close()
    assert out.exists()


@pytest.mark.screenshots
def test_screenshot_email_preview(screenshot_edition, context, base_url) -> None:
    """Capture a screenshot of the email preview for the README.

    Depends on test_screenshot having run first (uses editor.png as the
    newsletter image). Skips gracefully if run in isolation.
    """
    import shutil

    editor_png = REPO_ROOT / "screenshots" / "editor.png"
    if not editor_png.exists():
        pytest.skip("editor.png not yet generated; run test_screenshot first")
    shutil.copy(editor_png, state.CONTENT_DIR / screenshot_edition / "writing.png")
    p = context.new_page()
    p.set_viewport_size({"width": 700, "height": 900})
    try:
        p.goto(f"{base_url}/preview/{screenshot_edition}/email")
        p.wait_for_load_state("networkidle")
        out = REPO_ROOT / "screenshots" / "email-preview.png"
        p.screenshot(path=str(out), full_page=True)
    finally:
        p.close()
    assert out.exists()


def test_pdf_single_page(context, base_url) -> None:
    """PDF export must always fit on a single page, even with large images."""
    import re
    import shutil

    editor_png = REPO_ROOT / "screenshots" / "editor.png"
    email_png = REPO_ROOT / "screenshots" / "email-preview.png"
    assert editor_png.exists(), "screenshots/editor.png missing"
    assert email_png.exists(), "screenshots/email-preview.png missing"

    p = context.new_page()
    try:
        p.goto(base_url)
        p.wait_for_selector(".sidebar")
        p.locator(".sidebar-header button", has_text="+").click()
        p.locator("input[placeholder='e.g. Spring Edition']").fill("PDF Test")
        p.locator("button.btn-primary", has_text="Create").click()
        p.wait_for_selector(".edition-item:has-text('PDF Test')")
    finally:
        p.close()

    slug = "pdf-test"
    edition_dir = state.CONTENT_DIR / slug
    shutil.copy(editor_png, edition_dir / "editor.png")
    shutil.copy(email_png, edition_dir / "email-preview.png")
    (edition_dir / "index.md").write_text(
        "---\ntitle: PDF Test\ndate: 2025-04-01\ndraft: true\n---\n\n"
        "Here is the editor.\n\n"
        "![Editor screenshot](editor.png)\n\n"
        "Here is the email preview.\n\n"
        "![Email preview screenshot](email-preview.png)\n"
    )

    resp = context.request.get(f"{base_url}/preview/{slug}/email.pdf")
    assert resp.status == 200
    pages = len(re.findall(rb"/Type\s*/Page(?!s)", resp.body()))
    assert pages == 1, f"Expected 1 page PDF, got {pages}"


def test_publish_button_hidden_without_git(page, edition) -> None:
    """Publish button should not appear when the repo is not a git repository."""
    page.wait_for_selector(".action-bar")
    assert not page.locator("button", has_text="Publish").is_visible()


def test_publish_button_visible_with_git(repo, context, base_url) -> None:
    """Publish button appears when the repo is a git repository."""
    import subprocess

    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    try:
        p = context.new_page()
        p.goto(base_url)
        p.wait_for_selector(".sidebar")
        p.locator(".sidebar-header button", has_text="+").click()
        p.locator("input[placeholder='e.g. Spring Edition']").fill("Git Mode Test")
        p.locator("button.btn-primary", has_text="Create").click()
        p.locator(".edition-item:has-text('Git Mode Test')").click()
        p.wait_for_selector(".action-bar")
        # Wait for check-deployment to resolve
        p.wait_for_function(
            "!document.querySelector('.status-msg.info')",
            timeout=5000,
        )
        assert p.locator("button", has_text="Publish").is_visible()
        p.close()
    finally:
        import shutil

        shutil.rmtree(repo / ".git")


def test_app_loads(page) -> None:
    assert page.locator(".sidebar").is_visible()
    assert page.locator(".main").is_visible()
    assert page.locator(".empty-state").is_visible()


def test_create_edition(page) -> None:
    page.locator(".sidebar-header button", has_text="+").click()
    page.locator("input[placeholder='e.g. Spring Edition']").fill("My E2E Edition")
    page.locator("button.btn-primary", has_text="Create").click()
    page.wait_for_selector(".edition-item:has-text('My E2E Edition')")


def test_edition_select_shows_editor(page, edition) -> None:
    assert page.locator(".editor-title-input").is_visible()
    assert page.locator(".cm-content").is_visible()
    assert page.locator(".editor-toolbar").is_visible()


def test_autosave(page, edition, base_url) -> None:
    editor = page.locator(".cm-content")
    editor.click()
    page.wait_for_function("document.activeElement.classList.contains('cm-content')")
    editor.press_sequentially("Hello autosave")
    # Wait for text to appear in DOM, then for autosave to fire
    page.wait_for_function(
        "document.querySelector('.cm-content').textContent.includes('Hello autosave')"
    )
    page.wait_for_function(
        "document.querySelector('.editor-save-status')?.textContent === 'Saved'",
        timeout=5000,
    )
    content = page.request.get(f"{base_url}/api/edition/{edition}/content").json()
    assert "Hello autosave" in content["body"]


def test_toolbar_bold(page, edition) -> None:
    page.locator(".cm-content").click()
    page.wait_for_function("document.activeElement.classList.contains('cm-content')")
    page.locator(".editor-toolbar-btn", has_text="B").click()
    # Toolbar dispatches synchronously to CodeMirror — check DOM directly
    page.wait_for_function(
        "document.querySelector('.cm-content').textContent.includes('**')"
    )


def test_toolbar_italic(page, edition) -> None:
    page.locator(".cm-content").click()
    page.wait_for_function("document.activeElement.classList.contains('cm-content')")
    page.locator(".editor-toolbar-btn em", has_text="I").click()
    page.wait_for_function(
        "document.querySelector('.cm-content').textContent.includes('*')"
    )


def test_mode_switch_split(page, edition) -> None:
    page.locator("button.btn-toggle", has_text="Split").click()
    page.wait_for_selector(".split-preview")
    assert page.locator(".editor-pane").is_visible()


def test_mode_switch_preview_email(page, edition) -> None:
    page.locator("button.btn-toggle", has_text="Preview Email").click()
    assert page.locator(".full-preview").is_visible()
    assert page.locator("button", has_text="Download PDF").is_visible()


def test_focus_mode(page, edition) -> None:
    # Enter focus mode
    page.locator("button[title*='Focus mode']").click()
    assert not page.locator(".sidebar").is_visible()
    assert not page.locator(".action-bar").is_visible()
    assert not page.locator(".editor-title-input").is_visible()
    # Exit with Escape
    page.keyboard.press("Escape")
    page.wait_for_selector(".sidebar")
    assert page.locator(".sidebar").is_visible()


def test_footer_editing(page) -> None:
    page.locator(".edition-item.footer-item").click()
    page.wait_for_selector(".cm-content")
    assert page.locator(".cm-content").is_visible()
    # Title and intro fields should not appear for footer
    assert not page.locator(".editor-title-input").is_visible()


def test_mode_stored_in_hash(page, edition, base_url) -> None:
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


def test_hash_restores_mode(context, edition, base_url) -> None:
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


# ── Conflict detection ─────────────────────────────────────────────────────────


def _trigger_focus(page) -> None:
    """Simulate re-focusing the window (triggers the conflict check)."""
    page.evaluate("window.dispatchEvent(new Event('focus'))")


def test_conflict_clean_editor_silently_reloads(page, edition) -> None:
    """If editor is clean and file changes on disk, re-focusing reloads silently."""
    # Wait for editor to load
    page.wait_for_selector(".cm-content")
    # Modify the file on disk externally
    edition_dir = state.CONTENT_DIR / edition
    index = edition_dir / "index.md"
    original = index.read_text()
    index.write_text(original.rstrip() + "\n\nExternal edit.\n")

    _trigger_focus(page)
    # No conflict modal — content should be silently updated
    page.wait_for_function(
        "document.querySelector('.cm-content').textContent.includes('External edit.')",
        timeout=4000,
    )
    assert not page.locator(".conflict-modal").is_visible()


def test_conflict_dirty_editor_shows_modal(page, edition) -> None:
    """If editor has unsaved changes and file changes on disk, show conflict modal."""
    page.wait_for_selector(".cm-content")
    # Type something (makes editor dirty, triggers autosave)
    editor = page.locator(".cm-content")
    editor.click()
    page.wait_for_function("document.activeElement.classList.contains('cm-content')")
    editor.press_sequentially("My local edit")
    # Wait for autosave to fire and persist mtime
    page.wait_for_function(
        "document.querySelector('.editor-save-status')?.textContent === 'Saved'",
        timeout=5000,
    )

    # Now externally modify the file (after save, so mtime advances)
    import time

    time.sleep(0.05)
    edition_dir = state.CONTENT_DIR / edition
    index = edition_dir / "index.md"
    index.write_text(index.read_text().rstrip() + "\n\nDisk version.\n")

    # Type more (makes editor dirty again, so conflict check triggers modal)
    editor.press_sequentially(" extra")
    _trigger_focus(page)
    page.wait_for_selector(".conflict-modal", timeout=4000)


def test_conflict_keep_mine(page, edition, base_url) -> None:
    """'Keep mine' dismisses modal and saves the editor content."""
    page.wait_for_selector(".cm-content")
    editor = page.locator(".cm-content")
    editor.click()
    page.wait_for_function("document.activeElement.classList.contains('cm-content')")
    editor.press_sequentially("Keep-mine-content")
    page.wait_for_function(
        "document.querySelector('.editor-save-status')?.textContent === 'Saved'",
        timeout=5000,
    )

    import time

    time.sleep(0.05)
    edition_dir = state.CONTENT_DIR / edition
    index = edition_dir / "index.md"
    index.write_text(index.read_text().rstrip() + "\n\nDisk v2.\n")

    editor.press_sequentially(" more")
    _trigger_focus(page)
    page.wait_for_selector(".conflict-modal", timeout=4000)

    page.locator(".conflict-modal button", has_text="Keep mine").click()
    page.wait_for_function("!document.querySelector('.conflict-modal')", timeout=3000)
    # Editor content (mine) should be saved
    page.wait_for_function(
        "document.querySelector('.editor-save-status')?.textContent === 'Saved'",
        timeout=5000,
    )
    content = page.request.get(f"{base_url}/api/edition/{edition}/content").json()
    assert "Keep-mine-content" in content["body"]


def test_conflict_keep_theirs(page, edition) -> None:
    """'Keep theirs' dismisses modal and reloads disk content into editor."""
    page.wait_for_selector(".cm-content")
    editor = page.locator(".cm-content")
    editor.click()
    page.wait_for_function("document.activeElement.classList.contains('cm-content')")
    editor.press_sequentially("Keep-theirs-mine")
    page.wait_for_function(
        "document.querySelector('.editor-save-status')?.textContent === 'Saved'",
        timeout=5000,
    )

    import time

    time.sleep(0.05)
    edition_dir = state.CONTENT_DIR / edition
    index = edition_dir / "index.md"
    index.write_text(index.read_text().rstrip() + "\n\nDisk theirs.\n")

    editor.press_sequentially(" more")
    _trigger_focus(page)
    page.wait_for_selector(".conflict-modal", timeout=4000)

    page.locator(".conflict-modal button", has_text="Use disk version").click()
    page.wait_for_function("!document.querySelector('.conflict-modal')", timeout=3000)
    # Editor should now show disk content
    page.wait_for_function(
        "document.querySelector('.cm-content').textContent.includes('Disk theirs.')",
        timeout=3000,
    )
