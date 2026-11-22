"""arrangement.headings: a `###` heading under DETAILS within its word band."""

from tools.qa.inputs import candidate, limits_of
from tools.qa.page import word_count

RULE = "arrangement.headings"


def check(page, context):
    most = limits_of(context, RULE, "a `###` heading under details", "words")[
        "review"
    ]
    for sub in page.subsections:
        words = word_count(sub["title"])
        if words > most:
            yield candidate(
                sub["line"],
                sub["title"],
                f"a heading of {words} words; a declarative clause of at most"
                f" {most}",
            )
