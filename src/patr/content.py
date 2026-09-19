import base64
import difflib
import mimetypes
import re
from datetime import datetime
from pathlib import Path

import css_inline
import frontmatter
import markdown
import yaml
from bs4 import BeautifulSoup
from patr import state
from PIL import Image, ImageOps, UnidentifiedImageError

_EMAIL_CSS_PATH = Path(__file__).parent / "data" / "assets" / "email.css"

IMAGE_MAX_DIMENSION = 800  # bounds both width and height, whichever is larger
IMAGE_JPEG_QUALITY = 85
COMMIT_DIFF_THRESHOLD = 500  # bytes; below this amends the last wip commit / backup


class PatrYamlDumper(yaml.SafeDumper):
    """YAML dumper for edition frontmatter — preserves key order (via
    sort_keys=False at call sites) and uses literal block scalars for
    multi-line strings (e.g. intro:) instead of escaped single-line ones."""


def _str_representer(dumper, data):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


PatrYamlDumper.add_representer(str, _str_representer)


def write_edition_frontmatter(f: Path, post) -> None:
    """Write post's current metadata + content back to f, using
    PatrYamlDumper so key order and multi-line strings round-trip."""
    fm_yaml = yaml.dump(
        post.metadata, Dumper=PatrYamlDumper, sort_keys=False, allow_unicode=True
    )
    f.write_text(f"---\n{fm_yaml}---\n\n{post.content.strip()}\n")


def get_editions():
    """Return all editions as a list of dicts, sorted by date descending.

    Only page bundles (directories containing index.md) are returned — flat
    .md files are not recognized as editions (see patr migrate). Returns an
    empty list if CONTENT_DIR does not exist.
    """
    if not state.CONTENT_DIR.exists():
        return []

    _SKIP_NAMES = {"footer", "_index"}

    def _candidate_files():
        for entry in sorted(state.CONTENT_DIR.iterdir()):
            if entry.is_dir() and entry.name not in _SKIP_NAMES:
                f = entry / "index.md"
                if f.exists():
                    yield entry.name, f

    posts = []
    for slug, f in _candidate_files():
        try:
            post = frontmatter.load(f)
        except Exception as e:
            posts.append(
                {
                    "slug": slug,
                    "title": f"⚠ {slug} (frontmatter error)",
                    "date": "",
                    "draft": True,
                    "path": str(f.resolve()),
                    "error": str(e),
                }
            )
            continue
        posts.append(
            {
                "slug": slug,
                "title": post.get("title", slug),
                "date": str(post.get("date", ""))[:10],
                "draft": post.get("draft", False),
                "sent": post.get("sent"),
                "path": str(f.resolve()),
            }
        )
    posts.sort(key=lambda x: x["date"], reverse=True)
    return posts


def load_edition(slug):
    """Load an edition by slug, returning (path, post) or (None, None) if not found.

    Only a page bundle (slug/index.md) is recognized.
    """
    bundle = state.CONTENT_DIR / slug / "index.md"
    if not bundle.exists():
        return None, None
    try:
        return bundle, frontmatter.load(bundle)
    except Exception as e:
        raise ValueError(f"Frontmatter parse error in {slug}: {e}") from e


def edition_dir_for(f):
    """Return the directory used to store an edition's resources (e.g.
    images) — f.parent, the page bundle directory."""
    return f.parent


def repo_slug():
    """Derive a filesystem-safe slug from REPO_ROOT for backup directory naming.

    Uses Path.parts (OS-aware) rather than splitting the string on a
    hardcoded '/', so it works for both POSIX (``/home/user/my-newsletter``
    -> ``home-user-my-newsletter``) and Windows (``C:\\Users\\you\\newsletter``
    -> ``C-Users-you-newsletter``) roots. A leftover ':' or '\\' in the slug
    would make pathlib's '/' join treat it as a fresh absolute path, silently
    discarding BACKUPS_DIR instead of nesting under it.
    """
    parts = [str(p).strip("\\/:") for p in Path(state.REPO_ROOT).parts]
    return "-".join(p for p in parts if p)


def _diff_size(a: str, b: str) -> int:
    return len(
        "".join(
            difflib.unified_diff(
                a.splitlines(keepends=True), b.splitlines(keepends=True)
            )
        )
    )


