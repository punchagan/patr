import base64
import html as _html
import mimetypes
import re
from pathlib import Path

import frontmatter
import markdown
from bs4 import BeautifulSoup
import css_inline

from patr import state

_EMAIL_CSS_PATH = Path(__file__).parent / "data" / "assets" / "email.css"


def get_editions():
    posts = []
    for d in sorted(state.CONTENT_DIR.iterdir()):
        if not d.is_dir() or d.name == "footer":
            continue
        f = d / "index.md"
        if not f.exists():
            continue
        try:
            post = frontmatter.load(f)
        except Exception as e:
            posts.append(
                {
                    "slug": d.name,
                    "title": f"⚠ {d.name} (frontmatter error)",
                    "date": "",
                    "draft": True,
                    "path": str(f.resolve()),
                    "error": str(e),
                }
            )
            continue
        posts.append(
            {
                "slug": d.name,
                "title": post.get("title", d.name),
                "date": str(post.get("date", ""))[:10],
                "draft": post.get("draft", False),
                "path": str(f.resolve()),
            }
        )
    posts.sort(key=lambda x: x["date"], reverse=True)
    return posts


def load_edition(slug):
    f = state.CONTENT_DIR / slug / "index.md"
    if not f.exists():
        return None, None
    try:
        return f, frontmatter.load(f)
    except Exception as e:
        raise ValueError(f"Frontmatter parse error in {slug}/index.md: {e}") from e


def load_footer():
    footer_file = state.CONTENT_DIR / "footer" / "index.md"
    if not footer_file.exists():
        return ""
    return frontmatter.load(footer_file).content


_TITLE_BLOCK_RE = re.compile(r'\{([^}]*)\}\s*$')
_ATTR_PAIR_RE = re.compile(r"([\w-]+)='([^']*)'")


def _parse_title_attrs(title):
    """Split 'Text {key='val' ...}' into (clean_text, {key: val})."""
    m = _TITLE_BLOCK_RE.search(title)
    if not m:
        return title, {}
    attrs = dict(_ATTR_PAIR_RE.findall(m.group(1)))
    return title[:m.start()].strip(), attrs


def render_md(text):
    # "extra" minus attr_list — attr_list is disabled so {width="N"} syntax
    # is not silently processed; use the title convention instead.
    extensions = ["abbr", "def_list", "fenced_code", "footnotes", "md_in_html", "tables", "smarty"]
    html = markdown.markdown(text or "", extensions=extensions)

    # Mirror Hugo's render hook: wrap <img> with <figure>/<figcaption>
    soup = BeautifulSoup(html, "html.parser")
    for img in soup.find_all("img"):
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

    Handles relative paths (edition bundle) and root-relative paths
    (/images/... → {REPO_ROOT}/static/images/...).
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


def build_email_html(slug, post, footer_md, hugo_config, recipient_name=None,
                     email_only=False, edition_dir=None):
    base_url = hugo_config.get("baseURL", "").rstrip("/")
    page_url = f"{base_url}/newsletter/{slug}/"
    name = (recipient_name or "").strip()
    greeting = f"Hi {name}," if name else "Hi,"
    intro_html = render_md(post.get("intro", ""))
    body_html = render_md(post.content)
    footer_html = render_md(footer_md)

    view_in_browser = (
        "" if email_only
        else f'<p class="view-in-browser"><a href="{page_url}">View in browser</a></p>'
    )

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>{_EMAIL_CSS_PATH.read_text()}</style></head>
<body>
  {view_in_browser}
  <p>{greeting}</p>
  {"<div class='intro'>" + intro_html + "</div>" if intro_html else ""}
  <div class="content">{body_html}</div>
  {"<div class='footer'>" + footer_html + "</div>" if footer_html else ""}
</body>
</html>"""
    if email_only and edition_dir is not None:
        return css_inline.inline(embed_images(html, edition_dir))
    return css_inline.inline(absolutify_urls(html, base_url, page_url))
