"""The web newsletter's layout CSS (data/assets/newsletter.css, installed into
the Hugo site) must hold up on a phone. These check that the rules exist, not
their exact values, by inlining the real stylesheet into sample markup.
"""

from pathlib import Path

import css_inline
import patr
from bs4 import BeautifulSoup

CSS = (Path(patr.__file__).parent / "data" / "assets" / "newsletter.css").read_text()

PAGE = """
<div class="newsletter-archive"><ol class="newsletter-list"></ol></div>
<article class="newsletter-post">
  <div class="newsletter-intro"><p>Intro one</p><p>Intro two</p></div>
  <div class="newsletter-post-content"><p>First</p><p>Second</p></div>
  <div class="newsletter-footer-content"><p>Footer</p></div>
  <figure class="newsletter-figure"><figcaption>Caption</figcaption></figure>
</article>
"""


def inlined() -> BeautifulSoup:
    return BeautifulSoup(
        css_inline.inline(f"<style>{CSS}</style>{PAGE}"), "html.parser"
    )


def style_props(el) -> dict:
    props = {}
    for decl in str(el.get("style", "")).split(";"):
        if ":" in decl:
            key, value = decl.split(":", 1)
            props[key.strip()] = value.strip()
    return props


def is_zero(value: str) -> bool:
    return value in ("0", "0px", "0rem", "0em")


def test_columns_have_side_gutters_so_text_never_touches_the_screen_edge() -> None:
    soup = inlined()
    for cls in ("newsletter-post", "newsletter-archive"):
        props = style_props(soup.find(class_=cls))
        for side in ("padding-left", "padding-right"):
            assert side in props and not is_zero(props[side]), (cls, side)


def test_columns_size_their_padding_predictably() -> None:
    """Gutters must not shrink (or overflow) the text column on a host site
    whose global box-sizing differs."""
    soup = inlined()
    for cls in ("newsletter-post", "newsletter-archive"):
        assert style_props(soup.find(class_=cls)).get("box-sizing") == "border-box"


def test_long_words_and_urls_wrap_instead_of_overflowing() -> None:
    soup = inlined()
    for cls in (
        "newsletter-post-content",
        "newsletter-intro",
        "newsletter-footer-content",
    ):
        wrap = style_props(soup.find(class_=cls)).get("overflow-wrap")
        assert wrap in ("anywhere", "break-word"), cls


def test_paragraphs_are_spaced_apart_like_in_the_email() -> None:
    """A host site's global reset can zero paragraph margins."""
    soup = inlined()
    for cls in ("newsletter-post-content", "newsletter-footer-content"):
        first = soup.find(class_=cls).find("p")
        margin = style_props(first).get("margin-bottom")
        assert margin and not is_zero(margin), cls


def test_muted_text_follows_the_sites_text_colour_not_a_fixed_grey() -> None:
    """A fixed grey made for a light page is hard to read on a dark site, so
    the muted colour must be derived from the text colour it sits next to."""
    muted = style_props(inlined().find("html"))["--newsletter-muted"]
    assert "currentcolor" in muted.lower()


def test_intro_and_captions_use_the_muted_colour() -> None:
    soup = inlined()
    for el in (soup.find(class_="newsletter-intro"), soup.find("figcaption")):
        assert "var(--newsletter-muted)" in style_props(el).get("color", "")


def test_divider_lines_follow_the_sites_text_colour_too() -> None:
    """A fixed light grey rule is a harsh bright line on a dark site."""
    border = style_props(inlined().find("html"))["--newsletter-border"]
    assert "currentcolor" in border.lower()