def plan_backup_pruning(
    backups_root: Path, diff_threshold: int = COMMIT_DIFF_THRESHOLD
):
    """Plan a "checkpoint compaction" of timestamped backups under
    backups_root (one subdirectory per edition slug).

    Always keeps the first and last backup for each edition. For everything
    in between, keeps a backup only if its diff from the last *kept*
    checkpoint is >= diff_threshold bytes — i.e. it represents real,
    accumulated work — and drops it otherwise. Comparing against the last
    *kept* checkpoint (not the immediately-previous file) matters: a long
    run of individually-tiny edits must still accumulate into a new
    checkpoint once the drift is large enough, rather than being silently
    discarded as a chain of "small" diffs against each other.

    Returns {edition_slug: [prunable_paths]} — a dry-run-friendly plan; does
    not delete anything itself. Files with unparseable timestamp names are
    skipped (left untouched, never planned for pruning).
    """
    plan = {}
    if not backups_root.exists():
        return plan
    for ed_dir in sorted(p for p in backups_root.iterdir() if p.is_dir()):
        files = []
        for f in sorted(ed_dir.glob("*.md")):
            try:
                datetime.strptime(f.stem, "%Y%m%dT%H%M%S")  # noqa: DTZ007 (validation only)
            except ValueError:
                continue
            files.append(f)

        prunable = []
        if len(files) > 2:
            checkpoint_content = files[0].read_text(encoding="utf-8")
            for f in files[1:-1]:
                content = f.read_text(encoding="utf-8")
                if _diff_size(checkpoint_content, content) >= diff_threshold:
                    checkpoint_content = content
                else:
                    prunable.append(f)
        plan[ed_dir.name] = prunable
    return plan


def compress_image(src: Path, dest: Path) -> bool:
    """Resize src to fit within IMAGE_MAX_DIMENSION on both width and height
    (whichever would otherwise be larger) and re-encode as JPEG at dest,
    flattening any transparency onto a white background (both the email and
    the web edition render newsletter content on white). Both surfaces
    share this single compressed copy, so there's no separate
    full-resolution version.

    The EXIF Orientation tag is applied to the pixels before re-encoding.
    Cameras often store raw sensor pixels plus a tag saying how to rotate
    them for display; viewers honor it, but the re-encode below drops all
    EXIF, so without baking it in first the saved copy shows sideways.

    Returns True on success. Returns False (leaving dest untouched) if src
    isn't a decodable image — callers should fall back to saving the
    original bytes as-is.
    """
    try:
        with Image.open(src) as opened:
            img = ImageOps.exif_transpose(opened)
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGBA")
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                img = background
            else:
                img = img.convert("RGB")
            # thumbnail(), not a width-only check: bounds *both* dimensions,
            # so a tall portrait image (narrow width, huge height) doesn't
            # slip through uncapped just because its width alone is fine.
            img.thumbnail((IMAGE_MAX_DIMENSION, IMAGE_MAX_DIMENSION), Image.LANCZOS)
            img.save(dest, "JPEG", quality=IMAGE_JPEG_QUALITY)
    except UnidentifiedImageError:
        return False
    return True


def load_footer():
    footer_file = state.CONTENT_DIR / "footer" / "index.md"
    if not footer_file.exists():
        return ""
    return frontmatter.load(footer_file).content


# Must be kept in sync with the equivalent regex chain in
# src/patr/data/layouts/_markup/render-image.html (the Hugo/Go template
# equivalent, which can't share this code — different language/runtime).
# tests/fixtures/image_title_attrs.yaml has the shared test cases;
# tests/test_render_image_parity.py checks a Python port of the Go template
# against this function using that fixture. One deliberate difference: this
# function accepts any key='val' pair, while the Hugo template only
# recognizes style/width/height by name — an unrecognized key silently does
# nothing on the web side. That's intentional scope, not something to
# "fix" into matching.
_TITLE_BLOCK_RE = re.compile(r"\{([^}]*)\}\s*$")
_ATTR_PAIR_RE = re.compile(r"([\w-]+)='([^']*)'")


