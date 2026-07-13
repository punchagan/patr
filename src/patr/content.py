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
from patr.config import hugo_mode
from PIL import Image, UnidentifiedImageError

_EMAIL_CSS_PATH = Path(__file__).parent / "data" / "assets" / "email.css"

IMAGE_MAX_WIDTH = 800
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

    In Hugo mode, only page bundles (directories with index.md) are returned.
    In hugo-free mode, flat .md files are also returned alongside bundles.
    Returns an empty list if CONTENT_DIR does not exist.
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
            elif not hugo_mode() and entry.is_file() and entry.suffix == ".md":
                if entry.stem not in _SKIP_NAMES:
                    yield entry.stem, entry

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

    Checks for a page bundle (slug/index.md) first, then a flat file (slug.md)
    in hugo-free mode.
    """
    bundle = state.CONTENT_DIR / slug / "index.md"
    flat = state.CONTENT_DIR / f"{slug}.md"
    if bundle.exists():
        f = bundle
    elif not hugo_mode() and flat.exists():
        f = flat
    else:
        return None, None
    try:
        return f, frontmatter.load(f)
    except Exception as e:
        raise ValueError(f"Frontmatter parse error in {slug}: {e}") from e


def edition_dir_for(f):
    """Return the directory used to store an edition's resources (e.g. images).

    For a page bundle (slug/index.md) this is f.parent (slug/).
    For a flat file (slug.md) this is a sibling directory with the same stem (slug/).
    """
    return f.parent if f.parent != state.CONTENT_DIR else f.with_suffix("")


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
    """Resize src to at most IMAGE_MAX_WIDTH wide and re-encode as JPEG at
    dest, flattening any transparency onto a white background (both the
    email and the web edition render newsletter content on white). Both
    surfaces share this single compressed copy, so there's no separate
    full-resolution version.

    Returns True on success. Returns False (leaving dest untouched) if src
    isn't a decodable image — callers should fall back to saving the
    original bytes as-is.
    """
    try:
        with Image.open(src) as img:
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGBA")
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                img = background
            else:
                img = img.convert("RGB")
            if img.width > IMAGE_MAX_WIDTH:
                new_height = round(img.height * IMAGE_MAX_WIDTH / img.width)
                img = img.resize((IMAGE_MAX_WIDTH, new_height), Image.LANCZOS)
            img.save(dest, "JPEG", quality=IMAGE_JPEG_QUALITY)
    except UnidentifiedImageError:
        return False
    return True


def load_footer():
    footer_file = state.CONTENT_DIR / "footer" / "index.md"
    if not footer_file.exists():
        return ""
    return frontmatter.load(footer_file).content


_TITLE_BLOCK_RE = re.compile(r"\{([^}]*)\}\s*$")
_ATTR_PAIR_RE = re.compile(r"([\w-]+)='([^']*)'")


def _parse_title_attrs(title):
    """Split 'Text {key='val' ...}' into (clean_text, {key: val})."""
    m = _TITLE_BLOCK_RE.search(title)
    if not m:
        return title, {}
    attrs = dict(_ATTR_PAIR_RE.findall(m.group(1)))
    return title[: m.start()].strip(), attrs


def render_md(text):
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
    """Replace image src with base64 data URIs for email-only mode.

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


def build_email_html(
    slug,
    post,
    footer_md,
    hugo_config,
    recipient_name=None,
    absolute_urls=True,
    email_only=False,
    edition_dir=None,
):
    base_url = hugo_config.get("baseURL", "").rstrip("/")
    page_url = f"{base_url}/newsletter/{slug}/"
    name = (recipient_name or "").strip()
    greeting = f"Hi {name}," if name else "Hi,"
    intro_html = render_md(post.get("intro", ""))
    body_html = render_md(post.content)
    footer_html = render_md(footer_md)

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
    if email_only and edition_dir is not None:
        return css_inline.inline(embed_images(html, edition_dir))
    html = absolutify_urls(html, base_url, page_url) if absolute_urls else html
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
    separator, footer, and an optional view-in-browser link.
    """
    base_url = hugo_config.get("baseURL", "").rstrip("/")
    page_url = f"{base_url}/newsletter/{slug}/"
    name = (recipient_name or "").strip()
    greeting = f"Hi {name}," if name else "Hi,"

    parts = [greeting, ""]
    intro = (post.get("intro") or "").strip()
    if intro:
        parts += [intro, ""]
    parts.append(post.content.strip())
    if footer_md and footer_md.strip():
        parts += ["", "---", "", footer_md.strip()]
    if not email_only and page_url:
        parts += ["", f"View in browser: {page_url}"]
    return "\n".join(parts)
