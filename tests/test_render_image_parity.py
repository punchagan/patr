"""Parity check between _parse_title_attrs() (Python) and the regex chain in
render-image.html (Hugo/Go template) — the two independent implementations
of the "{key='val'}" trailing image-title attribute convention.

There's no Hugo binary in this environment or in CI (see
.github/workflows/tests.yml), so the real Go template can't be executed and
asserted on here. Instead, _parse_title_attrs_hugo_port() is a faithful
Python translation of render-image.html's findRE/replaceRE calls. This only
proves the two *specs* agree for the shared fixture — it can't catch a case
where render-image.html itself is edited without this port being updated to
match. If you touch either implementation, update both plus
tests/fixtures/image_title_attrs.yaml.
"""

import re
from pathlib import Path

import pytest
import yaml
from patr.content import _parse_title_attrs

IMAGE_TITLE_ATTR_CASES = yaml.safe_load(
    (Path(__file__).parent / "fixtures" / "image_title_attrs.yaml").read_text()
)["cases"]

_HUGO_ATTR_KEYS = ("style", "width", "height")


def _parse_title_attrs_hugo_port(title: str) -> tuple[str, dict[str, str]]:
    """Python port of render-image.html's regex chain (post-fix — the block
    must be anchored to the end of the title, or a title with unrelated
    curly braces earlier in the text gets silently mangled; see the parity
    test's git history for the pre-fix version and the case that caught it):

        {{ with findRE `\\{[^}]*\\}\\s*$` .Title }}
          {{ $block := replaceRE `^\\{|\\}\\s*$` "" (index . 0) }}
          {{ with findRE `style='[^']*'` $block }} ... {{ end }}
          {{ with findRE `width='[^']*'` $block }} ... {{ end }}
          {{ with findRE `height='[^']*'` $block }} ... {{ end }}
          {{ $cleanTitle = trim (replaceRE `\\s*\\{[^}]*\\}\\s*$` "" $.Title) " " }}
        {{ end }}

    Unlike _parse_title_attrs(), which accepts any key='val' pair generically,
    Hugo's template only recognizes style/width/height by name — anything
    else in the block is silently ignored on the web side (a real, deliberate
    scope difference documented at the call site in render-image.html, not a
    bug this port needs to hide).
    """
    m = re.search(r"\{[^}]*\}\s*$", title)
    if not m:
        return title, {}
    block = re.sub(r"^\{|\}\s*$", "", m.group(0))
    attrs = {}
    for key in _HUGO_ATTR_KEYS:
        am = re.search(rf"{key}='[^']*'", block)
        if am:
            attrs[key] = re.sub(rf"^{key}='|'$", "", am.group(0))
    clean_title = re.sub(r"\s*\{[^}]*\}\s*$", "", title).strip()
    return clean_title, attrs


@pytest.mark.parametrize(
    "case", IMAGE_TITLE_ATTR_CASES, ids=[c["title"] for c in IMAGE_TITLE_ATTR_CASES]
)
def test_hugo_port_matches_python(case) -> None:
    """The two implementations must agree on clean_title and on every attr
    Hugo's template is scoped to understand (style/width/height) — see
    _parse_title_attrs_hugo_port's docstring for the one deliberate scope
    difference (arbitrary keys) this comparison excludes."""
    py_clean, py_attrs = _parse_title_attrs(case["title"])
    hugo_clean, hugo_attrs = _parse_title_attrs_hugo_port(case["title"])
    assert hugo_clean == py_clean
    scoped_py_attrs = {k: v for k, v in py_attrs.items() if k in _HUGO_ATTR_KEYS}
    assert hugo_attrs == scoped_py_attrs