def _parse_title_attrs(title):
    """Split 'Text {key='val' ...}' into (clean_text, {key: val})."""
    m = _TITLE_BLOCK_RE.search(title)
    if not m:
        return title, {}
    attrs = dict(_ATTR_PAIR_RE.findall(m.group(1)))
    return title[: m.start()].strip(), attrs


def render_md(text, hard_wraps=False):
    # "extra" minus attr_list — attr_list is disabled so {width="N"} syntax
    # is not silently processed; use the title convention instead.
    extensions = [
        "abbr",
        "def_list",
        "fenced_code",
        "footnotes",
        "md_in_html",
        "tables",
        "smarty",
    ]
    # nl2br mirrors Hugo's markup.goldmark.renderer.hardWraps setting (see
    # README) — only enable it when that's also on, otherwise email and web
    # would render single newlines differently.
    if hard_wraps:
        extensions.append("nl2br")
    html = markdown.markdown(text or "", extensions=extensions)

    # Mirror Hugo's render hook: wrap <img> with <figure>/<figcaption>
    soup = BeautifulSoup(html, "html.parser")
    for img in soup.find_all("img"):
        # Gmail's mobile auto-fit reacts to a fixed-pixel image width (HTML
        # attribute, or its native resolution if no attribute is set) wider
        # than the screen by zooming the whole message, shrinking text.
        # width="100%" keeps it fluid; explicit title-attr width still wins.
        img["width"] = "100%"
        title = str(img.get("title", ""))
        if title:
            clean, attrs = _parse_title_attrs(title)
            for key, val in attrs.items():
                if key == "style":
                    existing = str(img.get("style", "")).rstrip(";")
                    img["style"] = (existing + ";" + val).lstrip(";")
                else:
                    img[key] = val
            if clean:
                img["title"] = clean
            else:
                del img["title"]
        alt = img.get("alt", "")
        if alt:
            figure = soup.new_tag("figure")
            img.replace_with(figure)
            figure.append(img)
            figcaption = soup.new_tag("figcaption")
            figcaption.string = alt
            figure.append(figcaption)
    return str(soup)


def embed_images(html: str, edition_dir: Path) -> str:
    """Replace image src with base64 data URIs, for emails that can't link to
    images on the site (email_only, or subscribers_only where the site is
    behind a login mail clients can't pass).

    edition_dir is the directory where relative image paths are resolved —
    either a page bundle dir (slug/index.md → slug/) or a flat file's sibling
    dir (slug.md → slug/). Root-relative paths (/images/...) resolve against
    REPO_ROOT/static/.
    """
    soup = BeautifulSoup(html, "html.parser")
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if src.startswith(("http://", "https://", "data:")):
            continue
        if src.startswith("/"):
            img_path = state.REPO_ROOT / "static" / src.lstrip("/")
        else:
            img_path = edition_dir / src
        if not img_path.exists():
            continue
        mime = mimetypes.guess_type(str(img_path))[0] or "image/png"
        data = base64.b64encode(img_path.read_bytes()).decode()
        img["src"] = f"data:{mime};base64,{data}"
        img["alt"] = (
            img_path.name
        )  # Gmail uses alt as MIME filename; keep it newline-free
    return str(soup)


def absolutify_urls(html: str, base_url: str, page_url: str) -> str:
    """Rewrite image src to absolute URLs for email sending.

    Handles root-relative (/images/foo.png → base_url/images/foo.png)
    and relative (photo.jpg → page_url/photo.jpg) paths.
    """
    soup = BeautifulSoup(html, "html.parser")
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if src.startswith("/"):
            img["src"] = base_url + src
        elif not src.startswith(("http://", "https://")):
            img["src"] = page_url + src
    return str(soup)


def absolutify_links(html: str, base_url: str) -> str:
    """Rewrite root-relative link hrefs to absolute URLs for email sending.

    Editions link to each other as ``/newsletter/<slug>/`` so the source has
    no domain in it and the site keeps working if the domain changes; an
    email has to carry the full URL, fixed at send time. Only hrefs starting
    with a single ``/`` are touched — ``https://``, ``//host``, ``mailto:``,
    ``#anchor`` and bare relative links are left alone. A no-op without a
    ``base_url`` (email-only / hugo-free: there's no site to point at).
    """
    if not base_url:
        return html
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a"):
        href = a.get("href", "")
        if href.startswith("/") and not href.startswith("//"):
            a["href"] = base_url + href
    return str(soup)


