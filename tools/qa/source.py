"""The tree-side helpers the excerpt and link checkers share: the anchors
procedure, the catalog forms, the constructs a unit touches, the functions a
page owns and the pieces that walk them.
"""

import fnmatch
import re

from .inputs import candidate, violation
from .page import MEMBER_KEY


def within(path, kernel_paths):
    """Whether a file lies in the subsystem whose kernel_paths these are
    (page-model.md, subsystem paths)."""
    parts = path.split("/")
    for spec in kernel_paths or ():
        spec = spec.strip().rstrip("/")
        if not spec:
            continue
        if any(c in spec for c in "*?["):
            pattern = spec.split("/")
            if len(parts) >= len(pattern) and all(
                fnmatch.fnmatchcase(p, q) for p, q in zip(parts, pattern)
            ):
                return True
        elif path == spec or path.startswith(spec + "/"):
            return True
    return False


def named_scope(scope):
    """The named struct or union a member belongs to; an unnamed `__anon` scope
    resolves to the one around it."""
    names = (scope or "").split("::")
    while names and names[-1].startswith("__anon"):
        names.pop()
    return names[-1] if names else None


def member_at(tree, path, line, text, struct, name):
    tags = tree.tag_at(path, line, name)
    if tags:
        return any(
            t["kind"] == "member" and named_scope(t.get("scope")) == struct
            for t in tags
        )
    holders = [
        t
        for t in tree.constructs(path)
        if t["kind"] in ("struct", "union")
        and not t["name"].startswith("__anon")
        and t["line"] <= line <= t["end"]
    ]
    holder = max(holders, key=lambda t: t["line"], default=None)
    # the member's name as a whole word of the line; e.g. error_detected in
    # `pci_ers_result_t (*error_detected)(struct pci_dev *dev,`, and not in
    # `error_detected_cb`
    return (
        holder is not None
        and holder["name"] == struct
        and re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text)
        is not None
    )


def named_holder(tree, path, construct):
    """The named struct or union around an unnamed `__anon` construct, the
    definition it counts as part of (excerpts.walkthrough): the innermost named
    struct or union whose lines hold its opening line, or None.
    """
    holders = [
        t
        for t in tree.constructs(path)
        if t["kind"] in ("struct", "union")
        and not t["name"].startswith("__anon")
        and t["line"] <= construct["line"] <= t["end"]
    ]
    return max(holders, key=lambda t: t["line"], default=None)


# a comment, or the part of one a line holds: a whole `/* */`, a `//` to the
# end of the line, an opening `/*` to the end, the close of a comment begun
# above, or a continuation line that opens with `*`; e.g. the `/* the lock */`
# of `int x; /* the lock */`, the `// note` of `x = 1; // note`, and the whole
# line ` * held by the caller`. The close of a comment begun above runs from
# the start of the line to the first `*/` with no `/*` before it, e.g. the
# `by the caller */` of `by the caller */ int y;`: a `*/` that follows a `/*`
# on the line closes that comment, and the code before it stays code
COMMENT = re.compile(r"/\*.*?\*/|//.*$|/\*.*$|^(?:(?!/\*).)*?\*/|^\s*\*.*$")


def code_text(text):
    """A source line with its comments blanked."""
    return COMMENT.sub(lambda m: " " * len(m.group(0)), text)


def target_finding(link, tree):
    """(settled, finding) for what a link's URL names, before any symbol is
    looked for: a file the tree lacks, a directory, a line that is missing or
    beyond the file. A file link and a plain link are settled once their
    target is there."""
    path, _version, line = link.cited
    quote = link.text
    if not tree.exists(path):
        return True, violation(link.line, quote, f"{path} is not in the tree")
    if link.cls in ("file", "plain") and line is None:
        return True, None
    if tree.is_dir(path):
        return True, violation(
            link.line,
            quote,
            f"{path} is a directory, and the URL anchors a line in it",
        )
    if line is None:
        if link.cls in ("symbol", "field", "config", "catalog"):
            return True, violation(
                link.line,
                quote,
                f"a {link.cls} link with no line in its URL",
            )
        return True, None
    if tree.line(path, line) is None:
        return True, violation(
            link.line, quote, f"{path}:{line} is beyond the file"
        )
    return link.cls in ("file", "plain"), None


