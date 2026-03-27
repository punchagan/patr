"""Tests for render_md and absolutify_urls in content.py."""
from patr.content import render_md, absolutify_urls


# render_md

def test_render_md_basic_paragraph():
    assert "<p>Hello</p>" in render_md("Hello")


def test_render_md_bold():
    assert "<strong>bold</strong>" in render_md("**bold**")


def test_render_md_heading():
    assert "<h2>" in render_md("## Heading")


def test_render_md_image_without_alt_stays_plain():
    html = render_md("![](photo.jpg)")
    assert "<figure>" not in html
    assert "<img" in html


def test_render_md_image_with_alt_becomes_figure():
    html = render_md("![A cat](photo.jpg)")
    assert "<figure>" in html
    assert "<figcaption>A cat</figcaption>" in html


def test_render_md_empty_string():
    assert render_md("") == ""


def test_render_md_none():
    assert render_md(None) == ""


# absolutify_urls

def test_absolutify_root_relative_image():
    html = '<img src="/images/foo.jpg">'
    result = absolutify_urls(html, "https://example.com", "https://example.com/newsletter/ed/")
    assert 'src="https://example.com/images/foo.jpg"' in result


def test_absolutify_relative_image():
    html = '<img src="photo.jpg">'
    result = absolutify_urls(html, "https://example.com", "https://example.com/newsletter/ed/")
    assert 'src="https://example.com/newsletter/ed/photo.jpg"' in result


def test_absolutify_leaves_https_urls_alone():
    html = '<img src="https://cdn.example.com/img.jpg">'
    result = absolutify_urls(html, "https://example.com", "https://example.com/newsletter/ed/")
    assert 'src="https://cdn.example.com/img.jpg"' in result


def test_absolutify_mixed():
    html = '<img src="/a.jpg"> <img src="b.jpg"> <img src="https://c.com/c.jpg">'
    result = absolutify_urls(html, "https://example.com", "https://example.com/newsletter/ed/")
    assert 'src="https://example.com/a.jpg"' in result
    assert 'src="https://example.com/newsletter/ed/b.jpg"' in result
    assert 'src="https://c.com/c.jpg"' in result