def absolutify_markdown_links(text: str, base_url: str) -> str:
    """Same as :func:`absolutify_links`, but for raw markdown (the plain-text
    email alternative): ``](/path)`` becomes ``](base_url/path)``. ``](//host``
    is left alone, and it's a no-op without a ``base_url``.
    """
    if not base_url:
        return text
    head, *rest = text.split("](")
    parts = [head]
    for part in rest:
        if part.startswith("/") and not part.startswith("//"):
            part = base_url + part
        parts.append(part)
    return "](".join(parts)


def build_email_html(
    slug,
    post,
    footer_md,
    hugo_config,
    recipient_name=None,
    absolute_urls=True,
    email_only=False,
    subscribers_only=False,
    edition_dir=None,
):
    """Build the HTML email for an edition.

    email_only: the edition isn't published, so drop the "View in browser"
    link and embed images.
    subscribers_only: the published site is behind a login, which mail clients
    can't pass, so images linked from the site would break; embed them too,
    but keep the "View in browser" link (readers can sign in).
    Embedding needs edition_dir (where relative image paths resolve); without
    it, image URLs are made absolute instead. Root-relative links (to other
    editions, say) are made absolute in every mode, unless absolute_urls is
    off or there's no baseURL.
    """
    base_url = hugo_config.get("baseURL", "").rstrip("/")
    page_url = f"{base_url}/newsletter/{slug}/"
    name = (recipient_name or "").strip()
    greeting = f"Hi {name}," if name else "Hi,"
    hard_wraps = (
        hugo_config.get("markup", {})
        .get("goldmark", {})
        .get("renderer", {})
        .get("hardWraps", False)
    )
    intro_html = render_md(post.get("intro", ""), hard_wraps=hard_wraps)
    body_html = render_md(post.content, hard_wraps=hard_wraps)
    footer_html = render_md(footer_md, hard_wraps=hard_wraps)

    view_in_browser = (
        ""
        if email_only
        else f'<p class="view-in-browser"><a href="{page_url}">View in browser</a></p>'
    )

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><style>{_EMAIL_CSS_PATH.read_text()}</style></head>
<body>
  <table width="100%" border="0" cellpadding="0" cellspacing="0">
    <tr>
      <td>
        <table width="600" border="0" cellpadding="0" cellspacing="0" align="center" style="max-width:600px;width:100%">
          <tr>
            <td class="email-body">
              {view_in_browser}
              <p>{greeting}</p>
              {"<div class='intro'>" + intro_html + "</div>" if intro_html else ""}
              <div class="content">{body_html}</div>
              {"<div class='footer'>" + footer_html + "</div>" if footer_html else ""}
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
    if (email_only or subscribers_only) and edition_dir is not None:
        html = embed_images(html, edition_dir)
    elif absolute_urls:
        html = absolutify_urls(html, base_url, page_url)
    if absolute_urls:
        html = absolutify_links(html, base_url)
    return css_inline.inline(html)


def build_email_plain(
    slug,
    post,
    footer_md,
    hugo_config,
    recipient_name=None,
    email_only=False,
):
    """Build a plain-text alternative for an email.

    Uses raw markdown so the text is readable without stripping syntax.
    Structure mirrors build_email_html: greeting, optional intro, body,
    separator, footer, and an optional view-in-browser link. Root-relative
    markdown links are made absolute, as in the HTML version.
    """
    base_url = hugo_config.get("baseURL", "").rstrip("/")
    page_url = f"{base_url}/newsletter/{slug}/"
    name = (recipient_name or "").strip()
    greeting = f"Hi {name}," if name else "Hi,"

    parts = [greeting, ""]
    intro = absolutify_markdown_links((post.get("intro") or "").strip(), base_url)
    if intro:
        parts += [intro, ""]
    parts.append(absolutify_markdown_links(post.content.strip(), base_url))
    if footer_md and footer_md.strip():
        parts += ["", "---", "", absolutify_markdown_links(footer_md.strip(), base_url)]
    if not email_only and page_url:
        parts += ["", f"View in browser: {page_url}"]
    return "\n".join(parts)
