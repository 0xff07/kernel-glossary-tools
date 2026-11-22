"""drawing.legend: every drawn mark has an entry, every entry marks a drawn
mark and carries its phrase, and with the tree every entry's site is reproduced
and lies in the function the entry names.
"""

import re

from tools.qa.inputs import rule_body, violation
from tools.qa.source import resolve_cited

WORDS = {"two": 2, "three": 3, "four": 4, "five": 5}


def check(page, context):
    # the number the rule file states in words, group 1; e.g. `at least three
    # words` gives three
    found = re.search(
        r"at least (\w+) words", rule_body(context, "drawing.legend")
    )
    phrase_words = WORDS.get(
        found.group(1), int(found.group(1)) if found.group(1).isdigit() else 3
    )
    pending = []
    for fence in page.figures:
        entries = page.legends.get(fence.start) or []
        drawn = page.drawn_marks.get(fence.start) or set()
        legend_marks = {e.mark for e in entries}
        for mark in sorted(drawn - legend_marks):
            yield violation(
                fence.start,
                mark,
                f"mark {mark} in the drawing has no legend entry",
            )
        for e in entries:
            if e.mark not in drawn:
                yield violation(
                    e.line,
                    page.lines[e.line - 1].strip(),
                    f"legend entry {e.mark} marks nothing in the drawing",
                )
            if len(e.phrase.split()) < phrase_words:
                yield violation(
                    e.line,
                    page.lines[e.line - 1].strip(),
                    f"legend entry {e.mark} {e.name} carries no phrase saying"
                    " what happens there",
                )
            pending.append(e)
    if not pending:
        return
    tree = context.require("tree")
    context.require("facts")
    for e in pending:
        where = page.lines[e.line - 1].strip()
        if not e.file:
            yield violation(
                e.line, where, f"legend entry {e.mark} names no file"
            )
            continue
        path, why = resolve_cited(page, e.file)
        if path is None:
            yield violation(
                e.line, where, f"legend entry {e.mark}: {e.file} {why}"
            )
            continue
        if tree.line(path, e.source_line) is None:
            yield violation(
                e.line,
                where,
                f"legend entry {e.mark}: {path}:{e.source_line} is beyond the"
                " file",
            )
            continue
        construct = tree.construct_at(path, e.source_line)
        if construct is None or construct["name"] != e.name:
            holder = (
                f"{construct['kind']} {construct['name']}"
                f" ({construct['line']}-{construct['end']})"
                if construct
                else "no construct"
            )
            yield violation(
                e.line,
                where,
                f"legend entry {e.mark}: {path}:{e.source_line} does not lie"
                f" in {e.name}(): {holder} holds that line",
            )
        if e.source_line not in context.reproduced.get(path, set()):
            yield violation(
                e.line,
                where,
                f"legend entry {e.mark}: no excerpt reproduces"
                f" {path}:{e.source_line}",
            )
