"""Tests for content rendering — render_md, absolutify_urls, build_email_html."""

import base64
import frontmatter
from patr.content import render_md, absolutify_urls, build_email_html

HUGO_CONFIG = {"baseURL": "https://example.com"}

FOOTER_MD = "Unsubscribe [here](https://example.com/unsubscribe)."


def make_post(title="Test Edition", date="2024-03-15", intro="", body="Hello world."):
    text = f"---\ntitle: {title}\ndate: {date}\n"
    if intro:
        indented = "\n".join("  " + line for line in intro.splitlines())
        text += f"intro: |\n{indented}\n"
    text += f"---\n\n{body}\n"
    return frontmatter.loads(text)


# render_md — only testing our own logic, not the markdown library


def test_render_md_image_without_alt_stays_plain():
    html = render_md("![](photo.jpg)")
    assert "<figure>" not in html
    assert "<img" in html


def test_render_md_image_with_alt_becomes_figure():
    html = render_md("![A cat](photo.jpg)")
    assert "<figure>" in html
    assert "<figcaption>A cat</figcaption>" in html


def test_render_md_attr_list_syntax_not_processed():
    """![](src){width="200"} must NOT apply as an attribute — use title convention instead."""
    html = render_md('![alt](photo.jpg){width="200"}')
    assert 'width="200"' not in html


def test_render_md_plain_title_stays_as_title():
    html = render_md('![A cat](photo.jpg "A cute cat")')
    assert 'title="A cute cat"' in html
    assert "width" not in html
    assert "style" not in html


def test_render_md_attr_block_style():
    html = render_md("![A cat](photo.jpg \"Title {style='width:100px'}\")")
    assert 'style="width:100px"' in html
    assert 'title="Title"' in html


def test_render_md_attr_block_width_and_height():
    html = render_md("![A cat](photo.jpg \"Title {width='100' height='75'}\")")
    assert 'width="100"' in html
    assert 'height="75"' in html
    assert 'title="Title"' in html


def test_render_md_attr_block_only_no_title():
    html = render_md("![A cat](photo.jpg \"{width='200'}\")")
    assert 'width="200"' in html
    assert "title=" not in html


def test_render_md_attr_block_multiple_attrs():
    html = render_md(
        "![A cat](photo.jpg \"Title {width='100' style='border: 1px solid red;'}\")"
    )
    assert 'width="100"' in html
    assert "border: 1px solid red" in html
    assert 'title="Title"' in html


def test_render_md_empty_and_none():
    assert render_md("") == ""
    assert render_md(None) == ""


# absolutify_urls


def test_absolutify_root_relative():
    html = '<img src="/images/foo.jpg">'
    result = absolutify_urls(
        html, "https://example.com", "https://example.com/newsletter/ed/"
    )
    assert 'src="https://example.com/images/foo.jpg"' in result


def test_absolutify_relative():
    html = '<img src="photo.jpg">'
    result = absolutify_urls(
        html, "https://example.com", "https://example.com/newsletter/ed/"
    )
    assert 'src="https://example.com/newsletter/ed/photo.jpg"' in result


def test_absolutify_leaves_absolute_alone():
    html = '<img src="https://cdn.example.com/img.jpg">'
    result = absolutify_urls(
        html, "https://example.com", "https://example.com/newsletter/ed/"
    )
    assert 'src="https://cdn.example.com/img.jpg"' in result


# build_email_html — end-to-end


def test_email_html_contains_greeting():
    post = make_post()
    html = build_email_html(
        "test-ed", post, FOOTER_MD, HUGO_CONFIG, recipient_name="Alice"
    )
    assert "Hi Alice," in html


def test_email_html_default_greeting():
    post = make_post()
    html = build_email_html("test-ed", post, FOOTER_MD, HUGO_CONFIG)
    assert "Hi," in html


def test_email_html_renders_body():
    post = make_post(body="Read all about **it**.")
    html = build_email_html("test-ed", post, FOOTER_MD, HUGO_CONFIG)
    assert "<strong>it</strong>" in html


def test_email_html_renders_intro():
    post = make_post(intro="Short intro.")
    html = build_email_html("test-ed", post, FOOTER_MD, HUGO_CONFIG)
    assert "Short intro." in html


def test_email_html_intro_with_blank_lines():
    post = make_post(intro="Para one.\n\nPara two.")
    html = build_email_html("test-ed", post, FOOTER_MD, HUGO_CONFIG)
    assert "Para one." in html
    assert "Para two." in html


def test_email_html_renders_footer():
    post = make_post()
    html = build_email_html("test-ed", post, FOOTER_MD, HUGO_CONFIG)
    assert "Unsubscribe" in html


def test_email_html_no_footer_when_empty():
    post = make_post()
    html = build_email_html("test-ed", post, "", HUGO_CONFIG)
    assert "border-top" not in html


