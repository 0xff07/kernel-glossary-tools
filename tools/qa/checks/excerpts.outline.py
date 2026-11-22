"""excerpts.outline: a function walked in pieces has an outline table before
its first piece whose rows are the pieces' ranges, and each piece's mark stands
in the line above its fence."""

from tools.qa.inputs import violation
from tools.qa.page import mark_occurrences
from tools.qa.source import owned_functions, pieces, walked_definitions


def check(page, context):
    tree = context.require("tree")
    context.require("facts")
    claimed = set()
    walkable = [
        (f"{name}()", path, start, end)
        for name, path, start, end in owned_functions(page, tree)
    ]
    walkable += walked_definitions(page, tree)
    for label, path, start, end in walkable:
        walked = pieces(page, path, start, end)
        if len(walked) < 2:
            continue
        first_fence = walked[0][0].fence.start
        base = path.rsplit("/", 1)[-1]
        candidates = [
            (line, rows)
            for line, rows in page.outline_tables
            if line < first_fence
            and line not in claimed
            and any(f.rsplit("/", 1)[-1] == base for _m, f, _a, _b in rows)
        ]
        table = candidates[-1] if candidates else None
        name = label[:-2] if label.endswith("()") else label
        if table is None:
            yield violation(
                first_fence,
                name,
                f"{label} is walked in {len(walked)} pieces with no outline"
                f" table naming {base} before its first piece",
            )
            continue
        claimed.add(table[0])
        wanted = [(inside[0], inside[-1]) for _u, inside in walked]
        rows = [(a, b) for _m, _f, a, b in table[1]]
        if rows != wanted:
            yield violation(
                table[0],
                name,
                f"{label}: the outline's rows {rows} differ from the pieces"
                f" shown {wanted}",
            )
            continue
        for (unit, _inside), (mark, _f, _a, _b) in zip(walked, table[1]):
            above = page.prose_line_above(unit.fence.start)
            if above is None or not mark_occurrences(
                page.lines[above - 1], [mark]
            ):
                yield violation(
                    unit.start,
                    name,
                    f"{label}: the sentence above the piece at {unit.label}"
                    f" does not carry its mark {mark}",
                )
