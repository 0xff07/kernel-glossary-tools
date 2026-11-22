#!/usr/bin/env python3
"""The tree's tags file read through readtags, every entry settled to a line of
its file.

`make tags` writes Universal Ctags entries that carry a search pattern
(`/^text$/`, cut at the pattern length limit, 96 bytes by default) and no
`line:` field, so `readtags -n` prints no line number for them, and a reader
that waits for one finds nothing. `entries` resolves each pattern on disk: the
line of the file that spells the pattern's text (whole, or as a prefix when the
pattern was cut), the k-th entry of one pattern to the k-th such line (the
twins two `#if` branches of one file define), a member or an enumerator to the
line inside the body of the struct, union or enum its scope field names when
two holders in one file declare it with the same text (the tags file lists such
entries by holder name, not in the file's order), a function entry to a line a
body follows and a prototype entry to a line a `;` ends when a prototype
repeats the definition's first line, a numeric entry as it stands; and it moves
a function's line up to the first line of a split signature (`static int` on
the line above `name(...)`), the definition line links.definition-line asks
for, so that readers and the QA engine's construct lines agree. A name the tags
file lacks, or a pattern its file no longer spells, yields nothing for that
entry.
"""

from pathlib import Path
import re
import shutil
import subprocess

# one line of a tags file: the name, the path, then a line number or a
# `/^pattern$/;"` search pattern, then the extension fields; e.g. the name
# pci_walk_bus, a tab, drivers/pci/bus.c, a tab, `/^void pci_walk_bus(struct
# pci_bus *top,$/;"`, a tab and `f` give the name, the path, the pattern's body
# and the rest `f`
_ENTRY = re.compile(
    r"^(?P<name>[^\t]*)\t(?P<path>[^\t]*)\t(?:(?P<number>\d+)|"
    r'/\^(?P<body>(?:\\.|[^\\/])*?)(?P<full>\$)?/);"(?:\t(?P<rest>.*))?$'
)
# a line that holds specifier words alone, the return type of a function whose
# name stands on the next line; e.g. `static int` and `struct pci_dev *`
_SPECIFIER_LINE = re.compile(r"^[A-Za-z_][\w \t*]*$")
# the line that opens a struct, union or enum, group 1 its tag; e.g. `struct
# pci_dev {` and `typedef struct foo {`
_HOLDER_OPENS = re.compile(
    r"^\s*(?:typedef\s+)?(?:static\s+)?(?:const\s+)?(?:struct|union|enum)"
    r"\s+([A-Za-z_]\w*)\s*(\{|$)"
)
_SCOPE_KEYS = ("struct", "union", "enum")
_FILES = {}
_HOLDERS = {}


def have_readtags():
    return shutil.which("readtags") is not None


def file_lines(tree, path):
    """The lines of a tree file, cached per path; [] when it cannot be read."""
    key = (tree, path)
    if key not in _FILES:
        try:
            text = Path(tree, path).read_text(
                encoding="utf-8", errors="replace"
            )
            _FILES[key] = text.split("\n")
        except OSError:
            _FILES[key] = []
    return _FILES[key]


def unescape(body):
    """The text of a ctags pattern: ctags writes `\\` for a backslash and `\\/`
    for a slash."""
    # a backslash and the character it escapes, replaced by that character;
    # e.g. `a\/b` becomes `a/b`
    return re.sub(r"\\(.)", lambda m: m.group(1), body)


def head_of(lines, number):
    """The first line of the signature whose name line is `number`: the return
    type and the storage class may stand on the lines above (`static
    __must_check int` above `__split_vma(...)`), each a line of specifier words
    and `*` alone, with no `;`, brace, parenthesis, directive or comment, which
    is when links.definition-line counts it as the signature's first line."""
    while number > 1:
        text = lines[number - 2].strip()
        if not text or not _SPECIFIER_LINE.match(text) or text.endswith(","):
            break
        number -= 1
    return number


def opens_body(lines, number):
    """Whether the declaration that begins on line `number` opens a body: a `{`
    comes before any `;` in the lines that follow (comments skipped), so a
    function definition is told from the prototype that repeats its first line.
    """
    in_comment = False
    for text in lines[number - 1 : number + 59]:
        code = []
        i = 0
        while i < len(text):
            if in_comment:
                if text.startswith("*/", i):
                    in_comment = False
                    i += 2
                else:
                    i += 1
            elif text.startswith("/*", i):
                in_comment = True
                i += 2
            elif text.startswith("//", i):
                break
            else:
                code.append(text[i])
                i += 1
        for ch in code:
            if ch == "{":
                return True
            if ch == ";":
                return False
    return False