def test_email_html_absolutifies_relative_image():
    post = make_post(body="![Cat](cat.jpg)")
    html = build_email_html("test-ed", post, FOOTER_MD, HUGO_CONFIG)
    assert "https://example.com/newsletter/test-ed/cat.jpg" in html


def test_email_html_absolutifies_root_relative_image():
    post = make_post(body="![Logo](/images/logo.png)")
    html = build_email_html("test-ed", post, FOOTER_MD, HUGO_CONFIG)
    assert "https://example.com/images/logo.png" in html


def test_email_html_view_in_browser_link():
    post = make_post()
    html = build_email_html("test-ed", post, FOOTER_MD, HUGO_CONFIG)
    assert "https://example.com/newsletter/test-ed/" in html


def test_email_html_css_inlined():
    post = make_post()
    html = build_email_html("test-ed", post, FOOTER_MD, HUGO_CONFIG)
    # css-inline moves <style> rules into inline style= attributes
    assert 'style="' in html
    assert "font-family" in html


def test_email_html_image_with_alt_becomes_figure():
    post = make_post(body="![A sunset](sunset.jpg)")
    html = build_email_html("test-ed", post, FOOTER_MD, HUGO_CONFIG)
    assert "<figure" in html
    assert "A sunset" in html
    assert "figcaption" in html


# build_email_html — edge cases


def test_email_html_empty_body():
    post = make_post(body="")
    html = build_email_html("test-ed", post, FOOTER_MD, HUGO_CONFIG)
    assert "Hi," in html  # renders without crashing


def test_email_html_no_intro():
    post = make_post(intro="")
    html = build_email_html("test-ed", post, FOOTER_MD, HUGO_CONFIG)
    assert "font-style:italic" not in html


def test_email_html_base_url_trailing_slash_not_doubled():
    config = {"baseURL": "https://example.com/"}
    post = make_post(body="![img](photo.jpg)")
    html = build_email_html("test-ed", post, FOOTER_MD, config)
    assert "example.com//newsletter" not in html
    assert "https://example.com/newsletter/test-ed/photo.jpg" in html


def test_email_html_multiple_images_all_absolutified():
    post = make_post(body="![A](a.jpg)\n\n![B](b.jpg)\n\n![C](/images/c.jpg)")
    html = build_email_html("test-ed", post, FOOTER_MD, HUGO_CONFIG)
    assert "https://example.com/newsletter/test-ed/a.jpg" in html
    assert "https://example.com/newsletter/test-ed/b.jpg" in html
    assert "https://example.com/images/c.jpg" in html


# build_email_html — empty baseURL produces non-absolute image paths
# (documents known behaviour: send is blocked at the UI layer if not deployed,
# but callers should be aware that images will be broken without a baseURL)


def test_email_html_empty_base_url_image_paths_are_not_absolute():
    post = make_post(body="![Cat](cat.jpg)")
    html = build_email_html("test-ed", post, FOOTER_MD, {"baseURL": ""})
    # Without a baseURL, relative images become root-relative — broken in email
    assert "https://" not in html.split("cat.jpg")[0].split("<img")[-1]


# build_email_html — recipient name edge cases


def test_email_html_whitespace_only_name_falls_back_to_generic_greeting():
    post = make_post()
    html = build_email_html(
        "test-ed", post, FOOTER_MD, HUGO_CONFIG, recipient_name="   "
    )
    assert "Hi   ," not in html
    assert "Hi," in html


LOCALHOST_CONFIG = {"baseURL": "http://127.0.0.1:5000"}


# preview HTML (build_email_html with localhost base URL) — same function, local images


def test_preview_html_renders_body():
    post = make_post(body="Read all about **it**.")
    html = build_email_html("test-ed", post, FOOTER_MD, LOCALHOST_CONFIG)
    assert "<strong>it</strong>" in html


def test_preview_html_renders_intro():
    post = make_post(intro="A quick note.")
    html = build_email_html("test-ed", post, FOOTER_MD, LOCALHOST_CONFIG)
    assert "A quick note." in html


def test_preview_html_renders_footer():
    post = make_post()
    html = build_email_html("test-ed", post, FOOTER_MD, LOCALHOST_CONFIG)
    assert "Unsubscribe" in html


def test_preview_html_no_footer_when_empty():
    post = make_post()
    html = build_email_html("test-ed", post, "", LOCALHOST_CONFIG)
    assert "Unsubscribe" not in html


def test_preview_html_image_with_alt_becomes_figure():
    post = make_post(body="![A sunset](sunset.jpg)")
    html = build_email_html("test-ed", post, FOOTER_MD, LOCALHOST_CONFIG)
    assert "<figure" in html
    assert "A sunset" in html
    assert "figcaption" in html


def test_preview_html_relative_image_uses_localhost():
    post = make_post(body="![img](photo.jpg)")
    html = build_email_html("test-ed", post, FOOTER_MD, LOCALHOST_CONFIG)
    assert "http://127.0.0.1:5000/newsletter/test-ed/photo.jpg" in html


