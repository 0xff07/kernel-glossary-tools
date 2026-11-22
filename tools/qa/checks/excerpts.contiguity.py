"""excerpts.contiguity: an elision begun inside a function resumes inside it, a
unit outside a function drops one run, and the run after an elision is at least
the rule's minimum or the closing line alone.
"""

import re

from tools.qa.inputs import rule_body, violation

WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


def check(page, context):
    # the number the rule file states in words, group 1; e.g. `at least three
    # contiguous source lines` gives three
    found = re.search(
        r"at least (\w+) contiguous source lines",
        rule_body(context, "excerpts.contiguity"),
    )
    minimum = WORDS.get(
        found.group(1), int(found.group(1)) if found.group(1).isdigit() else 3
    )
    tree = context.require("tree")
    context.require("facts")
    for unit in page.units:
        if not unit.elisions or unit.mapped is None:
            continue
        outside = 0
        for index, (n, _dropped, resumes) in enumerate(unit.elisions):
            before = [f for p, f in unit.mapped if p < n]
            limit = (
                unit.elisions[index + 1][0]
                if index + 1 < len(unit.elisions)
                else None
            )
            after = [
                f
                for p, f in unit.mapped
                if p > n and (limit is None or p < limit)
            ]
            construct = (
                tree.construct_at(unit.path, before[-1]) if before else None
            )
            if construct and construct["kind"] == "function":
                if not construct["head"] <= resumes <= construct["end"]:
                    yield violation(
                        n,
                        unit.label,
                        f"{unit.label} elides from inside"
                        f" {construct['name']}() to {unit.path}:{resumes}"
                        " outside it; an elision begun inside a function"
                        " resumes inside it",
                    )
                    continue
            else:
                outside += 1
                if outside > 1:
                    yield violation(
                        n,
                        unit.label,
                        f"{unit.label} carries {outside} elisions outside a"
                        " function; a definition drops one run",
                    )
                    continue
            holder = tree.construct_at(unit.path, resumes)
            closing = holder is not None and after == [holder["end"]]
            if after and len(after) < minimum and not closing:
                yield violation(
                    n,
                    unit.label,
                    f"{unit.label} shows {len(after)} line(s) after its"
                    f" elision; a run is at least {minimum} lines or the"
                    " closing line alone",
                )
