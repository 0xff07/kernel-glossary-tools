"""excerpts.verbatim: every unit maps onto its file byte for byte, every
elision dropping what the file shows dropped."""

from tools.qa.inputs import measurement, violation


def check(page, context):
    context.require("tree")
    bad = 0
    for unit in page.units:
        if unit.error:
            bad += 1
            yield violation(
                unit.start, unit.label, f"{unit.label}: {unit.error}"
            )
    elisions = sum(len(u.elisions) for u in page.units)
    yield measurement(
        None,
        None,
        f"units: {len(page.units)} in {len(page.source_fences)} fences,"
        f" {len(page.units) - bad} verbatim, {elisions} elisions",
    )
