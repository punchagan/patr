import html as _html
import re

import frontmatter
import markdown
from bs4 import BeautifulSoup
from premailer import transform

from patr import state


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


def render_md(text):
    html = markdown.markdown(text or "", extensions=["extra", "smarty"])

    # Mirror Hugo's render hook: wrap <img> with <figure>/<figcaption>
    soup = BeautifulSoup(html, "html.parser")
    for img in soup.find_all("img"):
        alt = img.get("alt", "")
        if alt:
            figure = soup.new_tag("figure")
            img.replace_with(figure)
            figure.append(img)
            figcaption = soup.new_tag("figcaption")
            figcaption.string = alt
            figure.append(figcaption)
    return str(soup)


def absolutify_urls(html: str, base_url: str, page_url: str) -> str:
    """Rewrite image src to absolute URLs for email sending.

    Handles root-relative (/images/foo.png → base_url/images/foo.png)
    and relative (photo.jpg → page_url/photo.jpg) paths.
    """
    html = re.sub(
        r'(<img\b[^>]*\bsrc=")(/[^"]+)',
        lambda m: m.group(1) + base_url + m.group(2),
        html,
    )
    html = re.sub(
        r'(<img\b[^>]*\bsrc=")(?!https?://|/)([^"]+)',
        lambda m: m.group(1) + page_url + m.group(2),
        html,
    )
    return html


def build_web_html(slug, post, footer_md):
    date = str(post.get("date", ""))[:10]
    title_escaped = _html.escape(post.get("title", ""))
    intro_html = render_md(post.get("intro", ""))
    body_html = render_md(post.content)
    footer_html = render_md(footer_md)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<base href="/newsletter/{slug}/">
<title>{title_escaped}</title>
<style>
  body {{ font-family: Georgia, serif; max-width: 640px; margin: 2rem auto; padding: 0 1.5rem; color: #333; line-height: 1.7; }}
  h1 {{ font-size: 1.8rem; margin-bottom: 0.25rem; }}
  .date {{ color: #999; font-size: 0.85em; margin-bottom: 1.5rem; }}
  .intro {{ font-style: italic; color: #555; border-bottom: 1px solid #ddd; padding-bottom: 1rem; margin-bottom: 1.5rem; font-size: 1.05em; }}
  .footer {{ border-top: 1px solid #ddd; margin-top: 2rem; padding-top: 1rem; font-size: 0.9em; color: #666; }}
  img {{ max-width: 500px; height: auto; display: block; margin: 1rem auto; }}
  figure {{ margin: 1.5rem 0; text-align: center; }}
  figcaption {{ font-size: 0.85em; color: #888; margin-top: 0.5rem; }}
</style>
</head>
<body>
  <p class="date">{date}</p>
  <h1>{title_escaped}</h1>
  {"<div class='intro'>" + intro_html + "</div>" if intro_html else ""}
  <div class="content">{body_html}</div>
  {"<div class='footer'>" + footer_html + "</div>" if footer_html else ""}
</body>
</html>"""


def build_email_html(slug, post, footer_md, hugo_config, recipient_name=None):
    base_url = hugo_config.get("baseURL", "").rstrip("/")
    page_url = f"{base_url}/newsletter/{slug}/"
    name = (recipient_name or "").strip()
    greeting = f"Hi {name}," if name else "Hi,"
    intro_html = render_md(post.get("intro", ""))
    body_html = render_md(post.content)
    footer_html = render_md(footer_md)

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>img {{ max-width: 500px; height: auto; display: block; margin: 1rem auto; }}</style></head>
<body style="font-family: Georgia, serif; max-width: 600px; margin: 0 auto; padding: 24px; color: #333; background: #fff; line-height: 1.7;">
  <p style="font-size: 0.8em; color: #aaa; margin-bottom: 2em;">
    <a href="{page_url}" style="color: #aaa;">View in browser</a>
  </p>
  <p>{greeting}</p>
  {"<div style='font-style:italic;color:#555;border-bottom:1px solid #eee;padding-bottom:1em;margin-bottom:1.5em;font-size:1.05em;'>" + intro_html + "</div>" if intro_html else ""}
  <div>{body_html}</div>
  {"<div style='border-top:1px solid #eee;margin-top:2em;padding-top:1em;font-size:0.9em;color:#666;'>" + footer_html + "</div>" if footer_html else ""}
</body>
</html>"""
    return transform(absolutify_urls(html, base_url, page_url))
