"""drawing.model: a figure fence starts in the lead or in SUMMARY."""

from tools.qa.inputs import violation


def check(page, context):
    summary = page.section("SUMMARY")
    for fence in page.figures:
        if page.lead.start <= fence.start <= page.lead.end or (
            summary and summary.start <= fence.start <= summary.end
        ):
            return
    yield violation(
        None,
        None,
        "no figure in the lead or in SUMMARY; the page carries its model"
        " figure there",
    )
