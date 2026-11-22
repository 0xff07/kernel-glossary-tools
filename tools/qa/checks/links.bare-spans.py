"""links.bare-spans: every bare occurrence of a span is licensed: by a linked
occurrence earlier in the same paragraph, or by a settled class the rule names
and this checker recognizes (by the text alone, or with the tree's facts for an
identifier no cited source file defines or declares); a bare span with none is
a violation, a member a cited file declares among them, unless a shown function
also uses the name as a local or a parameter, which is a candidate.
"""

import re

from tools.qa.inputs import candidate, violation
from tools.qa.source import named_scope

SETTLED = [
    (r"^-E[A-Z0-9_]+$", "error value"),
    (r"^(0x[0-9a-fA-F]+|\d+|true|false|NULL)$", "literal value"),
    (r"^[0-9a-f]{12,40}$", "commit hash"),
    (
        r"^(if|else|return|goto|switch|case|default|break|continue|for|while|"
        r"do|sizeof|static|const|struct|enum|union|typedef|unsigned|int|void|"
        r"char|long)\b.*$",
        "C keyword excerpt",
    ),
    (r"^(/|\.\.?/|[\w.-]+/)[\w./-]*$", "path string"),
    (r"^\"[^\"]*\"$|^'[^']*'$", "string or character literal"),
    (
        r"^\S+\s*(==|!=|<=|>=|<|>|=|%|\|\||&&|<<|>>|\+|-|\*|/|\||&)\s*\S+",
        "expression",
    ),
    (r"^[\w.]+=\S*$", "boot parameter or Kconfig fragment"),
    (r"^\w+\(\d\)$", "manual-page notation"),
    (r"^\w+\*$", "wildcard family"),
    (r"^\w+:\w+$", "tracepoint name"),
    (r"^\.\w+$", "designated initializer member"),
    (
        r"^(?!(?:struct|enum|union)\s)\S+\s.*$",
        "text with spaces: a printed string or a fragment",
    ),
]
# a name with an underscore in it, the mark of an identifier; e.g. `pci_dev`,
# `_OSC`, `__init`
UNDERSCORED = re.compile(r"[A-Za-z_]\w*_\w*|_\w+")
SYMBOL_KINDS = (
    "function",
    "struct",
    "union",
    "enum",
    "typedef",
    "variable",
    "macro",
    "prototype",
    "enumerator",
)


def settled_by_text(text):
    for pattern, reason in SETTLED:
        # the span belongs to a settled class of SETTLED when the class's
        # pattern matches it from its start; e.g. `-EINVAL` is an error value,
        # `0x8086` a literal, `drivers/pci/` a path and `pci=noaer` a boot
        # parameter
        if re.match(pattern, text):
            return reason
    if not UNDERSCORED.search(text):
        return (
            "no identifier with an underscore: a local, a fragment, a mark or"
            " a literal"
        )
    return None


def check(page, context):
    entries = page.catalog_entry_texts()
    seen, deferred = set(), []
    for text, n, _region, linked in page.span_occurrences:
        if linked or text in entries or (text, n) in seen:
            continue
        line = page.lines[n - 1]
        linked_at = line.find("[`" + text + "`](")
        # a bare occurrence of the span on the line, backticked and no link
        # text; e.g. "`pci_dev`" in "the `pci_dev` object", and not the one of
        # "[`pci_dev`](url)"
        bare = re.search(r"(?<!\[)`" + re.escape(text) + r"`(?!\]\()", line)
        if linked_at != -1 and bare is not None and linked_at < bare.start():
            continue
        if settled_by_text(text):
            continue
        seen.add((text, n))
        # the span as one identifier, an array suffix and a trailing `()` cut
        # off first; e.g. `pci_walk_bus()` and `regs[4]` give pci_walk_bus and
        # regs
        if re.fullmatch(
            r"[A-Za-z_]\w*",
            name := re.sub(r"\(\)$", "", re.sub(r"\[[^\]]*\]$", "", text)),
        ):
            # the rule reads `name()` and `name` alike: a helper no cited file
            # defines stays bare in either spelling
            deferred.append((name, n, text))
        else:
            yield violation(
                n,
                text,
                f"bare span `{text}` is linked by no earlier occurrence in its"
                " paragraph and belongs to no settled class",
            )
    if not deferred:
        return
    tree = context.require("facts")
    sources = [
        f
        for f in page.cited_files()
        if page.profile.is_source(f) and tree.exists(f) and not tree.is_dir(f)
    ]
    shown = getattr(context, "reproduced", None) or {}
    for name, n, text in deferred:
        tags = [t for path in sources for t in tree.tags_named(path, name)]
        kinds = {t["kind"] for t in tags}
        if kinds & set(SYMBOL_KINDS):
            yield violation(
                n,
                text,
                f"bare span `{text}` names a"
                f" {', '.join(sorted(kinds & set(SYMBOL_KINDS)))} a cited file"
                " defines; link it at its first occurrence in the paragraph",
            )
        elif "member" in kinds:
            owners = sorted(
                {
                    named_scope(t.get("scope"))
                    for t in tags
                    if t["kind"] == "member"
                }
                - {None}
            )
            # the name used as a plain identifier in a shown unit, not behind
            # `->` or `.`: a local or a parameter the sentence may mean
            # the name used as a plain identifier in a shown line, not behind
            # `->` or `.`; e.g. dev in `if (!dev)`, and not in `pdev->dev`
            local = any(
                re.search(
                    r"(?<![\w>.])" + re.escape(name) + r"(?!\w)",
                    tree.line(path, line) or "",
                )
                for path, lines in shown.items()
                for line in lines
            )
            if local:
                yield candidate(
                    n,
                    text,
                    f"bare span `{text}` names a member of"
                    f" {', '.join(owners) or 'a cited type'} and a shown"
                    " function uses the name as a local or a parameter; link"
                    " the member where the sentence means it, or say which"
                    " function's local it is",
                )
            else:
                yield violation(
                    n,
                    text,
                    f"bare span `{text}` names a member of"
                    f" {', '.join(owners) or 'a cited type'}; link it to its"
                    " declaration line at its first occurrence in the"
                    " paragraph",
                )
