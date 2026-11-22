"""arrangement.route: DETAILS opens with one route paragraph within its
sentence band."""

from tools.qa.inputs import candidate, limits_of, measured, violation
from tools.qa.page import first_sentence, sentences_of


def check(page, context):
    details = page.section("DETAILS")
    if details is None or not page.subsections:
        return
    prose = [i for i in page.preamble_items if i.kind == "P"]
    if not prose:
        yield violation(
            details.start,
            None,
            "DETAILS has no route paragraph before its first subsection",
        )
        return
    count = len(sentences_of(prose[0].text))
    finding = measured(
        prose[0].line,
        first_sentence(prose[0].text),
        "the route",
        count,
        "sentences",
        **limits_of(
            context,
            "arrangement.route",
            "the first prose line of the DETAILS preamble",
            "sentences",
        ),
    )
    if finding:
        yield finding
    if len(prose) > 1:
        yield candidate(
            prose[1].line,
            first_sentence(prose[1].text),
            f"{len(prose)} paragraphs before the first subsection; the route"
            " is one",
        )
