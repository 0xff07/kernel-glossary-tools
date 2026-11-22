"""sections.order: the H2 names are the profile's sections in order, with at
most one reference section and the claims section last when the page has
one."""

from tools.qa.inputs import violation


def check(page, context):
    names = page.h2_names
    reference = [n for n in names if n in page.profile.reference_sections]
    claims = [n for n in names if n in page.profile.claims_sections]
    order = list(page.profile.sections)
    wanted = (
        order[:-1]
        + (reference[:1] if reference else [])
        + order[-1:]
        + (claims[:1] if claims else [])
    )
    if names != wanted:
        yield violation(
            None,
            ", ".join(names),
            "H2 order is ["
            + ", ".join(names)
            + "]; expected ["
            + ", ".join(wanted)
            + "]",
        )
