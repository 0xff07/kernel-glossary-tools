"""lifecycle.order: within each DETAILS figure, the sites its legend marks are
first shown in the order of the marks' indices; rows of one index have no order
among them, and a legend mark outside the figure families is a candidate.
"""

import collections

from tools.qa.inputs import candidate
from tools.qa.page import figure_mark, mark_index
from tools.qa.source import resolve_cited


def check(page, context):
    pending = []
    for fence in page.figures:
        if page.section_of(fence.start).name != "DETAILS":
            continue
        for entry in page.legends.get(fence.start) or []:
            if not figure_mark(entry.mark):
                yield candidate(
                    None,
                    entry.mark,
                    f"legend mark {entry.mark!r} is outside the figure"
                    " families; no order is read from it",
                )
                continue
            pending.append((fence.start, entry))
    if not pending:
        return
    context.require("tree")
    groups = collections.defaultdict(lambda: collections.defaultdict(list))
    for figure, entry in pending:
        path = resolve_cited(page, entry.file)[0] if entry.file else None
        if path is None:
            continue
        shown = next(
            (
                u.start
                for u in page.units
                if u.path == path and entry.source_line in u.file_lines
            ),
            None,
        )
        if shown is None:
            continue
        groups[figure][mark_index(entry.mark)].append((entry, shown))
    for indices in groups.values():
        previous = None
        for index in sorted(indices):
            bucket = indices[index]
            for entry, shown in bucket:
                if previous is not None and shown < previous[1]:
                    yield candidate(
                        shown,
                        entry.mark,
                        f"the write marked {entry.mark} ({entry.name}"
                        f" {entry.file}:{entry.source_line}) is shown at page"
                        f" {shown}, before {previous[0]} at page"
                        f" {previous[1]}",
                    )
            entry, shown = max(bucket, key=lambda item: item[1])
            previous = (entry.mark, shown)
