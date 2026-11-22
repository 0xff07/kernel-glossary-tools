"""geometry.figure-tabs: no tab inside a figure fence."""

from tools.qa.inputs import violation


def check(page, context):
    for figure in page.figures:
        for k, line in enumerate(figure.body):
            if "\t" in line:
                yield violation(
                    figure.start + 1 + k,
                    line.strip(),
                    "Figure contains a tab.",
                )
