"""Tests for content rendering — render_md, absolutify_urls, build_email_html, build_web_html."""
import frontmatter
from patr.content import render_md, absolutify_urls, build_email_html, build_web_html

HUGO_CONFIG = {"baseURL": "https://example.com"}

FOOTER_MD = "Unsubscribe [here](https://example.com/unsubscribe)."


def make_post(title="Test Edition", date="2024-03-15", intro="", body="Hello world."):
    text = f"---\ntitle: {title}\ndate: {date}\n"
    if intro:
        indented = "\n".join("  " + l for l in intro.splitlines())
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


def test_render_md_empty_and_none():
    assert render_md("") == ""
    assert render_md(None) == ""


# absolutify_urls

def test_absolutify_root_relative():
    html = '<img src="/images/foo.jpg">'
    result = absolutify_urls(html, "https://example.com", "https://example.com/newsletter/ed/")
    assert 'src="https://example.com/images/foo.jpg"' in result


def test_absolutify_relative():
    html = '<img src="photo.jpg">'
    result = absolutify_urls(html, "https://example.com", "https://example.com/newsletter/ed/")
    assert 'src="https://example.com/newsletter/ed/photo.jpg"' in result


def test_absolutify_leaves_absolute_alone():
    html = '<img src="https://cdn.example.com/img.jpg">'
    result = absolutify_urls(html, "https://example.com", "https://example.com/newsletter/ed/")
    assert 'src="https://cdn.example.com/img.jpg"' in result


# build_email_html — end-to-end

def test_email_html_contains_greeting():
    post = make_post()
    html = build_email_html("test-ed", post, FOOTER_MD, HUGO_CONFIG, recipient_name="Alice")
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


def test_email_html_css_inlined_by_premailer():
    post = make_post()
    html = build_email_html("test-ed", post, FOOTER_MD, HUGO_CONFIG)
    # premailer moves <style> rules into inline style= attributes
    assert "<style>" not in html or "font-family" in html  # inlined on body tag
    assert 'style="' in html


def test_email_html_image_with_alt_becomes_figure():
    post = make_post(body="![A sunset](sunset.jpg)")
    html = build_email_html("test-ed", post, FOOTER_MD, HUGO_CONFIG)
    assert "<figure>" in html
    assert "<figcaption>A sunset</figcaption>" in html


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


# build_web_html — end-to-end

def test_web_html_contains_title():
    post = make_post(title="My Newsletter")
    html = build_web_html("test-ed", post, FOOTER_MD)
    assert "My Newsletter" in html


def test_web_html_contains_date():
    post = make_post(date="2024-03-15")
    html = build_web_html("test-ed", post, FOOTER_MD)
    assert "2024-03-15" in html


def test_web_html_base_href():
    post = make_post()
    html = build_web_html("test-ed", post, FOOTER_MD)
    assert '<base href="/newsletter/test-ed/">' in html


def test_web_html_renders_intro():
    post = make_post(intro="A quick note.")
    html = build_web_html("test-ed", post, FOOTER_MD)
    assert "A quick note." in html


def test_web_html_renders_footer():
    post = make_post()
    html = build_web_html("test-ed", post, FOOTER_MD)
    assert "Unsubscribe" in html
