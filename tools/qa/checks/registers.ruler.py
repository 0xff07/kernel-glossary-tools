"""registers.ruler: in a figure with a ruler line, every grid's cell boundaries
sit on the bit grid and every divider junction agrees with the rows beside
it."""

import re

from tools.qa.inputs import violation

# the ruler line of a register grid, single digits one space apart, with or
# without a leading `bit`; e.g. `bit  7 6 5 4 3 2 1 0`
RULER = re.compile(r"^\s*(?:bit\s+)?(?:[0-9] )+[0-9]\s*$")
# the top border of a register grid, group 1 what stands before it and group 2
# the border; e.g. `   ┌─┬─┬─┬─┐`
GRID_TOP = re.compile(r"^(\s*[^\s│├└┌]*?\s*)(┌[─┬]+┐)")


def grids(body):
    if not any(RULER.match(row) for row in body):
        return
    i = 0
    while i < len(body):
        match = GRID_TOP.match(body[i])
        if match:
            x0 = len(match.group(1))
            rows = [(i, body[i])]
            j = i + 1
            while j < len(body) and (
                "│" in body[j] or body[j].lstrip().startswith(("├", "└"))
            ):
                rows.append((j, body[j]))
                if body[j].lstrip().startswith("└"):
                    break
                j += 1
            yield x0, rows
            i = j + 1
        else:
            i += 1


def check(page, context):
    for fence in page.figures:
        for x0, rows in grids(fence.body):
            top = rows[0][1]
            width = len(top.rstrip()) - 1 - x0

            def boundaries(line):
                return {
                    c
                    for c, ch in enumerate(line)
                    if ch == "│" and x0 <= c <= x0 + width
                }

            cells_ = [
                (o, l)
                for o, l in rows
                if "│" in l and not l.lstrip().startswith(("├", "└", "┌"))
            ]
            for offset, line in cells_:
                off = sorted(c - x0 for c in boundaries(line) if (c - x0) % 2)
                if off:
                    yield violation(
                        fence.start + 1 + offset,
                        line.strip(),
                        "a cell boundary off the bit grid at column offset"
                        f" {off[0]} of the ruler",
                    )
            for k, (offset, line) in enumerate(rows):
                if not line.lstrip().startswith("├"):
                    continue
                above = next(
                    (
                        (o, l)
                        for o, l in reversed(rows[:k])
                        if "│" in l and not l.lstrip().startswith(("├", "┌"))
                    ),
                    None,
                )
                below = next(
                    (
                        (o, l)
                        for o, l in rows[k + 1 :]
                        if "│" in l and not l.lstrip().startswith(("├", "└"))
                    ),
                    None,
                )
                if above is None or below is None:
                    continue
                a, b = boundaries(above[1]), boundaries(below[1])
                for c in range(x0 + 1, x0 + width):
                    ch = line[c] if c < len(line) else " "
                    want = (
                        "┼"
                        if c in a and c in b
                        else "┴" if c in a else "┬" if c in b else "─"
                    )
                    if ch != want:
                        yield violation(
                            fence.start + 1 + offset,
                            line.strip(),
                            f"the divider has {ch!r} at column offset {c - x0}"
                            f" where the rows beside it call for {want!r}",
                        )
                        break
