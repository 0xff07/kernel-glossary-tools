"""sections.caution: the H1, a blank line and the three CAUTION lines, byte for
byte."""

import re

from tools.qa.inputs import violation


def check(page, context):
    lines = page.lines
    # line 1 is the H1, `# ` and a title; e.g. `# Memmap initialization at
    # boot`
    if not lines or not re.match(r"^# \S", lines[0]):
        yield violation(
            1, lines[0] if lines else "", "line 1 is not the H1 `# <topic>`"
        )
    if len(lines) < 5:
        yield violation(
            None, None, "the page is shorter than its H1 and CAUTION block"
        )
        return
    if lines[1].strip():
        yield violation(2, lines[1], "line 2 is not blank")
    for k, wanted in enumerate(page.profile.caution_lines):
        if lines[2 + k] != wanted:
            yield violation(
                3 + k,
                lines[2 + k],
                f"line {3 + k} is not the CAUTION line `{wanted}` byte for"
                " byte",
            )
