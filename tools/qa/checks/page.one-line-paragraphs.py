"""page.one-line-paragraphs: a prose line directly after another prose line,
before any renderer joins them."""

from tools.qa.inputs import violation
from tools.qa.page import readable


def check(page, context):
    for n in range(2, page.n + 1):
        if page.cls[n] == "prose" and page.cls[n - 1] == "prose":
            yield violation(
                n,
                readable(page.lines[n - 1]),
                "Separate paragraphs with a blank line; keep each paragraph on"
                " one raw line.",
            )
