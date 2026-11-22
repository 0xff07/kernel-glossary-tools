"""style.walk: the pattern rows of its rule file, swept over the prose view."""

from tools.qa.style import sweep


def check(page, context):
    return sweep(page, context, "style.walk")
