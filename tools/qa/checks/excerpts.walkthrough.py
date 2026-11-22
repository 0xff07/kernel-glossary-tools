"""excerpts.walkthrough: every line of a function the page owns is reproduced
by a piece, and the pieces follow the function; a definition the page reads in
pieces is reproduced whole by its pieces, in one subsection, and never shown
again."""

import collections

from tools.qa.inputs import candidate, measurement, violation
from tools.qa.source import owned_functions, pieces, walked_definitions


def check(page, context):
    tree = context.require("tree")
    context.require("facts")
    owned = owned_functions(page, tree)
    yield measurement(
        None,
        None,
        f"owned functions: {len(owned)}: " + ", ".join(o[0] for o in owned),
    )
    for name, path, start, end in owned:
        walked = pieces(page, path, start, end)
        shown = collections.Counter(f for _u, inside in walked for f in inside)
        missing = [f for f in range(start, end + 1) if f not in shown]
        if missing:
            yield violation(
                None,
                name,
                f"{name}() ({path}:{start}-{end}) is never shown whole:"
                f" {len(missing)} line(s) reproduced by no excerpt, the first"
                f" {path}:{missing[0]}",
            )
        for (a, a_inside), (b, b_inside) in zip(walked, walked[1:]):
            if b_inside[0] < a_inside[0]:
                yield candidate(
                    b.start,
                    name,
                    f"{name}(): the piece at {b.label} shows lines before the"
                    f" piece at {a.label}; pieces follow the function",
                )
        twice = sum(1 for f, c in shown.items() if c > 1)
        if twice:
            yield measurement(
                None,
                name,
                f"{name}(): {twice} line(s) reproduced more than once",
            )
    definitions = walked_definitions(page, tree)
    if definitions:
        yield measurement(
            None,
            None,
            f"definitions read in pieces: {len(definitions)}: "
            + ", ".join(d[0] for d in definitions),
        )
    for name, path, start, end in definitions:
        walked = pieces(page, path, start, end)
        shown = collections.Counter(f for _u, inside in walked for f in inside)
        missing = [f for f in range(start, end + 1) if f not in shown]
        if missing:
            yield violation(
                None,
                name,
                f"{name} ({path}:{start}-{end}) is read in pieces that do not"
                f" reproduce it whole: {len(missing)} line(s) reproduced by no"
                f" piece, the first {path}:{missing[0]}; a definition is never"
                " thinned",
            )
        for (a, a_inside), (b, b_inside) in zip(walked, walked[1:]):
            if b_inside[0] < a_inside[0]:
                yield candidate(
                    b.start,
                    name,
                    f"{name}: the piece at {b.label} shows lines before the"
                    f" piece at {a.label}; pieces follow the definition",
                )
        piece_units = {id(u) for u, _inside in walked}
        for unit in page.units:
            if unit.path != path or not unit.mapped or id(unit) in piece_units:
                continue
            if any(start <= f <= end for _p, f in unit.mapped):
                yield violation(
                    unit.start,
                    name,
                    f"{name}: the unit at {unit.label} shows lines of the"
                    " definition again; a definition is read once in pieces,"
                    " and a later paragraph links the members it reasons"
                    " about",
                )
        homes = []
        for unit, _inside in walked:
            sub = page.subsection_of(unit.fence.start)
            homes.append(sub["line"] if sub else None)
        if len(set(homes)) > 1:
            stray = next(
                u for (u, _i), h in zip(walked, homes) if h != homes[0]
            )
            yield violation(
                stray.start,
                name,
                f"{name}: the piece at {stray.label} stands in another"
                " subsection than the first piece; the pieces of a definition"
                " stay in the subsection that reads it",
            )