def body_end(lines, number):
    """The line that closes the body the declaration on line `number` opens,
    its braces counted outside comments and string and character literals; None
    when a `;` comes first or the file ends before the body closes.
    """
    depth, opened, in_comment = 0, False, False
    for n in range(number, len(lines) + 1):
        text = lines[n - 1]
        i, quote = 0, None
        while i < len(text):
            ch = text[i]
            if in_comment:
                if text.startswith("*/", i):
                    in_comment = False
                    i += 1
            elif quote:
                if ch == "\\":
                    i += 1
                elif ch == quote:
                    quote = None
            elif text.startswith("/*", i):
                in_comment = True
                i += 1
            elif text.startswith("//", i):
                break
            elif ch in "\"'":
                quote = ch
            elif ch == "{":
                depth += 1
                opened = True
            elif ch == "}":
                depth -= 1
                if opened and depth == 0:
                    return n
            elif ch == ";" and not opened:
                return None
            i += 1
    return None


def holders(tree, path):
    """[(first, last, name)] for every struct, union or enum a file defines
    with a tag: the line that opens `struct name {` (the brace on that line or
    opening the next one) to the line that closes its body. Cached per path."""
    key = (tree, path)
    if key not in _HOLDERS:
        lines = file_lines(tree, path)
        found = []
        for n, text in enumerate(lines, 1):
            match = _HOLDER_OPENS.match(text)
            if match is None:
                continue
            # the brace must open the next line that holds anything
            if match.group(2) != "{":
                following = next(
                    (t.strip() for t in lines[n : n + 3] if t.strip()), ""
                )
                if not following.startswith("{"):
                    continue
            last = body_end(lines, n)
            if last is not None:
                found.append((n, last, match.group(1)))
        _HOLDERS[key] = found
    return _HOLDERS[key]


def holder_at(spans, number):
    """The tag of the innermost definition among `spans` whose body holds the
    line, or None."""
    inside = [
        (last - first, name)
        for first, last, name in spans
        if first <= number <= last
    ]
    return min(inside)[1] if inside else None


def scope_holder(fields):
    """The struct, union or enum tag an entry's scope field names: the
    innermost one that has a tag, so a member of an anonymous union inside
    `struct page` (`union:page::__anon...`) is held by `page`; None for an
    entry without such a field or with an anonymous holder alone."""
    for key in _SCOPE_KEYS:
        if fields.get(key):
            named = [
                part
                for part in fields[key].split("::")
                if part and not part.startswith("__anon")
            ]
            return named[-1] if named else None
    return None


def parse(raw):
    """(name, path, number or None, body or None, full, fields) of one readtags
    -e line, or None."""
    match = _ENTRY.match(raw)
    if match is None:
        return None
    fields = {}
    for field in (match.group("rest") or "").split("\t"):
        key, _, value = field.partition(":")
        if key:
            fields[key] = value
    number = int(match.group("number")) if match.group("number") else None
    body = (
        unescape(match.group("body"))
        if match.group("body") is not None
        else None
    )
    return (
        match.group("name"),
        match.group("path"),
        number,
        body,
        bool(match.group("full")),
        fields,
    )


def entries(tree, tags, name, prefix=False):
    """[(path, line, kind, fields)] for the tags-file entries of name (every
    name beginning with it under prefix), each settled to a line of its file;
    the empty list when readtags fails or finds nothing.
    """
    command = (
        ["readtags", "-t", tags, "-e", "-n"]
        + (["-p"] if prefix else [])
        + [name]
    )
    done = subprocess.run(command, capture_output=True, text=True)
    if done.returncode != 0:
        return []
    out, taken = [], {}
    for raw in done.stdout.splitlines():
        parsed = parse(raw)
        if parsed is None:
            continue
        _name, path, number, body, full, fields = parsed
        kind = fields.get("kind", "")
        if number is None and fields.get("line", "").isdigit():
            number = int(fields["line"])
        if number is None:
            lines = file_lines(tree, path)
            hits = [
                n
                for n, text in enumerate(lines, 1)
                if (text == body if full else text.startswith(body))
            ]
            # a prototype that repeats the definition's first line
            if kind in ("f", "p") and len(hits) > 1:
                hits = [
                    n for n in hits if opens_body(lines, n) == (kind == "f")
                ] or hits
            slot = (path, body, kind)
            holder = scope_holder(fields) if len(hits) > 1 else None
            if (
                holder
                # two holders declare the name with one text: the line inside
                # this one
            ):
                spans = holders(tree, path)
                inside = [n for n in hits if holder_at(spans, n) == holder]
                if inside:
                    hits, slot = inside, (path, body, kind, holder)
            k = taken.get(slot, 0)
            taken[slot] = k + 1
            if k >= len(hits):
                continue
            number = hits[k]
            if kind == "f":
                number = head_of(lines, number)
        out.append((path, number, kind, fields))
    return out
