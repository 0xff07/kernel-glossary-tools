"""sources.one-version: the cited URLs carry one version."""

from tools.qa.inputs import violation


def check(page, context):
    versions = page.versions()
    if len(versions) > 1:
        yield violation(
            None,
            ", ".join(sorted(versions)),
            "the cited URLs pin more than one version: "
            + ", ".join(f"{v} ({n})" for v, n in versions.most_common()),
        )