def location_finding(link, tree):
    path, _version, line = link.cited
    _file, first, last = link.location
    if first != line:
        return violation(
            link.line,
            link.text,
            f"the text names line {first} but the URL anchors line {line}",
        )
    if tree.line(path, last) is None:
        return violation(
            link.line,
            link.text,
            f"the range ends at {last}, beyond the file",
        )
    return None


def config_finding(link, text):
    path, _version, line = link.cited
    # the Kconfig line that defines the option, `config NAME` or `menuconfig
    # NAME`; e.g. `config PCIEAER` for the option PCIEAER
    if re.match(r"^(menu)?config\s+" + re.escape(link.name) + r"\s*$", text):
        return None
    return violation(
        link.line,
        link.text,
        f"{path}:{line} is not `config {link.name}`: {text.strip()[:60]!r}",
    )


def declares_bare_type(link, text):
    """An incomplete type the tree declares and never defines (struct
    encoded_page;) links its declaration line, the only line carrying its
    name: a bare tagged declaration at the linked line is accepted."""
    # the quoting of a catalog key, taken off: backticks, quotes, backslashes
    # and angle brackets; e.g. `'\<struct encoded_page\>':'mm.h'` leaves
    # `struct encoded_page` before its colon
    bare = re.sub(r"[`'\\<>]", "", link.name or "").split(":")[0].strip()
    bare = bare.split()[-1] if bare else ""
    # a bare declaration of the tagged type; e.g. `struct encoded_page;` for
    # encoded_page
    return bool(
        bare
        and re.match(
            r"\s*(?:struct|union|enum)\s+" + re.escape(bare) + r"\s*;",
            code_text(text),
        )
    )


def member_finding(link, tree, text, struct, name):
    """The finding of a catalog entry keyed `A.B` whose line does not declare
    member B of A, with where B is declared or what the line declares it
    in."""
    path, _version, line = link.cited
    if member_at(tree, path, line, text, struct, name):
        return None
    found = [
        t
        for t in tree.tags_named(path, name)
        if t["kind"] == "member" and named_scope(t.get("scope")) == struct
    ]
    owners = sorted(
        {
            named_scope(t.get("scope"))
            for t in tree.tag_at(path, line, name)
            if t["kind"] == "member"
        }
        - {None}
    )
    hint = (
        f"; it is declared at line {found[0]['line']}"
        if found
        else (
            f"; the line declares it in {', '.join(owners)}" if owners else ""
        )
    )
    return violation(
        link.line,
        link.text,
        f"{path}:{line} declares no member {name} of {struct}:"
        f" {text.strip()[:60]!r}{hint}",
    )


def body_line_finding(link, context, tree):
    """(settled, finding) for a function span that lands inside the
    function's body: accepted on a line the sentence explains when an excerpt
    on the page reproduces that line, a candidate otherwise."""
    path, _version, line = link.cited
    holder = tree.construct_at(path, line)
    if not (
        holder is not None
        and holder["kind"] == "function"
        and holder["name"] == link.name
        and holder["line"] < line <= holder["end"]
    ):
        return False, None
    shown = getattr(context, "reproduced", None) or {}
    if line in shown.get(path, set()):
        return True, None
    return True, candidate(
        link.line,
        link.text,
        f"{path}:{line} lies inside {link.name}() at a line no"
        " excerpt reproduces; link the definition line"
        f" {holder['line']}, or show the lines the sentence"
        " explains",
    )


