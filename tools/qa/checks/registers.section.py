"""registers.section: no table in section six; a link to a register header
there while the section draws nothing is a candidate."""

from tools.qa.inputs import candidate, violation


def check(page, context):
    section = page.reference_section
    if section is None:
        return
    figures = sum(
        1 for f in page.figures if section.start <= f.start <= section.end
    )
    for item in page.items_of(section.start + 1, section.end):
        if item.kind == "T":
            yield violation(
                item.line,
                item.text,
                f"a table under {section.name}; section six carries no table,"
                " and the registers it names are drawn",
            )
    for link in page.links:
        if (
            section.start <= link.line <= section.end
            and link.cited
            and not figures
        ):
            if any(
                link.cited[0].endswith(s)
                for s in page.profile.register_headers
            ):
                yield candidate(
                    link.line,
                    link.text,
                    f"{section.name} links a register definition and draws"
                    " none",
                )
                break
