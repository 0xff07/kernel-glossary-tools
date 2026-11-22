"""drawing.walk: the paragraph after a DETAILS figure with a legend names every
mark and links every function, in legend order."""

from tools.qa.inputs import candidate, violation
from tools.qa.page import LINK, mark_occurrences, symbol_name


def check(page, context):
    details = page.section("DETAILS")
    if details is None:
        return
    for fence in page.figures:
        if not details.start <= fence.start <= details.end:
            continue
        entries = page.legends.get(fence.start) or []
        if not entries:
            continue
        below = page.prose_line_below(fence.end)
        outro = page.lines[below - 1] if below else ""
        at = below or fence.end
        linked = page.linked_names_in(outro)
        positions = {}
        for mark, offset in mark_occurrences(outro):
            positions.setdefault(mark, offset)
        rank, name_rank = {}, {}
        for e in entries:
            rank.setdefault(e.mark, len(rank))
            name_rank.setdefault(e.name, rank[e.mark])
            if e.name not in linked:
                yield violation(
                    at,
                    f"{e.mark} {e.name}",
                    f"the paragraph after the figure does not link {e.name}()"
                    f" ({e.mark})",
                )
            if e.mark not in positions:
                yield violation(
                    at,
                    f"{e.mark} {e.name}",
                    "the paragraph after the figure does not name mark"
                    f" {e.mark} ({e.name}())",
                )
        marks_at = sorted(
            (positions[m], r) for m, r in rank.items() if m in positions
        )
        names_at = []
        for match in LINK.finditer(outro):
            name = symbol_name(match.group(1).strip("`"))
            if name in name_rank and name not in [n for _o, n in names_at]:
                names_at.append((match.start(), name))
        if [r for _o, r in marks_at] != sorted(r for _o, r in marks_at) or [
            name_rank[n] for _o, n in sorted(names_at)
        ] != sorted(name_rank[n] for _o, n in names_at):
            yield candidate(
                at,
                entries[0].mark,
                "the paragraph after the figure walks the marks out of order",
            )
