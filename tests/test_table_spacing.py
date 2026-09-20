"""Markdown tables in an edition are borderless, so their columns run together
unless the cells have padding. The spacing must reach only the edition's own
tables — not the email shell's layout tables — and must be flush with the text
at the table's outer edges."""

from pathlib import Path

import css_inline
import frontmatter
import patr
from bs4 import BeautifulSoup
from patr.content import build_email_html

ASSETS = Path(patr.__file__).parent / "data" / "assets"
HUGO_CONFIG = {"baseURL": "https://example.com"}
TABLE_MD = "| Name | Qty |\n|------|-----|\n| Tea | 2 |\n| Biscuits | 12 |\n"
TABLE_HTML = (
    "<table><thead><tr><th>Name</th><th>Qty</th></tr></thead>"
    "<tbody><tr><td>Tea</td><td>2</td></tr></tbody></table>"
)


def padding(cell, side: str) -> str:
    """The cell's inline padding on one side ('top'/'right'/'bottom'/'left'),
    expanding the `padding` shorthand and letting a longhand override it."""
    props = {}
    for decl in str(cell.get("style", "")).split(";"):
        if ":" in decl:
            key, value = decl.split(":", 1)
            props[key.strip()] = value.strip()
    sides = ["top", "right", "bottom", "left"]
    values = props.get("padding", "0").split()
    if len(values) == 1:
        expanded = values * 4
    elif len(values) == 2:
        expanded = [values[0], values[1], values[0], values[1]]
    elif len(values) == 3:
        expanded = [values[0], values[1], values[2], values[1]]
    else:
        expanded = values
    return props.get(f"padding-{side}", expanded[sides.index(side)])


def em(value: str) -> float:
    """A padding value as a number of em ('0' is 0; other units aren't used
    for the table spacing)."""
    return 0.0 if value in ("0", "0px", "0em") else float(value.removesuffix("em"))


def collapsed(table) -> bool:
    """Whether the table has `border-collapse: collapse` inline."""
    style = str(table.get("style", "")).replace(" ", "")
    return "border-collapse:collapse" in style


def email_cells():
    text = f"---\ntitle: T\ndate: 2024-03-15\n---\n\n{TABLE_MD}"
    html = build_email_html("test-ed", frontmatter.loads(text), "", HUGO_CONFIG)
    soup = BeautifulSoup(html, "html.parser")
    return soup, soup.find("th", string="Name"), soup.find("th", string="Qty")


def web_cells(wrapper_class: str):
    css = (ASSETS / "newsletter.css").read_text()
    page = f'<article class="newsletter-post"><div class="{wrapper_class}">{TABLE_HTML}</div></article>'
    html = css_inline.inline(f"<style>{css}</style>{page}")
    soup = BeautifulSoup(html, "html.parser")
    return soup.find("th", string="Name"), soup.find("th", string="Qty")


def test_email_table_columns_have_space_between_them() -> None:
    _, first, last = email_cells()
    gap = em(padding(first, "right")) + em(padding(last, "left"))
    assert gap > 0


def test_email_table_is_flush_with_the_text_at_its_edges() -> None:
    _, first, last = email_cells()
    assert em(padding(first, "left")) == 0
    assert em(padding(last, "right")) == 0


def test_email_table_rows_have_some_vertical_room() -> None:
    _, first, _ = email_cells()
    assert em(padding(first, "top")) > 0
    assert em(padding(first, "bottom")) > 0


def test_email_shell_layout_cells_are_left_alone() -> None:
    """The email's own layout table keeps its 40px/20px page padding."""
    soup, _, _ = email_cells()
    shell = soup.find("td", style=lambda s: s and "40px" in s)
    assert shell is not None
    assert padding(shell, "left") == "20px"
    assert padding(shell, "top") == "40px"


def test_email_table_has_no_default_cell_spacing() -> None:
    """Without border-collapse, mail clients inset the whole table by their
    default border-spacing (2px), so it wouldn't line up with the text."""
    _, first, _ = email_cells()
    assert collapsed(first.find_parent("table"))


def test_web_table_columns_have_space_between_them() -> None:
    first, last = web_cells("newsletter-post-content")
    gap = em(padding(first, "right")) + em(padding(last, "left"))
    assert gap > 0


def test_web_table_is_flush_with_the_text_at_its_edges() -> None:
    first, last = web_cells("newsletter-post-content")
    assert em(padding(first, "left")) == 0
    assert em(padding(last, "right")) == 0


def test_web_footer_tables_get_the_same_spacing() -> None:
    first, last = web_cells("newsletter-footer-content")
    gap = em(padding(first, "right")) + em(padding(last, "left"))
    assert gap > 0


def test_web_table_has_no_default_cell_spacing() -> None:
    first, _ = web_cells("newsletter-post-content")
    assert collapsed(first.find_parent("table"))
