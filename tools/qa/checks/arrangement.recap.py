"""arrangement.recap: a `So far,` recap at most every sixth DETAILS subsection,
within its sentence band."""

import re

from tools.qa.inputs import candidate, limits_of, measured, rule_body
from tools.qa.page import RECAP, first_sentence, prose_text, sentences_of

ORDINALS = {
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
}


def check(page, context):
    body = rule_body(context, "arrangement.recap")
    # the ordinal the rule file states, group 1; e.g. `The seventh DETAILS
    # subsection in a row without a recap` gives seventh
    every = ORDINALS[
        re.search(
            r"The (\w+) DETAILS subsection in a row without a recap", body
        ).group(1)
    ]
    limits = limits_of(context, "arrangement.recap", "a recap", "sentences")
    run = 0
    for sub in page.subsections:
        recaps = [
            i
            for i in sub["items"]
            if i.kind == "P" and RECAP.match(prose_text(i.text))
        ]
        for recap in recaps:
            finding = measured(
                recap.line,
                first_sentence(recap.text),
                "a recap",
                len(sentences_of(recap.text)),
                "sentences",
                **limits,
            )
            if finding:
                yield finding
        if recaps:
            run = 0
            continue
        run += 1
        if run == every:
            yield candidate(
                sub["line"],
                sub["title"],
                f"[{sub['title']}] is the {every}th subsection since the last"
                " recap; a `So far,` recap closes a subsection at most every"
                f" {every - 1}",
            )
            run = 0