def tag_finding(link, tree, kernel_paths):
    """(settled, finding) by the facts at the linked line that carry the
    link's name: a member where a symbol is cataloged, a prototype, or a
    definition, which settles the link with no finding."""
    path, _version, line = link.cited
    tags = tree.tag_at(path, line, link.name)
    if link.tag:
        tags = [t for t in tags if t["kind"] == link.tag]
    if not tags:
        return False, None
    if link.cls == "catalog" and all(t["kind"] == "member" for t in tags):
        owner = named_scope(tags[0].get("scope"))
        return True, violation(
            link.line,
            link.text,
            f"{path}:{line} declares a member; a member entry is keyed"
            f" `A.B`, `'{owner}.{link.name}'`",
        )
    if not all(t["kind"] == "prototype" for t in tags):
        return True, None
    if within(path, kernel_paths):
        return True, candidate(
            link.line,
            link.text,
            f"{path}:{line} is a prototype of {link.name}, not its"
            " definition; cleared when the prose says a macro"
            " generates the symbol, else link the definition",
        )
    return True, candidate(
        link.line,
        link.text,
        f"{path}:{line} is the declaration of {link.name}, a"
        " primitive another subsystem defines; link its"
        " definition or keep the declaration knowingly",
    )


def defined_by_text(link, tree, text):
    """Whether a line no fact names for the link still defines its symbol, by
    one of four readings of its text."""
    path, _version, line = link.cited
    holder = tree.construct_at(path, line)
    # the first line of a split signature: the return type and the storage
    # class above the name line
    if (
        holder is not None
        and holder["kind"] == "function"
        and holder["name"] == link.name
        and holder["head"] <= line < holder["line"]
        and ";" not in text
    ):
        return True
    code = code_text(text)
    # the linked name as a whole word of the line's code; e.g. pci_walk_bus in
    # `void pci_walk_bus(struct pci_bus *top,`, and not in
    # `__pci_walk_bus(top)`
    spelled = (
        re.search(r"(?<!\w)" + re.escape(link.name) + r"(?!\w)", code)
        is not None
    )
    # a function a macro invocation defines
    # (DEFINE_IDTENTRY_ERRORCODE(exc_general_protection)): the construct at
    # the line is a function the invocation defines, and the line spells the
    # linked symbol inside the parentheses (the function's name) or before
    # them (the macro's)
    # the name inside the parentheses of an invocation, the function a macro
    # defines, or right before them, the macro itself; e.g.
    # exc_general_protection, and DEFINE_IDTENTRY_ERRORCODE, in
    # `DEFINE_IDTENTRY_ERRORCODE(exc_general_protection)`
    if (
        link.tag is None
        and holder is not None
        and holder.get("kind") == "function"
        and holder.get("line") == line
        and (
            re.search(
                r"\(.*(?<!\w)" + re.escape(link.name) + r"(?!\w).*\)", code
            )
            or re.match(r"\s*" + re.escape(link.name) + r"\s*\(", code)
        )
    ):
        return True
    # a symbol a macro declares at file scope (DEVICE_ATTR_RO(boot),
    # DEFINE_MUTEX(lock)): no tag carries its name, so the line, its comments
    # aside, spells the name inside an invocation and lies in no function
    # an invocation on the line, a name and `(`; e.g. `DEVICE_ATTR_RO(boot);`
    # and `static DEFINE_MUTEX(lock);`
    if (
        link.tag is None
        and spelled
        and re.search(r"[A-Za-z_]\w*\s*\(", code)
        and (holder is None or holder["kind"] != "function")
    ):
        return True
    # a typedef line the parser lost: tree-sitter's error recovery can swallow
    # a typedef that follows a construct it cannot parse (mm/slab.h's kmalloc
    # prototypes before freelist_full_t), so a line that spells
    # `typedef ... NAME;` and carries no tag is read textually as the
    # typedef's definition line
    # a typedef line that ends with the name, array brackets allowed after it;
    # e.g. `typedef unsigned int freelist_full_t;` for freelist_full_t
    return bool(
        link.tag in (None, "typedef")
        and re.match(
            r"\s*typedef\b.*(?<!\w)"
            + re.escape(link.name)
            + r"\s*(?:\[[^\]]*\])?\s*;",
            code,
        )
    )


