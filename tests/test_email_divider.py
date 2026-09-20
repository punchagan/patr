"""A markdown thematic break (`* * *` or `---` with blank lines around it)
renders as a hard grey line edge to edge. In an email it becomes a soft,
centred ornament instead - built from a table with inline styles only, since
mail clients strip SVG, images (blocked, or behind a login), masks and
pseudo-elements."""

import frontmatter
import pytest
from bs4 import BeautifulSoup
from patr.content import build_email_html, build_email_plain

HUGO_CONFIG = {"baseURL": "https://example.com"}
ORNAMENT = "✿"  # the florette in the middle


def build(body="", intro="", footer="", **kwargs) -> BeautifulSoup:
    post = frontmatter.Post(body, title="T", date="2024-03-15", intro=intro)
    html = build_email_html("test-ed", post, footer, HUGO_CONFIG, **kwargs)
    return BeautifulSoup(html, "html.parser")


def dividers(soup):
    return soup.find_all("table", class_="divider")


def style_of(el) -> dict:
    props = {}
    for decl in str(el.get("style", "")).split(";"):
        if ":" in decl:
            key, value = decl.split(":", 1)
            props[key.strip()] = value.strip()
    return props


def test_star_break_becomes_an_ornament() -> None:
    soup = build("Before.\n\n* * *\n\nAfter.")
    assert soup.find("hr") is None
    assert len(dividers(soup)) == 1


def test_dash_break_with_blank_lines_becomes_an_ornament() -> None:
    soup = build("Before.\n\n---\n\nAfter.")
    assert soup.find("hr") is None
    assert len(dividers(soup)) == 1


def test_every_break_is_replaced() -> None:
    soup = build("A\n\n* * *\n\nB\n\n* * *\n\nC\n\n---\n\nD")
    assert soup.find("hr") is None
    assert len(dividers(soup)) == 3


def test_breaks_in_the_intro_and_footer_too() -> None:
    soup = build(body="Body.", intro="One\n\n* * *\n\nTwo", footer="A\n\n* * *\n\nB")
    assert soup.find("hr") is None
    assert len(dividers(soup)) == 2


def test_ornament_is_email_safe_and_centred() -> None:
    (table,) = dividers(build("A\n\n* * *\n\nB"))
    assert table.get("role") == "presentation"
    assert table.get("align") == "center"
    assert ORNAMENT in table.get_text()
    assert table.find(["img", "svg", "style"]) is None
    assert table.find("td").get("style")  # styled inline, not by a stylesheet


def test_ornament_cells_keep_no_padding_from_the_content_table_rules() -> None:
    """email.css pads every table cell inside the edition's content; the
    ornament's cells must stay flush."""
    (table,) = dividers(build("A\n\n* * *\n\nB"))
    for cell in table.find_all("td"):
        props = style_of(cell)
        assert props.get("padding") in ("0", "0px"), props
        for side in ("left", "right", "top", "bottom"):
            assert props.get(f"padding-{side}", "0") in ("0", "0px")


def test_the_rule_above_footnotes_is_left_alone() -> None:
    soup = build("Text[^1]\n\n[^1]: A note.")
    footnotes = soup.find("div", class_="footnote")
    assert footnotes is not None
    assert footnotes.find("hr") is not None
    assert dividers(footnotes) == []


def test_the_rule_above_footnotes_is_a_quiet_hairline() -> None:
    footnotes = build("Text[^1]\n\n[^1]: A note.").find("div", class_="footnote")
    rule = style_of(footnotes.find("hr"))
    assert rule.get("border-top", "").startswith("1px solid")


@pytest.mark.parametrize(
    "kwargs",
    [{"email_only": True}, {"subscribers_only": True}],
    ids=lambda k: next(iter(k)),
)
def test_ornament_in_every_mode(kwargs, tmp_path) -> None:
    soup = build("A\n\n* * *\n\nB", edition_dir=tmp_path, **kwargs)
    assert soup.find("hr") is None
    assert len(dividers(soup)) == 1


def test_plain_text_keeps_the_break_as_written() -> None:
    post = frontmatter.loads("---\ntitle: T\n---\n\nA\n\n* * *\n\nB\n")
    assert "* * *" in build_email_plain("test-ed", post, "", HUGO_CONFIG)
