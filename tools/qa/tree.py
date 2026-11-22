"""The documented tree: its files, the facts of its source files (a tree-sitter
parse), the git questions the checkers ask, the validation of a page against it
and the mapping of excerpt units onto their files
(guidelines/page/page-model.md, source units and constructs).
"""

import datetime
import hashlib
import os
from pathlib import Path
import re
import subprocess

from tools.checkout import absolute, tree_default
from tools.tagsfile import head_of

GIT_TIMEOUT = 60
CONSTRUCT_KINDS = (
    "function",
    "struct",
    "union",
    "enum",
    "typedef",
    "variable",
    "macro",
)
# a commit id and nothing else, 12 to 40 hex digits; e.g. `8d3ae59288f1`
COMMIT_ID = re.compile(r"^[0-9a-f]{12,40}$")
TREE_MARKER = "Kconfig"


class GitError(OSError):
    pass


class FactsError(OSError):
    pass


def git(tree, *arguments, ok=(0,)):
    """The output of one git command in the tree. Every caller needs the same
    three things of it, so they stand here once: a time limit, the C locale
    that keeps the messages parseable, and a GitError that carries git's own
    words when the exit status is not one of `ok`."""
    try:
        done = subprocess.run(
            ["git", "-C", tree, *arguments],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
            env={**os.environ, "LC_ALL": "C"},
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise GitError(f"git {' '.join(arguments)}: {error}") from error
    if done.returncode not in ok:
        raise GitError(
            f"git {' '.join(arguments)}:"
            f" {done.stderr.strip() or f'exit {done.returncode}'}"
        )
    return done.stdout


class Tree:
    """A source tree: file lines, the facts of its source files and the git
    questions, cached per run."""

    def __init__(self, path, profile):
        self.path = path
        self.profile = profile
        self._lines = {}
        self._tags = {}
        self.facts_error = None
        self.head = self.tag = ""
        self.git = False
        try:
            self.git = (
                git(path, "rev-parse", "--is-inside-work-tree").strip()
                == "true"
            )
        except GitError as error:
            if "not a git repository" not in str(error):
                raise
        if self.git:
            self.head = git(path, "rev-parse", "HEAD").strip()
            tags = git(path, "tag", "--points-at", "HEAD").split()
            self.tag = tags[0] if tags else ""

    def absolute(self, relative):
        return Path(self.path, relative)

    def exists(self, relative):
        return self.absolute(relative).exists()

    def is_dir(self, relative):
        return self.absolute(relative).is_dir()

    def lines(self, relative):
        """The file's lines without their newlines (`\\r` kept), or None when
        it cannot be read."""
        if relative not in self._lines:
            try:
                with open(
                    self.absolute(relative),
                    encoding="utf-8",
                    errors="replace",
                    newline="",
                ) as handle:
                    text = handle.read()
                found = text.split("\n")
                if found and found[-1] == "":
                    found.pop()
                self._lines[relative] = found
            except OSError:
                self._lines[relative] = None
        return self._lines[relative]

    def line(self, relative, number):
        lines = self.lines(relative)
        if lines is None or not 1 <= number <= len(lines):
            return None
        return lines[number - 1]

    # ---- the facts: tree-sitter's C grammar ----

    def tags(self, relative):
        """The facts {name, kind, line, end, scope, scopeKind, typeref} of a
        source file."""
        if relative in self._tags:
            return self._tags[relative]
        if (
            not self.profile.is_source(relative)
            or not self.absolute(relative).is_file()
        ):
            self._tags[relative] = []
            return []
        try:
            parser = _parser()
        except ImportError as error:
            self.facts_error = f"tree-sitter: {error}"
            raise FactsError(self.facts_error) from error
        try:
            with open(self.absolute(relative), "rb") as handle:
                source = handle.read()
        except OSError:
            self._tags[relative] = []
            return []
        self._tags[relative] = _facts(
            parser, _blank_attributes(source), relative
        )
        return self._tags[relative]

    def constructs(self, relative):
        return [t for t in self.tags(relative) if t["kind"] in CONSTRUCT_KINDS]

    def construct_at(self, relative, line):
        """The innermost construct whose lines hold `line`, from its head (the
        first line of a split signature) to its end."""
        best = None
        for tag in self.constructs(relative):
            if tag["head"] <= line <= tag["end"] and (
                best is None or tag["head"] > best["head"]
            ):
                best = tag
        return best

    def members_of(self, relative, name):
        return [
            t
            for t in self.tags(relative)
            if t["kind"] == "member" and t.get("scope") == name
        ]

    def tag_at(self, relative, line, name):
        return [
            t
            for t in self.tags(relative)
            if t["line"] == line and t["name"] == name
        ]

    def tags_named(self, relative, name):
        return [t for t in self.tags(relative) if t["name"] == name]

    # ---- git ----

    def head_timestamp(self):
        return int(git(self.path, "log", "-1", "--format=%ct", "HEAD").strip())

    def newest_timestamp(self, relative):
        found = git(
            self.path, "log", "-1", "--format=%ct", "--", relative
        ).strip()
        return int(found) if found else None

    def commit_exists(self, sha):
        found = git(
            self.path,
            "rev-parse",
            "--verify",
            "--quiet",
            sha + "^{commit}",
            ok=(0, 1),
        ).strip()
        return bool(COMMIT_ID.match(found))

    def full_sha(self, sha):
        found = git(
            self.path,
            "rev-parse",
            "--verify",
            "--quiet",
            sha + "^{commit}",
            ok=(0, 1),
        ).strip()
        return found if COMMIT_ID.match(found) else None

    def trailers(self, sha, key):
        out = []
        for name in (key if isinstance(key, (list, tuple)) else [key]):
            out += git(
                self.path,
                "log",
                "-1",
                f"--format=%(trailers:key={name},valueonly)",
                sha,
            ).split()
        return out


_PARSER = None


def _parser():
    global _PARSER
    if _PARSER is None:
        from tree_sitter import Language, Parser
        import tree_sitter_c

        _PARSER = Parser(Language(tree_sitter_c.language()))
    return _PARSER


_NAME_NODES = ("identifier", "field_identifier", "type_identifier")

# The kernel's attribute macros that stand between a type and its declarator,
# blanked to spaces before the parse so that the declarator is read. A name
# ending in `+` takes a parenthesised argument list.
ATTRIBUTE_MACROS = (
    "__init",
    "__exit",
    "__initdata",
    "__initconst",
    "__exitdata",
    "__read_mostly",
    "__ro_after_init",
    "__maybe_unused",
    "__always_unused",
    "__cold",
    "__hot",
    "__weak",
    "__user",
    "__kernel",
    "__iomem",
    "__percpu",
    "__rcu",
    "__force",
    "__must_check",
    "__pure",
    "__noreturn",
    "__visible",
    "__nocast",
    "__sched",
    "__init_or_module",
    "__cacheline_aligned",
    "__cacheline_aligned_in_smp",
    "____cacheline_aligned",
    "____cacheline_aligned_in_smp",
    "____cacheline_internodealigned_in_smp",
    "__randomize_layout",
    "__no_randomize_layout",
    "asmlinkage",
    "noinline",
    "__always_inline",
    "__attribute_const__",
    "__deprecated",
    "__used",
    "__unused",
    "__packed",
    "__designated_init",
    "__bitwise",
    "__latent_entropy",
    "__nocfi",
    "__noclone",
    "__private",
    "__refdata",
    "__refconst",
    "__meminit",
    "__meminitdata",
    "notrace",
    "__no_kcsan",
    "__no_sanitize_address",
    "__ref",
    "__aligned+",
    "__printf+",
    "__scanf+",
    "__acquires+",
    "__releases+",
    "__must_hold+",
    "__attribute__+",
    "__section+",
    "__mode+",
    "__counted_by+",
    "__cond_acquires+",
    "__cond_releases+",
    "__acquires_shared+",
    "__releases_shared+",
    "__must_hold_shared+",
    "__must_not_hold+",
    "__guarded_by+",
    "__pt_guarded_by+",
    "__assumes_cap+",
    "__cond_lock+",
    "__acquire+",
    "__release+",
    "__free+",
    "__cleanup+",
    "__nonstring",
    "__no_context_analysis",
    "__flatten",
    "__noinstr_section+",
    "noinstr",
    "__always_kprobes",
    "__kprobes",
    "__irq_entry",
    "__exception_irq_entry",
    "__cpuidle",
    "__noendbr",
    "__preserve_most",
)
# one of the attribute macros of ATTRIBUTE_MACROS as a word of its own; e.g.
# the `__init` of `static int __init pci_setup(char *str)`
_ATTRIBUTE_RE = re.compile(
    r"\b(?:"
    + "|".join(re.escape(m.rstrip("+")) for m in ATTRIBUTE_MACROS)
    + r")\b"
)
_ATTRIBUTE_CALL = {m.rstrip("+") for m in ATTRIBUTE_MACROS if m.endswith("+")}


def _blank_attributes(source):
    """`source` with the attribute macros blanked to spaces, except on a
    preprocessor line and its continuation lines. A directive must keep its
    words: `#define __bss_decrypted __section(".bss..decrypted")`
    (arch/x86/include/asm/mem_encrypt.h:67 at v7.3) with its body blanked is
    read as running on into the lines below it, and the definition of `__init`
    itself (include/linux/init.h:45-46) with its name and all but the last word
    of its body blanked is read as defining that last word,
    `__no_kstack_erase`.
    """
    text = source.decode("utf-8", "replace")
    directive, continued, offset = [], False, 0
    for line in text.split("\n"):
        inside = continued or line.lstrip().startswith("#")
        if inside:
            directive.append((offset, offset + len(line)))
        continued = inside and line.rstrip().endswith("\\")
        offset += len(line) + 1
    spans, at = iter(directive), None
    out, pos = [], 0
    for match in _ATTRIBUTE_RE.finditer(text):
        start, stop = match.span()
        while at is None or at[1] < start:
            at = next(spans, (len(text) + 1, len(text) + 1))
        if at[0] <= start <= at[1]:
            continue
        if match.group(0) in _ATTRIBUTE_CALL:
            k = stop
            while k < len(text) and text[k] in " \t":
                k += 1
            if k < len(text) and text[k] == "(":
                depth = 0
                while k < len(text):
                    depth += {"(": 1, ")": -1}.get(text[k], 0)
                    k += 1
                    if depth == 0:
                        break
                stop = k
        if start < pos:
            continue
        out.append(text[pos:start])
        out.append(
            "".join(" " if ch != "\n" else "\n" for ch in text[start:stop])
        )
        pos = stop
    out.append(text[pos:])
    return "".join(out).encode("utf-8")


_SPECIFIERS = ("struct_specifier", "union_specifier", "enum_specifier")
# a macro definition in a file's bytes, group 1 its name; e.g. b"#define
# PCI_EXP_FLAGS 0x02" gives PCI_EXP_FLAGS
_DEFINE_LINE = re.compile(rb"\s*#\s*define\s+([A-Za-z_]\w*)")
_MACRO_AS_TYPE = ("type_identifier", "macro_type_specifier")
# a macro-style name, capitals, digits and underscores; e.g. b"DEFINE_MUTEX",
# and not b"pci_dev"
_MACRO_NAME = re.compile(rb"[A-Z_][A-Z0-9_]*")
_REPARSES = 64


def _member_macros(root, source):
    """The byte spans of the macro invocations that stand in a struct or union
    body as members with no `;` (the macro expands to the members), each read
    by the parse as the type of a field it does not belong to: a
    field_declaration that opens with the macro and holds after it either
    nothing but an ERROR node spelling `}`, the body's closing brace, or,
    starting on a later line, the next member's text broken by an ERROR node or
    a missing `;`. The second form asks for a name in capitals, since a type on
    one line with its declarator on the next is legal C and a broken declarator
    alone must not cost that field its type. Two such macros in a row are read
    as a field's type and its name, with the closing brace in an ERROR node or
    the `;` missing after them (drivers/acpi/acpica/amlresrc.h:217-218 and
    333-340 at v7.3, struct aml_resource_address and struct
    aml_resource_csi2_serialbus); both names are in capitals and both spans are
    returned."""

    def spelled(node):
        return source[node.start_byte : node.end_byte]

    spans, stack = [], [root]
    while stack:
        node = stack.pop()
        if not node.has_error:
            continue
        if node.type == "field_declaration":
            parts = [
                child for child in node.children if child.type != "comment"
            ]
            macro = (
                parts[0] if parts and parts[0].type in _MACRO_AS_TYPE else None
            )
            if macro is not None and len(parts) > 1:
                after = parts[1]
                if after.type == "ERROR" and spelled(after).strip() == b"}":
                    spans.append((macro.start_byte, macro.end_byte))
                elif (
                    len(parts) > 2
                    and macro.type == "type_identifier"
                    and after.type == "field_identifier"
                    and _MACRO_NAME.fullmatch(spelled(macro))
                    and _MACRO_NAME.fullmatch(spelled(after))
                    and (
                        parts[2].is_missing
                        or (
                            parts[2].type == "ERROR"
                            and spelled(parts[2]).strip() == b"}"
                        )
                    )
                ):
                    spans += [
                        (macro.start_byte, macro.end_byte),
                        (after.start_byte, after.end_byte),
                    ]
                elif macro.end_point[0] < after.start_point[0] and any(
                    part.type == "ERROR" or part.is_missing
                    for part in parts[1:]
                ):
                    named = (
                        macro
                        if macro.type == "type_identifier"
                        else next(
                            (
                                c
                                for c in macro.children
                                if c.type == "identifier"
                            ),
                            None,
                        )
                    )
                    if named is not None and _MACRO_NAME.fullmatch(
                        source[named.start_byte : named.end_byte]
                    ):
                        spans.append((macro.start_byte, macro.end_byte))
        stack.extend(node.children)
    return spans


# a word that opens with two underscores, the spelling of an attribute; e.g.
# b"__must_check" and b"__free"
_ATTRIBUTE_WORD = re.compile(rb"__\w+")
_DECLARATORS = (
    "identifier",
    "field_identifier",
    "array_declarator",
    "pointer_declarator",
)


def _trailing_attributes(root, source):
    """The byte spans of the attribute macros that follow a declarator and that
    ATTRIBUTE_MACROS does not name. The parse reads such a macro as the
    declarator and leaves the real one in an ERROR node: `struct memblock
    memblock __initdata_memblock = {` (mm/memblock.c:129 at v7.3) is read as a
    variable named `__initdata_memblock`. The declarator's place is taken, so a
    name that opens with two underscores and follows an ERROR node holding a
    declarator can only be an attribute; it is blanked like the listed ones. A
    held name that itself opens with two underscores is left alone, since there
    the first word is the attribute and the second the name (`bool
    __list_valid_slowpath __list_add_valid_or_report(...)`,
    include/linux/list.h:69), which the parse reads right as it stands."""
    spans, stack = [], [root]
    while stack:
        node = stack.pop()
        if not node.has_error:
            continue
        if node.type in ("declaration", "field_declaration"):
            parts = [
                child for child in node.children if child.type != "comment"
            ]
            for held, after in zip(parts, parts[1:]):
                if (
                    held.type != "ERROR"
                    or not held.children
                    or held.children[-1].type not in _DECLARATORS
                ):
                    continue
                if _ATTRIBUTE_WORD.match(
                    source[held.start_byte : held.end_byte].lstrip(b"* \t")
                ):
                    continue
                named = (
                    after.child_by_field_name("declarator")
                    if after.type == "init_declarator"
                    else after
                )
                if (
                    named is not None
                    and named.type in ("identifier", "field_identifier")
                    and _ATTRIBUTE_WORD.fullmatch(
                        source[named.start_byte : named.end_byte]
                    )
                ):
                    spans.append((named.start_byte, named.end_byte))
        stack.extend(node.children)
    return spans


# a preprocessor conditional, group 1 its directive; e.g. b"#ifdef
# CONFIG_PCIEAER" gives ifdef and b"# endif" gives endif
_CONDITIONAL = re.compile(
    rb"\s*#\s*(if|ifdef|ifndef|elif|elifdef|elifndef|else|endif)\b"
)


# A comment, or a string or character literal up to its closing quote or the
# end of its line.
# e.g. b"/* text */", b"// text", b'"a } b"' and b"'{'"
_LITERAL = re.compile(
    rb'/\*.*?(?:\*/|\Z)|//[^\n]*|"(?:\\(?:.|\Z)|[^"\\\n])*(?:"|\n|\Z)|'
    rb"\'(?:\\(?:.|\Z)|[^\'\\\n])*(?:\'|\n|\Z)",
    re.S,
)
_TO_SPACES = bytes(0x0A if byte == 0x0A else 0x20 for byte in range(256))


def _code_only(source):
    """`source` with every comment, string literal and character literal
    blanked to spaces, newlines kept: the text in which a brace is a block's
    and a `#` at the head of a line a directive's.
    """
    return _LITERAL.sub(
        lambda found: found.group(0).translate(_TO_SPACES), source
    )


def _one_branch(source):
    """`source` with every conditional group that tree-sitter-c cannot read as
    alternatives reduced to its first branch: the group's directive lines and
    its other branches blanked to spaces. Two forms are reduced. Branches that
    each leave the same nonzero number of braces or parentheses open spell one
    opening once per configuration, as in

    #if defined(CONFIG_DRM_AMD_DC_DCN6_0) || defined(CONFIG_DRM_AMD_DC_DCN5_0)
            if (adev->family == AMDGPU_FAMILY_GC_12_0_0
                || adev->family == AMDGPU_FAMILY_GC_13_0_1) {
    #else
            if (adev->family == AMDGPU_FAMILY_GC_12_0_0) {
    #endif

    (drivers/gpu/drm/amd/display/amdgpu_dm/amdgpu_dm_cursor.c:90-95 at v7.3),
    and the parser, which reads every branch, counts two openings for the one
    closing brace: dm_check_cursor_fb, lines 44-111, was read as running to the
    end of the file, line 448, over the five functions after it. And a group
    that opens inside an open parenthesis, between the operands of a condition
    or the parameters of a signature (the same file's lines 300-305, inside the
    condition of an `if`), stands where the grammar takes no directive, so the
    statement breaks there: amdgpu_dm_crtc_get_cursor_mode, lines 275-448, was
    read as ending at line 309. A brace or parenthesis inside a directive line
    (a `#define` body) is not counted. The parenthesis depth follows the first
    branch of every group, the text the reduced source keeps, and returns to
    zero at a line that ends a statement or opens or closes a block, so that an
    unbalanced line cannot carry it on.
    """
    lines = _code_only(source).split(b"\n")
    blank, stack, continued, depth = [], [], False, 0
    for number, line in enumerate(lines):
        directive = continued or line.lstrip().startswith(b"#")
        match = (
            None if continued or not directive else _CONDITIONAL.match(line)
        )
        continued = directive and line.rstrip().endswith(b"\\")
        if not directive:
            braces, parens = line.count(b"{") - line.count(b"}"), line.count(
                b"("
            ) - line.count(b")")
            if stack:
                stack[-1]["balance"][0] += braces
                stack[-1]["balance"][1] += parens
            depth = (
                0
                if line.rstrip().endswith((b";", b"{", b"}"))
                else max(0, depth + parens)
            )
            continue
        if match is None:
            continue
        word = match.group(1)
        if word in (b"if", b"ifdef", b"ifndef"):
            stack.append(
                {
                    "directives": [number],
                    "branches": [],
                    "from": number + 1,
                    "balance": [0, 0],
                    "depth": depth,
                }
            )
            continue
        if not stack:
            continue
        group = stack[-1]
        group["branches"].append(
            (group["from"], number, tuple(group["balance"]))
        )
        group["directives"].append(number)
        group["from"], group["balance"] = number + 1, [0, 0]
        depth = group["depth"]
        if word != b"endif":
            continue
        stack.pop()
        balances = [balance for _, _, balance in group["branches"]]
        same_opening = (
            len(balances) > 1
            and balances[0] != (0, 0)
            and all(balance == balances[0] for balance in balances)
        )
        if same_opening or group["depth"] > 0:
            blank += group["directives"]
            for start, stop, _ in group["branches"][1:]:
                blank += range(start, stop)
            seen = balances[0]
        else:
            seen = (sum(balance[0] for balance in balances), balances[0][1])
        depth = max(0, group["depth"] + balances[0][1])
        if stack:
            stack[-1]["balance"][0] += seen[0]
            stack[-1]["balance"][1] += seen[1]
    if not blank:
        return source
    out = source.split(b"\n")
    for number in blank:
        out[number] = b" " * len(out[number])
    return b"\n".join(out)


# the opening of an invocation at the start of a line: an optional `static`, a
# name and `(`; e.g. b"_PCI_NOP_ALL(read, *)" and b"static DEFINE_MUTEX(lock)"
_INVOCATION = re.compile(rb"(?:static\s+)?[A-Za-z_]\w*\s*\(")


def _bare_invocations(source, code, directive):
    """(text, lines): `source` with the macro invocations that stand alone at
    file scope blanked to spaces, and the indexes of the lines blanked; `code`
    is its lines with comments and literals blanked and `directive` says which
    of them are a directive's. A line in column 0 that is nothing but
    `NAME(arguments)`, over one or more lines, with no `;` after it and no body
    below it, is a declaration the macro writes, and tree-sitter-c reads it as
    the type of the definition after it, which then loses its name or is lost
    with the ones that follow (include/linux/pci.h:2148-2149 at v7.3,
    `_PCI_NOP_ALL(read, *)`, after which pci_probe_flush_workqueue and
    pci_get_device were not read). Such a line is taken only where it starts a
    statement: after an empty line, a directive, or a line that ends a
    statement, a block or another invocation. A name on a line of its own under
    its return type (include/linux/spinlock_api_smp.h:26,
    `_raw_spin_lock_nest_lock(...)` under `void __lockfunc`) is a declarator
    and stays, as does a line followed by `;`, `=` or `,`."""
    blank, i = [], 0
    while i < len(code):
        above = code[i - 1].rstrip() if i else b""
        if (
            directive[i]
            or not _INVOCATION.match(code[i])
            or not (
                i == 0
                or directive[i - 1]
                or not above
                or above.endswith((b";", b"}", b")"))
            )
        ):
            i += 1
            continue
        depth, last = 0, None
        for k in range(i, min(len(code), i + 60)):
            if directive[k]:
                break
            depth += code[k].count(b"(") - code[k].count(b")")
            if depth <= 0:
                last = k
                break
        text = b"".join(code[i : last + 1]) if last is not None else b""
        below = (
            next(
                (
                    code[k].lstrip()
                    for k in range(last + 1, len(code))
                    if code[k].strip()
                ),
                b"",
            )
            if last is not None
            else b""
        )
        if (
            last is None
            or depth < 0
            or not code[last].rstrip().endswith(b")")
            or b";" in text
            or b"{" in text
            or below[:1] in (b"{", b";", b"=", b",")
        ):
            i += 1
            continue
        blank += range(i, last + 1)
        i = last + 1
    if not blank:
        return source, []
    out = source.split(b"\n")
    for number in blank:
        out[number] = b" " * len(out[number])
    return b"\n".join(out), blank


def _parse(parser, source):
    """(source, root): the parse of `source` once every conditional group that
    opens one block per branch is reduced to one branch (_one_branch) and no
    macro stands in a body as a field's type. A struct or union body that holds
    a bare macro invocation with no `;` (the macro expands to members) makes
    tree-sitter-c read the macro as the type of a field. Where the macro is the
    body's last item, the closing brace becomes an error inside that field, the
    body runs on to a later brace and every definition up to it is filed as the
    body's member (drivers/gpu/drm/amd/display/dmub/inc/dmub_cmd.h:2735-2737 at
    v7.3, union dmub_fams2_cmd_stream_static_sub_state, read as running to line
    8066 over 336 other constructs). Where a member follows it, the first word
    of that member becomes the field's name and the member itself is lost or
    loses its type (the same file's lines 2739-2742, union
    dmub_fams2_stream_static_sub_state_v2, read as holding a member named
    `struct`). Such an invocation is blanked to spaces, as an attribute macro
    is, and the text parsed again; one repair can uncover the next, so the
    parse repeats until it finds none. An attribute macro the list does not
    name, read as a declarator, is blanked in the same pass
    (_trailing_attributes)."""
    source = _one_branch(source)
    root = parser.parse(source).root_node
    for _ in range(_REPARSES):
        spans = _member_macros(root, source) + _trailing_attributes(
            root, source
        )
        if not spans:
            break
        text = bytearray(source)
        for start, stop in spans:
            for k in range(start, stop):
                if text[k] != 0x0A:
                    text[k] = 0x20
        source = bytes(text)
        root = parser.parse(source).root_node
    return source, root


_C_KEYWORDS = frozenset(
    (
        "auto break case char const continue default do double else enum"
        " extern float for goto if inline int long register restrict return"
        " short signed sizeof static struct switch typedef union unsigned void"
        " volatile while"
    ).split()
)
# the line that opens the body of a struct, union or enum, group 1 the keyword
# and group 2 the tag; e.g. b"struct pci_dev {" and b"typedef struct foo {"
_TYPE_HEAD = re.compile(
    rb"(?:typedef\s+)?(struct|union|enum)\s+([A-Za-z_]\w*)\s*\{\s*$"
)
# the line that opens a struct declared through context_lock_struct, group 1
# its tag; e.g. b"context_lock_struct(local_lock) {" gives local_lock
_LOCK_HEAD = re.compile(
    rb"context_lock_struct\(\s*([A-Za-z_]\w*)\s*(?:,[^()]*)?\)\s*\{\s*$"
)
# a declaration that ends in `=` or `= {`, the opening of an initializer, group
# 1 the brace when there is one; e.g. b"static const struct pci_error_handlers
# err = {"
_INITIALIZED = re.compile(rb"[A-Za-z_][^;(){}=]*=\s*(\{)?\s*$")


def _directive_lines(code, written):
    """Per line, whether it is a preprocessor line or continues one. A `#`
    opens a directive where it heads a line of `code`, the text with comments
    and literals blanked; a backslash continues it where it ends the line as
    `written`, comments included, since a compiler joins the lines before it
    reads the comments: a comment block in a macro's body, each of its lines
    ending in a backslash, does not end the macro
    (include/linux/interval_tree_generic.h:28-183 at v7.3,
    INTERVAL_TREE_DEFINE).
    """
    out, continued = [], False
    for line, raw in zip(code, written):
        directive = continued or line.lstrip().startswith(b"#")
        out.append(directive)
        continued = directive and raw.rstrip().endswith(b"\\")
    return out


def _attribute_tail(text):
    """Whether `text`, what follows a parameter list in a signature, holds
    attribute macros alone: names that open with two underscores, each with or
    without an argument list (`__must_hold(&lock) __cold`).
    """
    i, named = 0, False
    while i < len(text):
        if text[i].isspace():
            i += 1
        elif text[i] == "(":
            if not named:
                return False
            depth = 0
            while i < len(text):
                depth += {"(": 1, ")": -1}.get(text[i], 0)
                i += 1
                if depth == 0:
                    break
            named = False
        else:
            # the identifier that stands at this point of an attribute tail;
            # e.g. `__init` of `__init __must_check`
            word = re.match(r"[A-Za-z_]\w*", text[i:])
            if word is None or not word.group(0).startswith("__"):
                return False
            i += word.end()
            named = True
    return True


# a function a macro defines from the one name it is given, group 1 the name;
# e.g. `static DEFINE_SHOW(aer_stats)` hands the name aer_stats to the macro
_MACRO_DEFINITION = re.compile(
    r"(?:static\s+)?[A-Z_][A-Z0-9_]*\s*\(\s*([A-Za-z_]\w*)\s*\)"
)
_TYPE_WORDS = frozenset(
    "void char short int long float double signed unsigned bool _Bool struct"
    " union enum const volatile".split()
)


def _declares_parameters(text):
    """Whether the parenthesised `text` reads as a parameter list and not as
    the arguments of an attribute macro: it is empty, names a type by a C word,
    ends in `...`, or holds an entry of two words or more, a type and a name
    (`const char * const POS p`), where an attribute's arguments are single
    expressions (`__diagnose_as(__builtin_strlen, 1)`,
    `__must_hold(&lock)`)."""
    inner = text.strip()[1:-1]
    if not inner.strip() or "..." in inner:
        return True
    for entry in inner.split(","):
        # the identifiers of one entry of a parameter list; e.g. `struct
        # pci_dev *dev` gives struct, pci_dev and dev
        words = re.findall(r"[A-Za-z_]\w*", entry)
        if len(words) >= 2 or any(word in _TYPE_WORDS for word in words):
            return True
    return False


def _signature(text):
    """(name, callers) of a function signature, or (None, []) when `text` is no
    signature. `callers` are the identifiers that stand before each
    parenthesised group at the top level, and the name is the one before the
    parameter list, in a text that holds no `=`, `;` or brace outside
    parentheses. The parameter list is the first group that declares parameters
    (_declares_parameters) and after which only attribute macros stand
    (_attribute_tail), so an attribute with arguments, before the name or after
    the list, known to the parse or not, is not taken for the list; where no
    group declares parameters, as in a macro's invocation above a body, it is
    the first group with nothing but attributes after it. A definition a macro
    writes, `DEFINE_IDTENTRY(exc_divide_error)` above the body
    (arch/x86/kernel/traps.c:380 at v7.3), is named by its one argument, as the
    parse names it."""
    depth, groups, start = 0, [], 0
    for i, ch in enumerate(text):
        if ch == "(":
            if depth == 0:
                start = i
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return None, []
            if depth == 0:
                groups.append((start, i))
        elif depth == 0 and ch in "=;{}":
            return None, []
    if depth:
        return None, []
    # the identifier right before each parenthesis group, the name the group
    # belongs to; e.g. pci_walk_bus before the `(` of `void pci_walk_bus(struct
    # pci_bus *top)`
    callers = [
        m.group(1)
        for m in (
            re.search(r"([A-Za-z_]\w*)\s*$", text[:start])
            for start, _ in groups
        )
        if m
    ]
    written = _MACRO_DEFINITION.fullmatch(text.strip())
    if written:
        return written.group(1), callers
    declaring = [
        group
        for group in groups
        if _declares_parameters(text[group[0] : group[1] + 1])
    ]
    for start, stop in declaring + groups:
        if _attribute_tail(text[stop + 1 :]):
            # the same lookup for the group that declares the parameters; e.g.
            # pci_walk_bus of `void pci_walk_bus(struct pci_bus *top) __init`
            named = re.search(r"([A-Za-z_]\w*)\s*$", text[:start])
            return (
                named.group(1)
                if named and named.group(1) not in _C_KEYWORDS
                else None
            ), callers
    return None, callers


def _body_end(code, directive, opener):
    """(end, column, matched), line indexes or None: where the body opened at
    line index `opener` closes. Two readings check each other: `column`, the
    first `}` in column 0 after the opener, which kernel style makes the
    closing brace, and `matched`, the line where the braces opened since the
    opener are all closed. They differ where a closing brace is indented
    (amdgpu_dm_helpers.c:508 at v7.3, ` }`), where an initializer inside the
    body closes in column 0 (arch/x86/mm/dump_pagetables.c:435) and where a
    macro hides a brace. `end` is the earlier of the two if the next line of
    code after it starts in column 0, a new definition; else the later one."""
    column = next(
        (
            k
            for k in range(opener + 1, len(code))
            if not directive[k] and code[k].startswith(b"}")
        ),
        None,
    )
    depth, matched = 0, None
    for k in range(opener, len(code)):
        if directive[k]:
            continue
        depth += code[k].count(b"{") - code[k].count(b"}")
        if depth <= 0:
            matched = k
            break
    candidates = sorted({c for c in (column, matched) if c is not None})
    for candidate in candidates:
        below = next(
            (
                code[k]
                for k in range(candidate + 1, len(code))
                if code[k].strip() and not directive[k]
            ),
            b"",
        )
        if not below[:1].isspace():
            return candidate, column, matched
    return (candidates[-1] if candidates else None), column, matched


def _style_functions(code, directive, soft):
    """[(first, open, end, name, name line, column, matched, callers)], lines
    1-based: the function definitions of a file read from its layout alone, as
    kernel style writes them. A `{` alone in column 0 opens a body; the run of
    lines above it, up to an empty line, a directive or a line that ends a
    statement or a block, is the signature (a line in `soft`, one a repair
    blanked, such as an attribute between the parameter list and the brace, is
    stepped over, as are the directives that close a conditional group and the
    empty lines that stand between a parameter list and the brace); and the
    body closes where _body_end says, whose two readings are returned with it.
    `code` is the text with comments and literals blanked."""
    out, i = [], 0
    while i < len(code):
        if directive[i] or code[i].rstrip() != b"{":
            i += 1
            continue
        end, column, matched = _body_end(code, directive, i)
        if end is None:
            break
        k, run = i - 1, []
        while k >= 0 and (directive[k] or not code[k].strip()):
            # `#endif`, or an empty line, between the signature and the brace
            k -= 1
        if k < 0 or not code[k].rstrip().endswith(b")"):
            k = i - 1
        while k >= 0 and (
            soft[k]
            or (
                code[k].strip()
                and not directive[k]
                and not code[k].rstrip().endswith((b";", b"}", b"{"))
            )
        ):
            if not soft[k]:
                run.append(k)
            k -= 1
        run.reverse()
        name, callers = (
            _signature(
                " ".join(
                    code[j].decode("utf-8", "replace").strip() for j in run
                )
            )
            if run
            else (None, [])
        )
        if name:
            # the function's name as a whole word of the file's bytes; e.g.
            # b"pci_walk_bus" in b"void pci_walk_bus(", and not in
            # b"__pci_walk_bus("
            spelled = re.compile(rb"\b" + name.encode("utf-8") + rb"\b")
            at = next(
                (j for j in reversed(run) if spelled.search(code[j])), run[0]
            )
            out.append(
                (
                    run[0] + 1,
                    i + 1,
                    end + 1,
                    name,
                    at + 1,
                    None if column is None else column + 1,
                    None if matched is None else matched + 1,
                    callers,
                )
            )
        i = end + 1
    return out


def _blocks(code, directive):
    """[(open, close)], line indexes: the blocks that open at file scope, by
    layout. A line in column 0 that ends in `{` opens one, and it closes on the
    line where the braces opened since are all closed: a line that starts with
    `}` in column 0, as kernel style closes a function, a type and an
    initializer alike, or a line that ends in `};`
    (drivers/acpi/acpica/amlresrc.h:217-218 at v7.3, a struct whose members are
    two macros). Where the braces close on any other line, or a `}` in column 0
    comes while some are open, the text is not laid out as this reading expects
    and no block is reported for it."""
    out, opened, depth = [], None, 0
    for i, line in enumerate(code):
        if directive[i]:
            continue
        if opened is None:
            if not (
                line[:1].strip()
                and not line.startswith(b"}")
                and line.rstrip().endswith(b"{")
            ):
                continue
            opened, depth = i, 0
        depth += line.count(b"{") - line.count(b"}")
        if i == opened:
            continue
        if line.startswith(b"}") or depth <= 0:
            if depth <= 0 and (
                line.startswith(b"}") or line.rstrip().endswith(b"};")
            ):
                out.append((opened, i))
            opened = None
    return out


def _settle_functions(found, style, source_lines):
    """Bring the file-scope function facts in line with the functions of the
    layout (_style_functions), in place, and return the ids of the facts that
    are such a function. One the parse lost is added. One the parse has keeps
    its head and its name, except that a name which is a C keyword, or an
    attribute macro standing before the real name with an argument list of its
    own (`__diagnose_as(...)`, include/linux/fortify-string.h:210 at v7.3),
    gives way to the signature's; and it takes the layout's end unless its own
    end is one of two readings of the body's end that differ."""
    top = [f for f in found if f["kind"] == "function" and not f["scope"]]
    settled = set()
    for first, opener, last, name, at, column, matched, callers in style:
        own = [
            f
            for f in top
            if first - 1 <= f["head"] <= opener and id(f) not in settled
        ]
        fact = next(
            (f for f in own if f["name"] == name), own[0] if own else None
        )
        if fact is None:
            fact = {
                "name": name,
                "kind": "function",
                "line": at,
                "head": max(first, head_of(source_lines, at)),
                "end": last,
                "scope": None,
                "scopeKind": None,
                "typeref": None,
            }
            found.append(fact)
        else:
            if fact["name"] != name and (
                fact["name"] in _C_KEYWORDS or fact["name"] in callers
            ):
                fact["name"], fact["line"], fact["head"] = (
                    name,
                    at,
                    max(first, head_of(source_lines, at)),
                )
            if fact["end"] != last and (
                column == matched or fact["end"] not in (column, matched)
            ):
                fact["end"] = last
        settled.add(id(fact))
    return settled


def _runs_into_a_body(text):
    """Whether `text`, the lines of a function fact, show a signature that runs
    into a body of its own: a parameter list, then nothing but plain words
    (attribute macros), then `{`, with no statement ending before it."""
    before = text.split(b"{", 1)[0]
    words = before[before.rfind(b")") + 1 :].split()
    # every word between the parameter list and `{` is a plain identifier, an
    # attribute macro; e.g. the b"__init" of `static int foo(void) __init {`
    return (
        b"{" in text
        and b")" in before
        and b";" not in before
        and b"}" not in before
        and all(
            re.fullmatch(rb"[A-Za-z_]\w*", word)
            and word.decode() not in _C_KEYWORDS
            for word in words
        )
    )


def _drop_misreadings(found, style, settled, code, directive):
    """Drop, in place, the facts the parse made of text that defines nothing of
    the kind: a fact named by a C keyword (`STATIC_IFN_KUNIT struct
    dc_stream_state *` above a name, amdgpu_dm_connector.c:1449 at v7.3, read
    as a variable named `struct`); a function fact at file scope that overlaps
    a function of the layout without being it; a variable or a prototype filed
    at file scope from inside a function's body; a function fact with no
    signature that runs into a body of its own; and what the parse read out of
    a directive's lines, where it takes a macro's body for code once a comment
    in it has ended its reading of the macro. A function with a signature and a
    body of its own stays even there: the body of a macro that writes functions
    (include/linux/interval_tree_generic.h:38-63 at v7.3, `_insert` inside
    INTERVAL_TREE_DEFINE) is read as those functions, each of which is a place
    a page can name."""
    spans = [(first, last) for first, _, last, *_ in style]
    bodies = [(opener, last) for _, opener, last, *_ in style]
    dropped = set()
    for fact in found:
        if fact["kind"] == "macro":
            continue
        if fact["name"] in _C_KEYWORDS:
            dropped.add(id(fact))
        elif fact["scope"]:
            continue
        elif fact["kind"] == "function" and id(fact) not in settled:
            if any(
                fact["head"] <= last and fact["end"] >= first
                for first, last in spans
            ):
                dropped.add(id(fact))
        elif fact["kind"] in ("variable", "prototype") and any(
            opener < fact["line"] <= last for opener, last in bodies
        ):
            dropped.add(id(fact))
    for fact in found:
        if (
            id(fact) in dropped
            or fact["kind"] == "macro"
            or not 0 < fact["head"] <= len(code)
        ):
            continue
        inside = directive[fact["head"] - 1]
        if fact["kind"] != "function" or fact["scope"]:
            if inside:
                dropped.add(id(fact))
        elif inside:
            own = b" ".join(
                code[k].rstrip().rstrip(b"\\")
                for k in range(fact["head"] - 1, min(len(code), fact["end"]))
            )
            if not _runs_into_a_body(own):
                dropped.add(id(fact))
        elif id(fact) not in settled and fact["end"] > fact["head"]:
            own = b" ".join(
                code[k]
                for k in range(fact["head"] - 1, min(len(code), fact["end"]))
                if not directive[k]
            )
            if not _runs_into_a_body(own):
                dropped.add(id(fact))
    found[:] = [fact for fact in found if id(fact) not in dropped]


def _recover_behind_invocations(
    found, parser, source, code, directive, relative
):
    """Add, in place, the definitions the parse lost behind a macro invocation
    that stands alone at file scope. The text is parsed a second time without
    such invocations (_bare_invocations); what that parse reads where the first
    one has nothing is added, nothing else changes, and a fact the first parse
    read out of such an invocation is dropped."""
    bare, blanked = _bare_invocations(source, code, directive)
    if not blanked:
        return
    on = {number + 1 for number in blanked}
    found[:] = [
        f
        for f in found
        if f["kind"] == "macro" or f["scope"] or f["line"] not in on
    ]
    taken = [
        (f["head"], f["end"])
        for f in found
        if not f["scope"] and f["kind"] != "macro"
    ]
    for fact in _facts(parser, bare, relative, part=len(found) + 500):
        if (
            fact["scope"]
            or fact["kind"]
            not in ("function", "prototype", "variable", "typedef")
            or fact["name"] in _C_KEYWORDS
        ):
            continue
        if not any(
            head <= fact["end"] and end >= fact["head"] for head, end in taken
        ):
            found.append(fact)
            taken.append((fact["head"], fact["end"]))


def _layout_fact(name, kind, first, last):
    """A fact the layout alone gives: a file-scope name and the lines of its
    block, first..last as indexes."""
    return {
        "name": name,
        "kind": kind,
        "line": first + 1,
        "head": first + 1,
        "end": last + 1,
        "scope": None,
        "scopeKind": None,
        "typeref": None,
    }


class _Layout:
    """The lines of one file beside the facts its parse left, to which the
    recovery adds in place."""

    def __init__(self, found, parser, lines, code, directive, relative):
        self.found = found
        self.parser = parser
        self.lines = lines
        self.code = code
        self.directive = directive
        self.relative = relative

    def again(self, first, last, head_text=None):
        """Parse lines first..last (indexes) on their own and file their facts
        in place of what the parse of the whole file left on those lines."""
        found = self.found
        chunk = self.lines[first : last + 1]
        if head_text is not None:
            chunk = [head_text] + chunk[1:]
        part = _facts(
            self.parser,
            b"\n".join(chunk) + b"\n",
            self.relative,
            part=len(found) + 1000 * (first + 1),
        )
        found[:] = [
            f
            for f in found
            if f["kind"] == "macro" or not first + 1 <= f["line"] <= last + 1
        ]
        for fact in part:
            if fact["kind"] != "macro":
                fact["line"], fact["head"], fact["end"] = (
                    fact["line"] + first,
                    fact["head"] + first,
                    fact["end"] + first,
                )
                found.append(fact)
        return part

    def variable(self, first, last):
        """The variable declared on lines first..last (indexes), if the parse
        has none there."""
        if any(
            f["kind"] == "variable"
            and not f["scope"]
            and first + 1 <= f["line"] <= last + 1
            for f in self.found
        ):
            return
        part = self.again(first, last)
        if any(f["kind"] == "variable" and not f["scope"] for f in part):
            return
        # the identifiers of a declaration up to its `=`, the array brackets
        # taken out first; e.g. b"static int pci_cache[8] = {" gives static,
        # int and pci_cache
        words = re.findall(
            rb"[A-Za-z_]\w*",
            re.sub(rb"\[[^\]]*\]", b"", self.code[first].split(b"=")[0]),
        )
        words = [w for w in words if w.decode() not in _C_KEYWORDS]
        named = next(
            (w for w in reversed(words) if not w.startswith(b"__")),
            words[-1] if words else None,
        )
        if named is not None:
            self.found.append(
                _layout_fact(
                    named.decode("utf-8", "replace"), "variable", first, last
                )
            )

    def type_block(self, first, last, typed, lock):
        """The struct, union or enum whose block is lines first..last
        (indexes), if the parse has none that begins there."""
        kind = typed.group(1).decode() if typed else "struct"
        name = (typed.group(2) if typed else lock.group(1)).decode(
            "utf-8", "replace"
        )
        if any(
            f["kind"] == kind and f["name"] == name and f["head"] == first + 1
            for f in self.found
        ):
            return
        part = self.again(
            first,
            last,
            None if typed else b"struct " + lock.group(1) + b" {",
        )
        if not any(f["kind"] == kind and f["name"] == name for f in part):
            self.found.append(_layout_fact(name, kind, first, last))

    def statement_end(self, first):
        """The index of the line that ends the statement whose `=` ends line
        `first`: the line of its `;`, or of the `#endif` of a conditional
        group opened in it; None when the next 200 lines hold no end."""
        code, directive = self.code, self.directive
        depth, groups, last = 0, 0, None
        for k in range(first + 1, min(len(code), first + 200)):
            if directive[k]:
                word = _CONDITIONAL.match(code[k])
                groups += (
                    0
                    if word is None
                    else {
                        b"if": 1,
                        b"ifdef": 1,
                        b"ifndef": 1,
                        b"endif": -1,
                    }.get(word.group(1), 0)
                )
                if last is not None and groups <= 0:
                    last = k
                    break
                continue
            if last is None:
                depth += (
                    code[k].count(b"{")
                    + code[k].count(b"(")
                    - code[k].count(b"}")
                    - code[k].count(b")")
                )
                if depth <= 0 and b";" in code[k]:
                    last = k
                    if groups <= 0:
                        break
        return last

    def recover(self, style):
        code, directive = self.code, self.directive
        inside = [(opener - 1, last - 1) for _, opener, last, *_ in style]
        blocks = _blocks(code, directive)
        within = [False] * len(code)
        for opener, close in inside + blocks:
            within[opener : close + 1] = [True] * (close + 1 - opener)
        # a variable whose initializer begins on the line after its `=`
        for first, text in enumerate(code):
            if (
                within[first]
                or directive[first]
                or not text.rstrip().endswith(b"=")
                or not _INITIALIZED.match(text)
            ):
                continue
            last = self.statement_end(first)
            if last is not None:
                self.variable(first, last)
        # a type or a variable whose block opens in column 0
        for first, last in blocks:
            if any(opener <= first <= close for opener, close in inside):
                continue
            typed, lock = _TYPE_HEAD.match(code[first]), _LOCK_HEAD.match(
                code[first]
            )
            if typed or lock:
                self.type_block(first, last, typed, lock)
            elif _INITIALIZED.match(code[first]):
                self.variable(first, last)


def _recover_by_layout(found, parser, lines, code, directive, style, relative):
    """Add, in place, the types and the initialized variables that the layout
    shows at file scope and the parse lost, each parsed again on its own lines:
    a struct, union or enum that opens in column 0, the kernel's
    `context_lock_struct(NAME) {` (include/linux/mutex_types.h:41 at v7.3,
    struct mutex, parsed as `struct NAME {`), and a variable whose initializer
    opens a block on the line of its `=` or begins on the line after it
    (sound/soc/codecs/rt5682.c:787). Where the lines parsed alone still give no
    such fact, the name the layout shows is filed with the block's range."""
    _Layout(found, parser, lines, code, directive, relative).recover(style)


def _settle(found, parser, source, source_lines, relative):
    """Hold the parse to the file's layout, in place. tree-sitter-c recovers
    from what it cannot read (a macro invocation with no `;` at file scope, a
    specifier macro it does not know, a statement macro with a block, a
    directive inside an expression) by ending a function early or late, by
    losing the definitions after it or by naming a call or a keyword as a
    definition, and each new file finds a new way. Kernel style writes a
    definition's layout the same way everywhere, and the layout does not depend
    on the parse: where the two disagree the layout decides, and what the parse
    read right is left as it is. The functions first (_settle_functions), then
    what the parse misread (_drop_misreadings), then what it lost
    (_recover_behind_invocations, _recover_by_layout)."""
    lines = source.split(b"\n")
    code = _code_only(source).split(b"\n")
    directive = _directive_lines(code, lines)
    # blanked by a repair, or spaces alone
    soft = [bool(line) and not line.strip() for line in lines]
    style = _style_functions(code, directive, soft)
    settled = _settle_functions(found, style, source_lines)
    _drop_misreadings(found, style, settled, code, directive)
    _recover_behind_invocations(
        found, parser, source, code, directive, relative
    )
    _recover_by_layout(found, parser, lines, code, directive, style, relative)


def _line(node):
    return node.start_point[0] + 1


def _end(node):
    row, column = node.end_point
    return row if column == 0 else row + 1


def _name_node(decl):
    """The node that spells the name a declarator declares, or None."""
    node = decl
    while node is not None:
        if node.type in _NAME_NODES:
            return node
        inner = node.child_by_field_name("declarator")
        if inner is None:
            inner = next(
                (
                    c
                    for c in node.children
                    if c.is_named
                    and (
                        c.type.endswith("declarator") or c.type in _NAME_NODES
                    )
                ),
                None,
            )
        node = inner
    return None


def _declares_function(decl):
    node = decl
    while node is not None:
        if node.type == "function_declarator":
            inner = node.child_by_field_name("declarator")
            while inner is not None and inner.type in (
                "array_declarator",
                "attributed_declarator",
            ):
                inner = inner.child_by_field_name("declarator")
            return inner is not None and inner.type in _NAME_NODES
        node = node.child_by_field_name("declarator")
    return False


def _body_members(body):
    """The children of a struct, union or enum body in source order, those
    inside a conditional group or an ERROR node among them."""
    members = []
    for child in body.children:
        if child.type in (
            "preproc_if",
            "preproc_ifdef",
            "preproc_elif",
            "preproc_else",
            "ERROR",
        ):
            members.extend(_body_members(child))
        else:
            members.append(child)
    return members


class _Collector:
    """The facts of one parsed source, gathered as its syntax tree is walked:
    every name the file defines, with the line that spells it and the lines of
    its construct."""

    def __init__(self, source, relative, anonymous=0):
        self.source = source
        self.source_lines = source.decode("utf-8", "replace").split("\n")
        self.found = []
        # unnamed structs, unions and enums are numbered through the file; a
        # part of the file that is parsed again starts at a number of its own
        self.anonymous = anonymous
        self.stem = hashlib.sha1(relative.encode("utf-8")).hexdigest()[:6]

    def text(self, node):
        return self.source[node.start_byte : node.end_byte].decode(
            "utf-8", "replace"
        )

    def tag(self, name, kind, at, until, scope, typeref=None, head=None):
        """A fact: `line` is the line that spells the name, `head` the first
        line of the construct, which for a function whose signature is split
        stands above the name line (the return type and the storage class, the
        signature's first line by links.definition-line); `head` equals `line`
        for everything else.
        """
        # a name that is one C identifier; e.g. `pci_walk_bus`, and not `struct
        # pci_dev`
        if not name or not re.match(r"^[A-Za-z_]\w*$", name):
            return
        scope_kind = None
        if scope:
            last = scope.split("::")[-1]
            scope_kind = (
                "struct"
                if last.startswith("__anon")
                else next(
                    (
                        f["kind"]
                        for f in self.found
                        if f["name"] == last
                        and f["kind"] in ("struct", "union", "enum")
                    ),
                    None,
                )
            )
        self.found.append(
            {
                "name": name,
                "kind": kind,
                "line": at,
                "head": head or at,
                "end": until,
                "scope": scope,
                "scopeKind": scope_kind,
                "typeref": typeref,
            }
        )

    def typeref_of(self, type_node):
        if type_node is None:
            return None
        if type_node.type in _SPECIFIERS:
            name = type_node.child_by_field_name("name")
            return (
                f"{type_node.type.split('_')[0]}:{self.text(name)}"
                if name is not None
                else None
            )
        if type_node.type in (
            "type_identifier",
            "primitive_type",
            "sized_type_specifier",
        ):
            return "typename:" + self.text(type_node)
        return None

    def macro(self, node, scope):
        named = node.child_by_field_name("name")
        if named is not None:
            self.tag(self.text(named), "macro", _line(node), _end(node), scope)

    def specifier(self, node, scope):
        """A struct, union or enum with a body, and what the body holds."""
        body = node.child_by_field_name("body")
        if body is None:
            return
        kind = node.type.split("_")[0]
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            name = self.text(name_node)
        else:
            self.anonymous += 1
            name = f"__anon{self.stem}{self.anonymous:02d}"
        self.tag(name, kind, _line(node), _end(node), scope)
        inner = f"{scope}::{name}" if scope else name
        for child in _body_members(body):
            if child.type in ("preproc_def", "preproc_function_def"):
                self.macro(child, None)
            elif kind == "enum":
                self.enumerator(child, inner)
            elif child.type == "field_declaration":
                self.field(child, inner)

    def enumerator(self, node, scope):
        if node.type != "enumerator":
            return
        named = node.child_by_field_name("name")
        if named is not None:
            self.tag(
                self.text(named), "enumerator", _line(node), _line(node), scope
            )

    def field(self, node, scope):
        """The members one field declaration names, after the struct, union
        or enum it defines in place."""
        field_type = node.child_by_field_name("type")
        if (
            field_type is not None
            and field_type.type in _SPECIFIERS
            and field_type.child_by_field_name("body") is not None
        ):
            self.specifier(field_type, scope)
        for decl in node.children_by_field_name("declarator"):
            named = _name_node(decl)
            if named is not None:
                self.tag(
                    self.text(named),
                    "member",
                    _line(named),
                    _line(named),
                    scope,
                    self.typeref_of(field_type),
                )

    def function_definition(self, node, scope, in_function):
        decl = node.child_by_field_name("declarator")
        named = _name_node(decl) if decl is not None else None
        if named is not None and not in_function:
            # the signature's first line by links.definition-line: specifier
            # lines above the name, never a macro invocation without a `;`
            # that tree-sitter folds into the function as its type
            # (INTERVAL_TREE_DEFINE)
            self.tag(
                self.text(named),
                "function",
                _line(named),
                _end(node),
                scope,
                head=max(
                    _line(node), head_of(self.source_lines, _line(named))
                ),
            )
        for child in node.children:
            self.walk(child, scope, True)

    def declaration(self, node, scope, in_function):
        """The prototypes and variables a file-scope declaration names, then
        the type it defines in place."""
        head = self.text(node).lstrip()
        if head.startswith(("static_assert", "_Static_assert")):
            return
        broken = any(child.type == "ERROR" for child in node.children)
        for decl in node.children_by_field_name("declarator"):
            inner = (
                decl.child_by_field_name("declarator")
                if decl.type == "init_declarator"
                else decl
            )
            named = _name_node(inner) if inner is not None else None
            if named is None or in_function:
                continue
            self.tag(
                self.text(named),
                "prototype" if _declares_function(inner) else "variable",
                _line(named),
                _line(named) if broken else _end(node),
                scope,
            )
        type_node = node.child_by_field_name("type")
        if type_node is not None:
            self.walk(type_node, scope, in_function)

    def type_definition(self, node, scope, in_function):
        type_node = node.child_by_field_name("type")
        if type_node is not None:
            self.walk(type_node, scope, in_function)
        for decl in node.children_by_field_name("declarator"):
            named = _name_node(decl)
            if named is not None:
                self.tag(
                    self.text(named),
                    "typedef",
                    _line(named),
                    _end(node),
                    scope,
                )

    def invoked_function(self, node, scope):
        """Whether the statement is a macro invocation that the block after
        it makes a function definition; the function is then recorded."""
        if node.parent is None:
            return False
        call = node.children[0] if node.children else None
        if call is None or call.type != "call_expression":
            return False
        siblings = node.parent.children
        i = siblings.index(node)
        body = siblings[i + 1] if i + 1 < len(siblings) else None
        if body is None or not (
            body.type == "compound_statement"
            or (
                body.type == "ERROR"
                and self.text(body).lstrip().startswith("{")
            )
        ):
            return False
        macro = call.child_by_field_name("function")
        if macro is None or macro.type != "identifier":
            return False
        self.tag(self.text(macro), "function", _line(macro), _end(body), scope)
        return True

    def error_functions(self, node, scope):
        """Inside an ERROR node, a name with its argument list and a block
        after them is a function."""
        children = node.children
        for i, child in enumerate(children):
            if (
                child.type == "identifier"
                and i + 1 < len(children)
                and children[i + 1].type == "argument_list"
            ):
                body = next(
                    (
                        c
                        for c in children[i + 2 :]
                        if c.type == "compound_statement"
                    ),
                    None,
                )
                if body is not None:
                    self.tag(
                        self.text(child),
                        "function",
                        _line(child),
                        _end(body),
                        scope,
                    )

    def walk(self, node, scope, in_function):
        kind = node.type
        if kind == "function_definition":
            self.function_definition(node, scope, in_function)
        elif kind == "declaration":
            self.declaration(node, scope, in_function)
        elif kind in _SPECIFIERS:
            self.specifier(node, scope)
        elif kind == "type_definition":
            self.type_definition(node, scope, in_function)
        elif kind in ("preproc_def", "preproc_function_def"):
            self.macro(node, scope)
        else:
            if kind == "expression_statement" and not in_function:
                if self.invoked_function(node, scope):
                    return
            elif kind == "ERROR" and not in_function:
                self.error_functions(node, scope)
            elif kind == "compound_statement":
                in_function = True
            walk = self.walk
            for child in node.children:
                walk(child, scope, in_function)

    def macros_by_text(self, root):
        """The text decides the macros: a `#define` line names its macro, which
        runs to the last line of its backslash continuation. tree-sitter-c
        stops reading a macro's body at a comment that more of the body
        follows, so it ends the macro there
        (include/linux/interval_tree_generic.h:28-183 at v7.3,
        INTERVAL_TREE_DEFINE, read as ending at line 36) or, where the comment
        stands inside a line, names the macro by a word of its body
        (include/drm/drm_atomic.h:948-956, for_each_oldnew_connector_in_state,
        read as a macro named old_connector_state); and it accepts no
        preprocessor definition inside an enumerator list or an initializer
        list, so such lines fall into an ERROR node
        (include/linux/pci.h:120-132 at v7.2, the bridge window macros inside
        the resource enum). A macro fact on a `#define` line that names another
        macro is dropped, a `#define` line outside a comment that no macro fact
        covers is a macro, and a macro ends no earlier than its continuation.
        """
        lines = self.source.split(b"\n")
        defined = {}
        for i, raw in enumerate(lines):
            match = _DEFINE_LINE.match(raw)
            if match is not None:
                defined[i + 1] = match.group(1).decode("utf-8", "replace")
        self.found = [
            f
            for f in self.found
            if f["kind"] != "macro"
            or defined.get(f["line"], f["name"]) == f["name"]
        ]
        tagged = {
            (f["name"], f["line"]): f
            for f in self.found
            if f["kind"] == "macro"
        }
        for number, name in defined.items():
            until = number - 1
            while until < len(lines) - 1 and lines[until].rstrip().endswith(
                b"\\"
            ):
                until += 1
            known = tagged.get((name, number))
            if known is not None:
                known["end"] = max(known["end"], until + 1)
                continue
            node = root.descendant_for_point_range(
                (number - 1, 0), (number - 1, 0)
            )
            if node is not None and node.type == "comment":
                continue
            self.tag(name, "macro", number, until + 1, None)


def _facts(parser, source, relative, part=None):
    """The facts of one source file, or of a part of it parsed again, which
    is not settled a second time."""
    source, root = _parse(parser, source)
    collector = _Collector(source, relative, part or 0)
    collector.walk(root, None, False)
    collector.macros_by_text(root)
    if part is None:
        _settle(
            collector.found,
            parser,
            source,
            collector.source_lines,
            relative,
        )
    return collector.found


def resolve_tree(explicit, skill_root):
    """(path or None, how, candidate): --tree, $KG_TREE, else the kernel
    checkout whose .claude directory holds the repository's checkout; the
    candidate is the path tried, or what was missing.
    """
    candidate, how = tree_default(skill_root, explicit)
    if (
        candidate
        and Path(candidate).is_dir()
        and Path(candidate, TREE_MARKER).exists()
    ):
        return candidate, how, candidate
    return (
        None,
        how,
        candidate or f"no .claude directory above {absolute(skill_root)}",
    )


def validate(tree, page):
    """The input problems of a page against a tree: one version, pinned at
    HEAD, cited files tracked and clean. Returns a list of problem texts."""
    problems = []
    versions = page.versions()
    if len(versions) > 1:
        problems.append(
            "the page pins several versions: "
            + ", ".join(f"{v} ({n})" for v, n in versions.most_common())
        )
        return problems
    version = page.version()
    if tree.git and version:
        pinned = git(
            tree.path,
            "rev-parse",
            "--verify",
            "--quiet",
            version + "^{commit}",
            ok=(0, 1),
        ).strip()
        if not COMMIT_ID.match(pinned or "x"):
            problems.append(
                f"the page pins {version} but the tree has no tag {version}"
            )
        elif pinned != tree.head:
            problems.append(
                f"the page pins {version} ({pinned[:12]}) but the tree is at"
                f" {tree.head[:12]}"
                + (f", tagged {tree.tag}" if tree.tag else ", not at any tag")
            )
    if tree.git:
        files = page.cited_files()
        if files:
            status = git(
                tree.path,
                "status",
                "--porcelain",
                "--untracked-files=no",
                "--",
                *files,
            )
            modified = sorted(
                line[3:].strip() for line in status.split("\n") if line.strip()
            )
            tracked = set(git(tree.path, "ls-files", "--", *files).split("\n"))
            untracked = sorted(
                f
                for f in files
                if f not in tracked
                and not any(t.startswith(f.rstrip("/") + "/") for t in tracked)
            )
            if modified:
                problems.append(
                    "the tree has uncommitted changes in files the page"
                    " cites: "
                    + ", ".join(modified[:6])
                    + (" and more" if len(modified) > 6 else "")
                )
            if untracked:
                problems.append(
                    "the page cites paths the commit does not track: "
                    + ", ".join(untracked[:6])
                    + (" and more" if len(untracked) > 6 else "")
                )
    return problems


def map_units(page, tree):
    """Map every unit onto its file: unit.mapped becomes [(page line, file
    line)] or unit.error the reason; returns {path: set of reproduced file
    lines}."""
    reproduced = {}
    for unit in page.units:
        unit.mapped, unit.error = None, None
        source = tree.lines(unit.path) if tree is not None else None
        if source is None:
            unit.error = f"{unit.path} cannot be read under the tree"
            continue
        if unit.line < 1:
            unit.error = "lines count from 1"
            continue
        pos = unit.line
        mapped = []
        elisions = {
            n: (dropped, resumes) for n, dropped, resumes in unit.elisions
        }
        for n, text in unit.body:
            if n in elisions:
                dropped, resumes = elisions[n]
                if dropped is None:
                    unit.error = f"malformed elision at page line {n}"
                    break
                if resumes - pos != dropped:
                    unit.error = (
                        f"the elision at page line {n} says {dropped} lines to"
                        f" :{resumes}, but the excerpt stands at line {pos}:"
                        f" write `... {page.profile.comment_open}"
                        f" {resumes - pos} lines, to :{resumes}"
                        f" {page.profile.comment_close}`"
                        if resumes > pos
                        else (
                            f"the elision at page line {n} resumes at"
                            f" :{resumes}, before line {pos}"
                        )
                    )
                    break
                pos = resumes
                continue
            if pos > len(source):
                unit.error = (
                    f"page line {n} runs past the end of {unit.path}"
                    f" ({len(source)} lines)"
                )
                break
            if source[pos - 1] != text:
                unit.error = (
                    f"page line {n} differs from {unit.path}:{pos}: page"
                    f" {text[:60]!r}, file {source[pos - 1][:60]!r}"
                )
                break
            mapped.append((n, pos))
            pos += 1
        if unit.error is None:
            unit.mapped = mapped
            reproduced.setdefault(unit.path, set()).update(
                f for _p, f in mapped
            )
    return reproduced


def years_between(later_ts, earlier_ts):
    return (later_ts - earlier_ts) / (365.25 * 86400)


def date_of(ts):
    return (
        datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)
        .date()
        .isoformat()
    )