def anchor_finding(link, context, tree, kernel_paths):
    """The one finding of a cited link, or None when its URL anchors what its
    text names."""
    settled, finding = target_finding(link, tree)
    if settled:
        return finding
    path, _version, line = link.cited
    text = tree.line(path, line)
    if link.cls == "location":
        return location_finding(link, tree)
    if link.cls == "config":
        return config_finding(link, text)
    if declares_bare_type(link, text):
        return None
    context.require("facts")
    member = MEMBER_KEY.match(link.name) if link.cls == "catalog" else None
    if member:
        return member_finding(link, tree, text, *member.groups())
    if link.cls == "symbol" and link.tag is None:
        settled, finding = body_line_finding(link, context, tree)
        if settled:
            return finding
    settled, finding = tag_finding(link, tree, kernel_paths)
    if settled:
        return finding
    if defined_by_text(link, tree, text):
        return None
    named = [
        t for t in tree.tags_named(path, link.name) if t["kind"] != "prototype"
    ]
    hint = (
        f"; {link.name} is defined at line {named[0]['line']}" if named else ""
    )
    return violation(
        link.line,
        link.text,
        f"{path}:{line} is not the definition line of {link.name}:"
        f" {text.strip()[:60]!r}{hint}",
    )


def anchors(page, context, tree, checked):
    """The anchors procedure of links.definition-line over every cited link."""
    kernel_paths = (
        (context.subsystem or {}).get("kernel_paths", [])
        if hasattr(context, "subsystem")
        else []
    )
    for link in page.cited_links():
        checked[link.cls] += 1
        finding = anchor_finding(link, context, tree, kernel_paths)
        if finding is not None:
            yield finding


# a target `git log -L` can trace, an identifier with or without its tag
# keyword; e.g. `pci_walk_bus` and `struct pci_dev`
TRACEABLE = re.compile(r"(?:(?:struct|enum|union) )?[A-Za-z_]\w*")


def trace_of(lines, target):
    """Where `git log -L:'\\<T\\>':'<file>'` starts: the first line beginning
    with a letter or `_` that holds T as a whole word."""
    if not TRACEABLE.fullmatch(target):
        return None
    # the target as a whole word; e.g. pci_dev in `struct pci_dev {`, and not
    # in `struct pci_dev_resource {`
    word = re.compile(r"(?<!\w)" + re.escape(target) + r"(?!\w)")
    return next(
        (
            n
            for n, text in enumerate(lines, 1)
            if text[:1].isascii()
            and (text[:1].isalpha() or text[:1] == "_")
            and word.search(text)
        ),
        None,
    )


def catalog_forms(page, context, tree):
    """An entry in the traced form traces with KEY = T, one in the bare form
    does not."""
    for entry in page.catalog:
        path, line, key = (
            entry["cited_path"],
            entry["cited_line"],
            entry["key"],
        )
        if (
            not path
            or not line
            or MEMBER_KEY.match(key)
            or not tree.exists(path)
            or tree.is_dir(path)
        ):
            continue
        target = (
            f"{entry['tag']} {entry['name']}"
            if entry["tag"]
            else entry["name"]
        )
        lines = tree.lines(path) or []
        start = trace_of(lines, target)
        traces = start == line
        if start is not None and start > line and line <= len(lines):
            # the entry cites the first line of a split signature, above the
            # name line the trace starts at
            context.require("facts")
            holder = tree.construct_at(path, line)
            traces = (
                holder is not None
                and holder["kind"] == "function"
                and holder["name"] == target.split()[-1]
                and holder["head"] <= line < holder["line"] == start
            )
        where = (
            f"starts at line {start}, {lines[start - 1].strip()[:50]!r}, not"
            " at the definition"
            if start
            else "finds no line"
        )
        command = f"git log -L:'\\<{target}\\>':'{path}'"
        if entry["form"] == "traced":
            if entry["path"] != path:
                yield violation(
                    entry["line"],
                    entry["text"],
                    f"PATH {entry['path']} is not the URL's file {path}",
                )
            elif not traces:
                yield violation(
                    entry["line"],
                    entry["text"],
                    f"{command} {where}; write the bare form `'{key}'`",
                )
            elif key != target:
                yield violation(
                    entry["line"],
                    entry["text"],
                    f"the traced key is `{target}`,"
                    f" `'\\<{target}\\>':'{path}'`",
                )
        elif traces:
            yield violation(
                entry["line"],
                entry["text"],
                f"{command} starts at line {line}, the definition; write the"
                f" traced form `'\\<{target}\\>':'{path}'`",
            )


