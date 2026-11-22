"""excerpts.enclosing: a unit that touches a construct without its opening line
fails when the construct is no function and no definition the prose above the
fence links, and for a function when the introduction above the fence links
none of it; a later piece of a definition read in pieces passes here and is
held to the whole definition by the walkthrough check. An unnamed struct or
union counts as part of the named definition around it (excerpts.walkthrough),
so a piece inside one is judged by that definition's opening line and the link
to it.
"""

import re

from tools.qa.inputs import violation
from tools.qa.source import DEFINITION_KINDS, named_holder, touched


def check(page, context):
    tree = context.require("tree")
    context.require("facts")
    for fence in page.source_fences:
        for unit in fence.units:
            if unit.mapped is None:
                continue
            lines = unit.file_lines
            intro = set(page.intro_lines(fence.start))
            intro_names = [
                name
                for k in intro
                for name in page.linked_names_in(page.lines[k - 1])
            ]
            intro_links = [link for link in page.links if link.line in intro]

            def introduced(construct):
                if construct["name"] in intro_names:
                    return True
                for link in intro_links:
                    cited = link.cited or ()
                    if (
                        len(cited) > 2
                        and cited[0] == unit.path
                        and cited[2] is not None
                        and construct["head"] <= cited[2] <= construct["line"]
                    ):
                        return True
                    # the construct's name inside the parentheses of a link
                    # text, an argument of a macro invocation; e.g.
                    # exc_page_fault in
                    # `DEFINE_IDTENTRY_RAW_ERRORCODE(exc_page_fault)`
                    if re.search(
                        r"\(\s*" + re.escape(construct["name"]) + r"\s*[,)]",
                        link.text or "",
                    ):
                        return True
                return False

            for construct in touched(tree, unit).values():
                if construct["line"] in lines:
                    continue
                if construct["kind"] == "function":
                    if not introduced(construct):
                        yield violation(
                            unit.start,
                            unit.label,
                            f"{unit.label} shows lines of"
                            f" {construct['name']}() without its signature,"
                            " and the introduction above the fence does not"
                            f" link {construct['name']}",
                        )
                    continue
                holder = construct
                if construct["name"].startswith(
                    "__anon"
                    # the definition an unnamed struct or union counts as part
                    # of
                ):
                    holder = (
                        named_holder(tree, unit.path, construct) or construct
                    )
                if (
                    holder["kind"] in DEFINITION_KINDS
                    and not holder["name"].startswith("__anon")
                    and (holder["line"] in lines or introduced(holder))
                ):
                    # a later piece of a definition read in pieces; the
                    # walkthrough holds it to the whole
                    continue
                inside = (
                    f" (inside its unnamed {construct['kind']} opened at"
                    f" {construct['line']})"
                    if holder is not construct
                    else ""
                )
                yield violation(
                    unit.start,
                    unit.label,
                    f"{unit.label} shows members of {holder['kind']}"
                    f" {holder['name']}{inside} without its opening line"
                    f" {holder['line']}",
                )