def test_preview_html_root_relative_image_uses_localhost():
    post = make_post(body="![logo](/images/logo.png)")
    html = build_email_html("test-ed", post, FOOTER_MD, LOCALHOST_CONFIG)
    assert "http://127.0.0.1:5000/images/logo.png" in html


# build_email_html — email_only mode (embedded images, no view-in-browser)


def test_email_only_omits_view_in_browser(tmp_path):
    post = make_post()
    html = build_email_html(
        "test-ed", post, FOOTER_MD, HUGO_CONFIG, email_only=True, edition_dir=tmp_path
    )
    assert "View in browser" not in html
    assert "view-in-browser" not in html


def test_email_only_embeds_relative_image_as_data_uri(tmp_path):
    img_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20  # fake PNG bytes
    (tmp_path / "photo.png").write_bytes(img_bytes)
    post = make_post(body="![A photo](photo.png)")
    html = build_email_html(
        "test-ed", post, FOOTER_MD, HUGO_CONFIG, email_only=True, edition_dir=tmp_path
    )
    expected = "data:image/png;base64," + base64.b64encode(img_bytes).decode()
    assert expected in html


def test_email_only_does_not_embed_missing_image(tmp_path):
    """Missing image src is left as-is rather than crashing."""
    post = make_post(body="![Ghost](ghost.png)")
    html = build_email_html(
        "test-ed", post, FOOTER_MD, HUGO_CONFIG, email_only=True, edition_dir=tmp_path
    )
    assert "ghost.png" in html
    assert "data:" not in html


def test_email_only_leaves_external_images_alone(tmp_path):
    post = make_post(body="![Ext](https://cdn.example.com/img.jpg)")
    html = build_email_html(
        "test-ed", post, FOOTER_MD, HUGO_CONFIG, email_only=True, edition_dir=tmp_path
    )
    assert "https://cdn.example.com/img.jpg" in html
    assert "data:" not in html


def test_email_only_embeds_root_relative_image_from_static(tmp_path):
    """Root-relative images are resolved from {REPO_ROOT}/static/ and embedded."""
    from patr import state

    state.REPO_ROOT = tmp_path
    static_img = tmp_path / "static" / "images" / "newsletter"
    static_img.mkdir(parents=True)
    img_bytes = b"PNGDATA"
    (static_img / "upi-qr.png").write_bytes(img_bytes)
    footer_md = "![QR](/images/newsletter/upi-qr.png)"
    post = make_post()
    html = build_email_html(
        "test-ed", post, footer_md, HUGO_CONFIG, email_only=True, edition_dir=tmp_path
    )
    expected = "data:image/png;base64," + base64.b64encode(img_bytes).decode()
    assert expected in html


def test_email_only_embedded_image_alt_is_filename(tmp_path):
    """Embedded images use the filename as alt to avoid newlines in Gmail MIME attachment names."""
    (tmp_path / "photo.jpg").write_bytes(b"JPGDATA")
    post = make_post(body="![Multi\nline\nalt](photo.jpg)")
    html = build_email_html(
        "test-ed", post, FOOTER_MD, HUGO_CONFIG, email_only=True, edition_dir=tmp_path
    )
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    img = soup.find("img", src=lambda s: s and s.startswith("data:"))
    assert img is not None
    assert img.get("alt") == "photo.jpg"


def test_email_only_leaves_missing_root_relative_alone(tmp_path):
    """Root-relative images that don't exist on disk are left as-is."""
    from patr import state

    state.REPO_ROOT = tmp_path
    post = make_post(body="![Logo](/images/logo.png)")
    html = build_email_html(
        "test-ed", post, FOOTER_MD, HUGO_CONFIG, email_only=True, edition_dir=tmp_path
    )
    assert "/images/logo.png" in html
    assert "data:" not in html


def test_normal_mode_still_has_view_in_browser():
    post = make_post()
    html = build_email_html("test-ed", post, FOOTER_MD, HUGO_CONFIG)
    assert "View in browser" in html


# shared CSS — must hold for both production email and preview


def test_img_max_width_constrained():
    post = make_post(body="![img](photo.jpg)")
    for config in [HUGO_CONFIG, LOCALHOST_CONFIG]:
        html = build_email_html("test-ed", post, FOOTER_MD, config)
        assert "max-width" in html


def test_footer_img_constrained_smaller_than_body_imgs():
    """Footer images must be narrower than body images — e.g. QR codes."""
    footer_with_img = "![QR](/images/qr.png)"
    post = make_post()
    html = build_email_html("test-ed", post, footer_with_img, HUGO_CONFIG)
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    footer_div = soup.find("div", style=lambda s: s and "border-top" in s)
    assert footer_div is not None, "footer div not found"
    img = footer_div.find("img")
    assert img is not None, "no img in footer"
    style = str(img.get("style", ""))
    assert "max-width" in style
    assert "200px" in style