DEFINITION_KINDS = ("struct", "union", "enum", "variable")


def walked_definitions(page, tree):
    """The struct, union, enum or file-scope variable definitions the page
    reads in pieces: a definition some unit touches without reproducing its
    opening line is read in pieces, and the walkthrough then holds its pieces
    to the whole definition. An unnamed union or struct inside a definition
    belongs to the definition around it.
    """
    out, seen = [], set()
    for unit in page.units:
        if unit.mapped is None:
            continue
        lines = unit.file_lines
        for construct in touched(tree, unit).values():
            if construct["name"].startswith(
                "__anon"
                # an unnamed union or struct belongs to the definition around
                # it
            ):
                construct = named_holder(tree, unit.path, construct)
                if construct is None:
                    continue
            if construct["kind"] not in DEFINITION_KINDS:
                continue
            if (
                construct["line"] in lines
                or (unit.path, construct["line"]) in seen
            ):
                continue
            seen.add((unit.path, construct["line"]))
            out.append(
                (
                    f"{construct['kind']} {construct['name']}",
                    unit.path,
                    construct["line"],
                    construct["end"],
                )
            )
    return out


def touched(tree, unit):
    found = {}
    for _p, f in unit.mapped or []:
        construct = tree.construct_at(unit.path, f)
        if construct:
            found[(construct["line"], construct["name"])] = construct
    return found


def owned_functions(page, tree):
    """(name, path, start, end) of every function a catalog entry cites, by its
    name line and its closing brace: an entry may cite the first line of a
    split signature (construct_at reaches the function from its head), and the
    walkthrough and the outline count the function's lines from the name line
    as they always have.
    """
    out, seen = [], set()
    for entry in page.catalog:
        path, line = entry["cited_path"], entry["cited_line"]
        if not path or not line or not page.profile.is_source(path):
            continue
        construct = tree.construct_at(path, line)
        if (
            construct is None
            or construct["kind"] != "function"
            or (path, construct["line"]) in seen
        ):
            continue
        seen.add((path, construct["line"]))
        out.append(
            (construct["name"], path, construct["line"], construct["end"])
        )
    return out


def pieces(page, path, start, end):
    """The units that walk the function, in page order: a unit that elides
    inside the function is a folded excerpt, and a unit all of whose function
    lines earlier units already showed is a re-show; neither is a piece.
    """
    out, shown = [], set()
    for unit in page.units:
        if unit.path != path or not unit.mapped:
            continue
        inside = [f for _p, f in unit.mapped if start <= f <= end]
        if not inside:
            continue
        if set(inside) <= shown:
            continue
        befores = [
            [f for p, f in unit.mapped if p < n] for n, _d, _r in unit.elisions
        ]
        if any(b and start <= b[-1] <= end for b in befores):
            continue
        out.append((unit, inside))
        shown.update(inside)
    return out


def resolve_cited(page, file):
    cited = page.cited_files()
    if file in cited:
        return file, None
    tails = [
        c
        for c in cited
        if c.rsplit("/", 1)[-1] == file or c.endswith("/" + file)
    ]
    if len(tails) == 1:
        return tails[0], None
    return None, (
        "names no file the page cites"
        if not tails
        else f"is ambiguous among {len(tails)} cited files"
    )
