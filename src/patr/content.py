import re

import frontmatter
import markdown
from premailer import transform

from patr import state


def get_editions():
    posts = []
    for f in sorted(state.CONTENT_DIR.glob("*.md")):
        if f.name in ("_index.md", "footer.md"):
            continue
        try:
            post = frontmatter.load(f)
        except Exception as e:
            posts.append(
                {
                    "slug": f.stem,
                    "title": f"⚠ {f.stem} (frontmatter error)",
                    "date": "",
                    "draft": True,
                    "path": str(f.resolve()),
                    "error": str(e),
                }
            )
            continue
        posts.append(
            {
                "slug": f.stem,
                "title": post.get("title", f.stem),
                "date": str(post.get("date", ""))[:10],
                "draft": post.get("draft", False),
                "path": str(f.resolve()),
            }
        )
    posts.sort(key=lambda x: x["date"], reverse=True)
    return posts


def load_edition(slug):
    f = state.CONTENT_DIR / f"{slug}.md"
    if not f.exists():
        return None, None
    try:
        return f, frontmatter.load(f)
    except Exception as e:
        raise ValueError(f"Frontmatter parse error in {f.name}: {e}") from e


def load_footer():
    footer_file = state.CONTENT_DIR / "footer.md"
    if not footer_file.exists():
        return ""
    return frontmatter.load(footer_file).content


def render_md(text):
    html = markdown.markdown(text or "", extensions=["extra", "smarty"])

    # Mirror Hugo's render hook: wrap <img> with <figure>/<figcaption>
    def img_to_figure(m):
        tag = m.group(0)
        alt = re.search(r'alt="([^"]+)"', tag)
        if not alt:
            return tag
        return f"<figure>{tag}<figcaption>{alt.group(1)}</figcaption></figure>"

    return re.sub(r"<img[^>]+>", img_to_figure, html)


def build_web_html(post, footer_md):
    date = str(post.get("date", ""))[:10]
    intro_html = render_md(post.get("intro", ""))
    body_html = render_md(post.content)
    footer_html = render_md(footer_md)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{post["title"]}</title>
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
  <h1>{post["title"]}</h1>
  {"<div class='intro'>" + intro_html + "</div>" if intro_html else ""}
  <div class="content">{body_html}</div>
  {"<div class='footer'>" + footer_html + "</div>" if footer_html else ""}
</body>
</html>"""


def build_email_html(slug, post, footer_md, hugo_config, recipient_name=None):
    base_url = hugo_config.get("baseURL", "").rstrip("/")
    web_url = f"{base_url}/newsletter/{slug}/"
    greeting = f"Hi {recipient_name}," if recipient_name else "Hi,"
    intro_html = render_md(post.get("intro", ""))
    body_html = render_md(post.content)
    footer_html = render_md(footer_md)

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>img {{ max-width: 500px; height: auto; display: block; margin: 1rem auto; }}</style></head>
<body style="font-family: Georgia, serif; max-width: 600px; margin: 0 auto; padding: 24px; color: #333; background: #fff; line-height: 1.7;">
  <p style="font-size: 0.8em; color: #aaa; margin-bottom: 2em;">
    <a href="{web_url}" style="color: #aaa;">View in browser</a>
  </p>
  <p>{greeting}</p>
  {"<div style='font-style:italic;color:#555;border-bottom:1px solid #eee;padding-bottom:1em;margin-bottom:1.5em;font-size:1.05em;'>" + intro_html + "</div>" if intro_html else ""}
  <div>{body_html}</div>
  {"<div style='border-top:1px solid #eee;margin-top:2em;padding-top:1em;font-size:0.9em;color:#666;'>" + footer_html + "</div>" if footer_html else ""}
</body>
</html>"""
    return transform(html)
