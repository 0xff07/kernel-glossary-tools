"""The page model of guidelines/page/page-model.md, read once by every checker
and view.

Every definition a checker relies on is implemented here as page-model.md
states it: the profile constants, fences and units, headings and regions, line
classes, blocks, sentences and words, spans and links, the catalog, legends and
marks, the prose view. Nothing here reads the tree, the campaign spec or any
notes file."""

import collections
import hashlib
from pathlib import Path
import re

from tools.checkout import absolute

ROOT = str(absolute(__file__).parents[2])
PAGE_MODEL = Path("guidelines", "page", "page-model.md")
PROFILE_KEYS = (
    "source_lang",
    "comment",
    "source_suffixes",
    "cited_suffixes",
    "permalink",
    "commit_permalink",
    "sections",
    "catalog_sections",
    "reference_sections",
    "claims_sections",
    "register_headers",
    "config_option",
    "upstream_trailer",
    "example_consumer_paths",
    "caution",
)


class ModelError(Exception):
    """guidelines/page/page-model.md lacks something the tools read, or says it
    in a form they cannot read."""


def profile_values(skill=ROOT):
    """The `yaml kg:profile` fence of guidelines/page/page-model.md, as a
    mapping."""
    import yaml

    try:
        text = Path(skill, PAGE_MODEL).read_text(encoding="utf-8")
    except OSError as error:
        raise ModelError(f"{PAGE_MODEL}: {error}") from error
    # the body of the profile fence of page-model.md: from the line that opens
    # ```yaml kg:profile to the next line that is ``` alone, group 1 the YAML
    # between them; e.g. "```yaml kg:profile\nsource_lang: c\n```" gives
    # "source_lang: c\n"
    match = re.search(
        r"^```yaml kg:profile[ \t]*\n(.*?)^```[ \t]*$", text, re.M | re.S
    )
    if not match:
        raise ModelError(f"{PAGE_MODEL} carries no `yaml kg:profile` fence")
    values = yaml.safe_load(match.group(1)) or {}
    if not isinstance(values, dict):
        raise ModelError(f"{PAGE_MODEL}: the profile fence is not a mapping")
    missing = [key for key in PROFILE_KEYS if key not in values]
    if missing:
        raise ModelError(
            f"the profile of {PAGE_MODEL} lacks " + ", ".join(missing)
        )
    return values


class Profile:
    """The constants of page-model.md [profile] with the patterns derived from
    them."""

    def __init__(self, values):
        for key, value in values.items():
            setattr(self, key, value)
        self.caution_lines = self.caution.rstrip("\n").split("\n")
        self.comment_open, self.comment_close = self.comment
        suffixes = list(self.source_suffixes) + list(self.cited_suffixes)
        names = "|".join(re.escape(s) for s in suffixes)
        # the location forms of page-model.md [spans], which the prose view
        # masks
        # a location inside a sentence: a path with a slash, or a file named by
        # one of the profile's suffixes, then `:line` or `:line-line`; e.g.
        # `drivers/pci/probe.c:120-134` and `pci.h:45`, and not the `3:0` of
        # `bits 3:0`
        self.location_mask = re.compile(
            r"(?<![\w/.-])(?:[\w.-]+(?:/[\w.-]+)+|[\w.-]*(?:"
            + names
            + r")):\d+(?:-\d+)?(?!\w)"
        )
        file_part = r"(?:[\w.-]+/)*[\w.-]+"
        # a span that is a location and nothing else: group 1 the file, 2 the
        # line, 3 the last line of a range; e.g. `mm/memory.c:6621-6630` gives
        # mm/memory.c, 6621 and 6630
        self.location_re = re.compile(
            r"^(" + file_part + r"):(\d+)(?:-(\d+))?$"
        )
        # a span that is a file path and nothing else; e.g.
        # `include/linux/pci.h`
        self.file_re = re.compile(r"^(" + file_part + r")$")
        # a span that names a Kconfig option, the profile's config_option
        # anchored at both ends; e.g. `CONFIG_PCIEAER`, group 1 PCIEAER
        self.config_re = re.compile("^" + self.config_option + "$")
        # a cited URL, the profile's permalink template as a pattern
        # (_permalink_pattern); e.g.
        # https://elixir.bootlin.com/linux/v7.3/source/mm/memory.c#L6621 gives
        # version v7.3, path mm/memory.c and line 6621
        self.permalink_re = re.compile(self._permalink_pattern(self.permalink))
        head, _sep, tail = self.commit_permalink.partition("{commit}")
        # a commit's page, the profile's commit_permalink with a full id of 40
        # hex digits in the place of {commit}; e.g. the URL that ends
        # `/commit/?id=` and c03c1a14507dfaf8b856c2608f9ac216021fc222
        self.commit_permalink_re = re.compile(
            "^"
            + re.escape(head)
            + r"(?P<commit>[0-9a-f]{40})"
            + re.escape(tail)
            + "$"
        )
        open_, close = re.escape(self.comment_open), re.escape(
            self.comment_close
        )
        # the provenance line of an excerpt, a comment that holds `path:line`
        # and may hold text after it; e.g. `/* mm/memory.c:6621 */` gives
        # mm/memory.c and 6621, and group 3 is the text between the line number
        # and the closing delimiter
        self.provenance_re = re.compile(
            r"^"
            + open_
            + r"\s*([\w./-]+):(\d+)\b((?:(?!"
            + close
            + r").)*)"
            + close
            + r"\s*$"
        )
        # the elision line of an excerpt, `...` and a comment that counts the
        # lines left out and names the line the excerpt resumes at; e.g. `...
        # /* 12 lines, to :6640 */` gives 12 and 6640
        self.elision_re = re.compile(
            r"^\.\.\.\s*"
            + open_
            + r"\s*(\d+) lines?, to :(\d+)\s*"
            + close
            + r"\s*$"
        )

    @staticmethod
    def _permalink_pattern(template):
        out = []
        # cuts the permalink template at its placeholders and keeps them as
        # pieces: `#L{line}`, `{version}`, `{path}`, `{line}`; e.g.
        # `https://x/{version}/source/{path}#L{line}` gives `https://x/`,
        # `{version}`, `/source/`, `{path}`, an empty piece and `#L{line}`
        for piece in re.split(
            r"(#L\{line\}|\{version\}|\{path\}|\{line\})", template
        ):
            if piece == "{version}":
                out.append(r"(?P<version>[^/\s)#?]+)")
            elif piece == "{path}":
                out.append(r"(?P<path>[^#)\s?]+)(?:\?[^#)\s]*)?")
            elif piece == "#L{line}":
                out.append(r"(?:#L(?P<line>\d+))?")
            elif piece == "{line}":
                out.append(r"(?P<line>\d+)")
            else:
                out.append(re.escape(piece))
        return "".join(out)

    def has_suffix(self, name, suffixes=None):
        for suffix in (
            suffixes
            if suffixes is not None
            else list(self.source_suffixes) + list(self.cited_suffixes)
        ):
            if name.endswith(suffix):
                return True
        return False

    def is_source(self, path):
        return self.has_suffix(path, self.source_suffixes)

    def commit_url(self, full):
        return self.commit_permalink.replace("{commit}", full)

    def cited_url(self, url):
        """(path, version, line or None) of a cited URL, or None."""
        match = self.permalink_re.search(url)
        if not match:
            return None
        return (
            match.group("path"),
            match.group("version"),
            int(match.group("line")) if match.group("line") else None,
        )

    def location(self, text):
        """(file, first, last) of a location form, or None."""
        match = self.location_re.match(text.strip())
        if not match:
            return None
        file = match.group(1)
        base = file.rsplit("/", 1)[-1]
        if not (
            "/" in file
            or self.has_suffix(base)
            or base in ("Kconfig", "Makefile")
        ):
            return None
        first = int(match.group(2))
        last = int(match.group(3)) if match.group(3) else first
        return file, first, last

    def is_file_text(self, text):
        match = self.file_re.match(text.strip())
        if not match:
            return False
        base = text.strip().rsplit("/", 1)[-1]
        return (
            "/" in text.strip()
            or self.has_suffix(base)
            or base in ("Kconfig", "Makefile")
        )


_PROFILES = {}
CONFIG = (
    None  # the profile loaded last, whose location forms the prose view masks
)


def profile(skill=ROOT):
    global CONFIG
    skill = str(absolute(skill))
    if skill not in _PROFILES:
        _PROFILES[skill] = Profile(profile_values(skill))
    CONFIG = _PROFILES[skill]
    return CONFIG


# ---- constants of the model
# --------------------------------------------------------------------

MARK_ALPHABETS = [
    ("circled digits", "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"),
    ("sans-serif circled digits", "➊➋➌➍➎➏➐➑➒➓"),
    ("negative circled digits", "❶❷❸❹❺❻❼❽❾❿⓫⓬⓭⓮⓯⓰⓱⓲⓳⓴"),
    ("circled capitals", "ⒶⒷⒸⒹⒺⒻⒼⒽⒾⒿⓀⓁⓂⓃⓄⓅⓆⓇⓈⓉⓊⓋⓌⓍⓎⓏ"),
    ("circled small letters", "ⓐⓑⓒⓓⓔⓕⓖⓗⓘⓙⓚⓛⓜⓝⓞⓟⓠⓡⓢⓣⓤⓥⓦⓧⓨⓩ"),
    ("double-circled digits", "⓵⓶⓷⓸⓹⓺⓻⓼⓽⓾"),
    (
        "negative squared capitals",
        "".join(chr(n) for n in range(0x1F170, 0x1F18A)),
    ),
    ("parenthesized digits", "".join(chr(n) for n in range(0x2474, 0x2488))),
    (
        "parenthesized small letters",
        "".join(chr(n) for n in range(0x249C, 0x24B6)),
    ),
    ("guillemet capitals", tuple("«" + chr(n) + "»" for n in range(65, 91))),
    ("at capitals", tuple("@" + chr(n) for n in range(65, 91))),
]
FIGURE_FAMILIES = (
    "circled digits",
    "sans-serif circled digits",
    "guillemet digits",
    "guillemet capitals",
    "at digits",
    "at capitals",
)
FIGURE_CAPACITY = dict(zip(FIGURE_FAMILIES, (10, 10, None, 26, None, 26)))
RESERVED_MARKS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳➊➋➌➍➎➏➐➑➒➓"
MARKS = "".join(
    s for _name, symbols in MARK_ALPHABETS for s in symbols if len(s) == 1
)
TOKEN_LEFT, TOKEN_RIGHT = r"(?<![\w@«»])", r"(?![\w@«»])"
AT_LEFT, AT_RIGHT = r"(?<![\w@«».+%/])", r"(?![\w@«»/]|\.\w)"
MULTI_MARK = (
    TOKEN_LEFT
    + r"«(?:[1-9][0-9]*|[A-Z])»"
    + TOKEN_RIGHT
    + "|"
    + AT_LEFT
    + r"@(?:[1-9][0-9]*|[A-Z])"
    + AT_RIGHT
)
# a figure mark standing as a token of its own: one of the single characters of
# MARKS (①, ➊, ⒜ and the like) or `«3»`, `«B»`, `@3`, `@B`; e.g. the `«2»` of
# `│ 7  table «2»├─▶`, and not the `@2` of `x@2y`
MARK = re.compile("[" + re.escape(MARKS) + "]|" + MULTI_MARK)
# what was perhaps meant as a mark, wider than MARK: a single-character mark,
# any `«...»` token or any `@word`; e.g. `«12a»` and `@note`, which MARK
# refuses
MARK_CANDIDATE = re.compile(
    "["
    + re.escape(MARKS)
    + "]|"
    + TOKEN_LEFT
    + r"«[^\s«»]+»"
    + TOKEN_RIGHT
    + "|"
    + AT_LEFT
    + r"@[A-Za-z0-9_]+"
    + AT_RIGHT
)
# a drawing character: box drawing and blocks (U+2500 to U+259F), arrows
# (U+2190 to U+21FF) or geometric shapes (U+25A0 to U+25FF); e.g. `├`, `→`, `▶`
DRAWING = re.compile("[─-▟←-⇿■-◿]")
# a Markdown link `[text](url)` on one line, the text allowed one level of
# brackets: group 1 the text, group 2 the URL; e.g.
# "[`pci_dev`](https://x/pci.h#L5)", and "[a [b] c](u)" is one link
LINK = re.compile(r"\[((?:[^\[\]\n]|\[[^\[\]\n]*\])*)\]\(([^)\n]*)\)")
# a code span on one line; e.g. "`pci_dev`"
CODE_SPAN = re.compile(r"`[^`\n]+`")
# a run in double quotes on one line; e.g. `"PCI ECAM"`
QUOTED = re.compile(r'"[^"\n]*"')
# `::` or a pair of numbers around a colon, which is no location; e.g. the
# `3:0` of `bits 3:0` and the `::` of `a::b`
COLON_PAIR = re.compile(r"::|\d+:\d+")
# page-model.md: `- `, `* ` or digits and `. `, a space
# the opening of a list item; e.g. `- text`, `  * text`, `12. text`
ITEM = re.compile(r"^\s*(?:[-*] |\d+\. )")
# an ATX heading: group 1 the run of `#`, whose length is the level, group 2
# the title without the spaces around it; e.g. `### Kconfig assumptions` gives
# `###` and `Kconfig assumptions`
HEADING = re.compile(r"^(#{1,6})\s*(.*?)\s*$")
# the whitespace that follows a sentence end: after `.`, `!` or `?`, or after a
# period and a closing quote; e.g. the space of `ends. Next` and of `said "no."
# Then`
SENTENCE_END = re.compile(r"(?:(?<=[.!?])|(?<=\.[\"'”]))\s+")
# a traced catalog key, `'\<name\>':'path'`; e.g.
# `'\<pcie_do_recovery\>':'drivers/pci/pcie/err.c'` gives key pcie_do_recovery
# and path drivers/pci/pcie/err.c
CATALOG_KEY = re.compile(r"^'\\<(?P<key>[^\\]+)\\>':'(?P<path>[^']*)'$")
# a bare catalog key, a name in single quotes and no path; e.g.
# `'pci_channel_io_frozen'`
BARE_KEY = re.compile(r"^'(?P<key>[^'\\]+)'$")
# a catalog entry line, `- [`key`](url)` with an optional `: description`:
# group 1 the key in either form, 2 the URL, 3 the description; e.g. "-
# [`'pci_channel_io_frozen'`](https://x/pci.h#L213): the frozen state"
CATALOG_ENTRY = re.compile(
    r"^- \[`('\\<[^\\]+\\>':'[^']*'|'[^'\\]+')`\]\(([^)]+)\)(?::\s*(.*))?$"
)
# a member key `A.B`, two identifiers around one dot; e.g.
# `pci_error_handlers.error_detected`
MEMBER_KEY = re.compile(r"^([A-Za-z_]\w*)\.([A-Za-z_]\w*)$")
# a C identifier; e.g. `pci_walk_bridge`, `__free_pages`
IDENTIFIER = re.compile(r"[A-Za-z_]\w*")
TAGS = ("struct", "enum", "union")
# the separator row of a Markdown table; e.g. `|---|:---:|---|`
TABLE_SEPARATOR = re.compile(r"^\|(?:\s*:?-{3,}:?\s*\|)+\s*$")
# a `|` no backslash escapes, a cell boundary of a table row; e.g. the pipe of
# `a | b` and not the one of `a \| b`
UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")
# the opening of a recap paragraph; e.g. `So far, the page has shown the
# probe.`
RECAP = re.compile(r"^So far,")

Fence = collections.namedtuple("Fence", "start end info kind body units")
Item = collections.namedtuple("Item", "kind line end size text")
Section = collections.namedtuple("Section", "name start end region")
Link = collections.namedtuple(
    "Link", "line col text url backticked cls name tag location cited"
)
Legend = collections.namedtuple(
    "Legend", "line mark name file source_line phrase"
)
Table = collections.namedtuple("Table", "line header rows")
Series = collections.namedtuple("Series", "line kind marks")


class Unit:
    """One excerpt unit: its fence, provenance path and line, the page line of
    the provenance line, its body as [(page line, text)] and its elisions as
    [(page line, dropped, resumes)].
    """

    def __init__(self, fence, path, line, start):
        self.fence, self.path, self.line, self.start = fence, path, line, start
        self.body = []
        self.elisions = []
        self.mapped = None  # [(page line, file line)] once the tree mapped it
        self.error = None  # why the mapping failed

    @property
    def reproduced(self):
        return [
            (n, t) for n, t in self.body if (n, t) not in self._elision_lines
        ]

    @property
    def _elision_lines(self):
        return {
            (n, self.fence.body[n - self.fence.start - 1])
            for n, _d, _r in self.elisions
        }

    @property
    def label(self):
        return f"{self.path}:{self.line}"

    @property
    def file_lines(self):
        return {f for _p, f in self.mapped or []}


class SpanSummary:
    def __init__(self, text):
        self.text = text
        self.region = "catalog"
        self.linked = 0
        self.bare = 0
        self.bare_at = []
        self.urls = []


def mark_alphabet(mark):
    # a guillemet mark that holds a number; e.g. `«12»`
    if re.fullmatch(r"«[1-9][0-9]*»", mark):
        return "guillemet digits"
    # an at mark that holds a number; e.g. `@3`
    if re.fullmatch(r"@[1-9][0-9]*", mark):
        return "at digits"
    return next(
        (
            name
            for name, symbols in MARK_ALPHABETS
            if mark in symbols
            and (not isinstance(symbols, str) or len(mark) == 1)
        ),
        None,
    )


def mark_index(mark):
    family = mark_alphabet(mark)
    if family in ("guillemet digits", "at digits"):
        try:
            return int(
                mark[1:-1] if family == "guillemet digits" else mark[1:]
            )
        except ValueError:
            return 0
    for _name, symbols in MARK_ALPHABETS:
        if mark in symbols and (
            not isinstance(symbols, str) or len(mark) == 1
        ):
            return symbols.index(mark) + 1
    return 0


def figure_mark(mark):
    family = mark_alphabet(mark)
    if family not in FIGURE_CAPACITY:
        return False
    index, capacity = mark_index(mark), FIGURE_CAPACITY[family]
    return index > 0 and (capacity is None or index <= capacity)


def mark_occurrences(text, marks=None):
    """Complete marks and their offsets in visible text; a link's URL cannot
    supply one."""
    visible = LINK.sub(
        lambda m: " "
        + m.group(1)
        + " " * (len(m.group(0)) - len(m.group(1)) - 1),
        text,
    )
    if marks is None:
        return [(m.group(0), m.start()) for m in MARK.finditer(visible)]
    found = []
    for mark in set(marks):
        pattern = re.escape(mark)
        if len(mark) > 1 or mark.isascii():
            pattern = (
                (AT_LEFT if mark.startswith("@") else TOKEN_LEFT)
                + pattern
                + (AT_RIGHT if mark.startswith("@") else TOKEN_RIGHT)
            )
        # every place where this one mark stands in the visible text, a
        # multi-character or ASCII mark only as a token of its own; e.g. the
        # mark `@2` is found in `(@2)` and not in `x@2y`
        found.extend((mark, m.start()) for m in re.finditer(pattern, visible))
    return sorted(found, key=lambda item: item[1])


# ---- text helpers (page-model.md, words and sentences)
# -----------------------------------------


def prose_text(text):
    """Links reduced to their text, code spans to the token X."""
    return CODE_SPAN.sub("X", LINK.sub(r"\1", text))


def readable(text):
    """Links reduced to their text, backticks removed: the form a quote
    takes."""
    return LINK.sub(r"\1", text).replace("`", "")


def sentences_of(text):
    # a piece counts as a sentence when it holds a word character; e.g. a piece
    # that is `--` or `...` alone is dropped
    return [
        s
        for s in SENTENCE_END.split(prose_text(text).strip())
        if re.search(r"\w", s)
    ]


def is_word(token):
    stripped = MARK.sub("", token)
    # a token is a word when, its marks taken out, it holds a letter, a digit
    # or an underscore; e.g. `x86-64` and `_OSC` are words, `--` and `«3»` are
    # not
    return (
        re.search(r"[^\W_]", stripped) is not None
        or re.search(r"\w", stripped) is not None
    )


def word_count(text):
    return sum(1 for token in prose_text(text).split() if is_word(token))


def sentence_words(sentence):
    return sum(1 for token in sentence.split() if is_word(token))


def _is_location_link(text, url):
    bare = text.strip().strip("`").lstrip("&*")
    if CONFIG is None:
        return False
    if CONFIG.location(bare):
        return True
    # a link text that has the shape of a location whatever its file is called:
    # group 1 the file, 2 the line, 3 the end of a range; e.g.
    # `Kconfig.debug:12` and `arch/x86/pci/acpi.c:40-52`
    form = re.match(r"^([\w./-]+):(\d+)(?:-(\d+))?$", bare)
    cited = CONFIG.cited_url(url) if form else None
    return bool(cited) and (
        cited[0] == form.group(1) or cited[0].endswith("/" + form.group(1))
    )


def masked_same_length(text, spans_visible=False):
    """The line with the prose view's masks applied in place, every masked run
    replaced by `§` and filler, so positions in the result are positions in the
    line."""

    def fill(match, keep=None):
        found = match.group(0)
        if keep is not None:
            return keep + " " * (len(found) - len(keep))
        return "§" + " " * (len(found) - 1)

    def reduce(match):
        if _is_location_link(match.group(1), match.group(2)):
            return "§" + " " * (len(match.group(0)) - 1)
        return (
            " "
            + match.group(1)
            + " " * (len(match.group(0)) - len(match.group(1)) - 1)
        )

    out = LINK.sub(reduce, text)
    if not spans_visible:
        out = CODE_SPAN.sub(fill, out)
    out = QUOTED.sub(fill, out)
    if CONFIG is not None:
        out = CONFIG.location_mask.sub(fill, out)
    out = COLON_PAIR.sub(fill, out)
    return out


def sentence_spans(masked):
    """(start, end) of each sentence of a masked line."""
    spans, start = [], 0
    for end in SENTENCE_END.finditer(masked):
        # a stretch between two sentence ends is a sentence only when it holds
        # a word character; e.g. a stretch of spaces or of `...` is none
        if re.search(r"\w", masked[start : end.start()]):
            spans.append((start, end.start()))
        start = end.end()
    # the same test for what follows the last sentence end
    if re.search(r"\w", masked[start:]):
        spans.append((start, len(masked)))
    return spans


def readable_slice(line, start, end):
    """readable() of line[start:end], the slice widened to whole links."""
    for match in LINK.finditer(line):
        if match.start() < start < match.end():
            start = match.start()
        if match.start() < end < match.end():
            end = match.end()
    return readable(line[start:end])


def readable_sentences(line):
    masked = masked_same_length(line, spans_visible=True)
    # every code span, replaced by an X and spaces of the same length so that
    # the columns stay; e.g. "`pci_dev`" becomes an X and eight spaces
    masked = re.sub(
        r"`[^`\n]+`", lambda m: "X" + " " * (len(m.group(0)) - 1), masked
    )
    return [
        readable_slice(line, s, e).strip() for s, e in sentence_spans(masked)
    ]


def first_sentence(line):
    found = readable_sentences(line)
    return found[0] if found else readable(line).strip()


def last_sentence(line):
    found = readable_sentences(line)
    return found[-1] if found else readable(line).strip()


def symbol_name(text):
    """The name a link text or catalog key names (page-model.md, spans)."""
    text = text.strip()
    if "(" in text:
        before = text[: text.index("(")]
        found = IDENTIFIER.findall(before)
        return found[-1] if found else ""
    words = text.split()
    while words:
        word = words[-1].strip("*&")
        # an array suffix at the end of the last word, cut off; e.g.
        # `tmu_rates[]` gives tmu_rates and `regs[4]` gives regs
        word = re.sub(r"\[[^\]]*\]$", "", word)
        if word:
            return word
        words.pop()
    return ""


C_KEYWORDS = frozenset(
    """auto break case char const continue default do double else enum extern
    float for goto if inline int long register restrict return short signed
    sizeof static struct switch typedef union unsigned void volatile while
    _Alignas _Alignof _Atomic _Bool _Complex _Generic _Imaginary _Noreturn
    _Static_assert _Thread_local alignof typeof __typeof__ asm
    defined""".split()
)


def scope_name(text):
    """The name a scope text gives, or None (page-model.md, scope names)."""
    text = " ".join(text.split())
    # a tagged type and nothing else, group 1 its name; e.g. `struct pci_dev`
    # gives pci_dev
    tag = re.fullmatch(r"(?:struct|enum|union) ([A-Za-z_]\w*)", text)
    if tag:
        return tag.group(1)
    # the identifier the text opens with; e.g. tb_port_enable of
    # `tb_port_enable(port)`, and none for `-EINVAL`
    head = re.match(r"[A-Za-z_]\w*", text)
    if not head:
        return None
    name, rest = head.group(0), text[head.end() :].lstrip()
    if not rest:
        return name
    if rest[0] == "(":
        depth = 0
        for at, char in enumerate(rest):
            depth += {"(": 1, ")": -1}.get(char, 0)
            if depth == 0:
                return (
                    name
                    if at == len(rest) - 1 and name not in C_KEYWORDS
                    else None
                )
        return None
    # what follows the name is one bracket pair, so the text names an array;
    # e.g. the `[MAX_GROUPS + 1]` of `groups[MAX_GROUPS + 1]`
    return name if re.fullmatch(r"\[[^\[\]]*\]", rest) else None


def scope_names_of(text):
    """The names the backticked texts of a scope fence give; a text that gives
    none is kept as written."""
    names = []
    # every backticked text of the scope, without its backticks; e.g. "`struct
    # pci_dev` and `pci_walk_bridge`" gives `struct pci_dev` and
    # `pci_walk_bridge`
    for span in re.findall(r"`([^`]+)`", text):
        name = scope_name(span) or span.strip()
        if name and name not in names:
            names.append(name)
    return names


def symbol_tag(text):
    words = text.strip().split()
    return words[0] if len(words) == 2 and words[0] in TAGS else None


def split_cells(line):
    cells = UNESCAPED_PIPE.split(line.strip())
    if cells and not cells[0].strip():
        cells = cells[1:]
    if cells and not cells[-1].strip():
        cells = cells[:-1]
    return [c.strip() for c in cells]


# ---- the page
# -----------------------------------------------------------------------------


class Page:
    def __init__(self, text, path="page.md", skill=ROOT, profile_=None):
        if not isinstance(text, str):
            raise ValueError("page must be UTF-8 text")
        self.path = path
        self.profile = profile_ or profile(skill)
        self.config = self.profile
        self.digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        self.text = text
        self.lines = text.split("\n")
        if self.lines and self.lines[-1] == "":
            self.lines.pop()
        self.n = len(self.lines)
        self._parse_fences()
        self._parse_headings()
        self._classify_lines()
        self._parse_links()
        self._parse_catalog()
        self._parse_tables()
        self._parse_figures()
        self._parse_subsections()

    @classmethod
    def read(cls, path, skill=ROOT):
        raw = Path(path).read_bytes()
        page = cls(raw.decode("utf-8"), str(absolute(path)), skill)
        page.digest = hashlib.sha256(raw).hexdigest()
        return page

    # ---- fences and units ----

    def _parse_fences(self):
        self.fences, self.units, self.problems = [], [], []
        self._fence_of = [None] * (self.n + 1)
        i = 0
        while i < self.n:
            if not self.lines[i].startswith("```"):
                i += 1
                continue
            j = i + 1
            while j < self.n and not self.lines[j].startswith("```"):
                j += 1
            info = self.lines[i][3:].strip()
            body = self.lines[i + 1 : j]
            if j >= self.n:
                self.problems.append(
                    {
                        "line": i + 1,
                        "quote": self.lines[i],
                        "message": "Unclosed fence.",
                        "code": "unclosed",
                    }
                )
            # a closing fence line is backticks and spaces alone; e.g. "```"
            # closes a fence and "``` c" does not
            elif not re.fullmatch(r"`{3,} *", self.lines[j]):
                self.problems.append(
                    {
                        "line": j + 1,
                        "quote": self.lines[j].strip(),
                        "message": (
                            "A fence's closing line holds text after its"
                            " backticks; a Markdown renderer keeps the fence"
                            " open past it."
                        ),
                        "code": "malformed-close",
                    }
                )
            if info == self.profile.source_lang:
                kind = "source"
            elif any(DRAWING.search(line) for line in body):
                kind = "figure"
            else:
                kind = "quotation"
            fence = Fence(i + 1, min(j + 1, self.n), info, kind, body, [])
            for k in range(fence.start, fence.end + 1):
                self._fence_of[k] = fence
            if kind == "source":
                self._units_of(fence)
            self.fences.append(fence)
            i = j + 1

    def _units_of(self, fence):
        current = None
        for k, text in enumerate(fence.body):
            n = fence.start + 1 + k
            match = self.profile.provenance_re.match(text.strip())
            if match:
                current = Unit(fence, match.group(1), int(match.group(2)), n)
                fence.units.append(current)
                self.units.append(current)
                continue
            if current is None:
                continue
            elision = self.profile.elision_re.match(text.strip())
            if elision:
                current.elisions.append(
                    (n, int(elision.group(1)), int(elision.group(2)))
                )
            elif text.strip().startswith("..."):
                current.elisions.append((n, None, None))
            current.body.append((n, text))

    def fence_at(self, n):
        return self._fence_of[n] if 0 < n <= self.n else None

    @property
    def source_fences(self):
        return [f for f in self.fences if f.kind == "source"]

    @property
    def figures(self):
        return [f for f in self.fences if f.kind == "figure"]

    @property
    def quotations(self):
        return [f for f in self.fences if f.kind == "quotation"]

    def excerpted_code(self):
        return "\n".join(line for f in self.source_fences for line in f.body)

    def require_valid(self):
        if self.problems:
            raise ValueError(
                "page fence structure is invalid at line"
                f" {self.problems[0]['line']}"
            )

    # ---- headings, sections, regions ----

    def _parse_headings(self):
        self.headings = []
        for n, line in enumerate(self.lines, 1):
            if self.fence_at(n) is None and line.startswith("#"):
                match = HEADING.match(line)
                self.headings.append((n, len(match.group(1)), match.group(2)))
        h2 = [(n, text) for n, level, text in self.headings if level == 2]
        self.sections = []
        for k, (n, name) in enumerate(h2):
            end = h2[k + 1][0] - 1 if k + 1 < len(h2) else self.n
            self.sections.append(
                Section(name, n, end, self.region_of_name(name))
            )
        self.h2_names = [s.name for s in self.sections]
        first = h2[0][0] if h2 else self.n + 1
        self.lead = Section("lead", 2, first - 1, "prose")

    def region_of_name(self, name):
        if name in self.profile.catalog_sections:
            return "catalog"
        if name in self.profile.reference_sections:
            return "reference"
        if name in self.profile.claims_sections:
            return "claims"
        return "prose"

    def section(self, name):
        return next((s for s in self.sections if s.name == name), None)

    def section_of(self, n):
        for s in self.sections:
            if s.start <= n <= s.end:
                return s
        return self.lead

    @property
    def reference_section(self):
        return next(
            (s for s in self.sections if s.region == "reference"), None
        )

    # ---- line classes ----

    def _classify_lines(self):
        self.cls = [None] * (self.n + 1)
        self.region = [None] * (self.n + 1)
        for n, line in enumerate(self.lines, 1):
            self.region[n] = self.section_of(n).region
            if self.fence_at(n) is not None:
                self.cls[n] = "fence"
            elif not line.strip():
                self.cls[n] = "blank"
            elif line.startswith("#"):
                self.cls[n] = "heading"
            elif line.startswith(">"):
                self.cls[n] = "blockquote"
            elif line.startswith("|"):
                self.cls[n] = "table"
            elif ITEM.match(line):
                self.cls[n] = "list"
            elif line.startswith(("    ", "\t")):
                self.cls[n] = "indented"
            else:
                self.cls[n] = "prose"

    def class_of(self, n):
        return self.cls[n] if 0 < n <= self.n else "blank"

    def prose_lines(self, regions=("prose", "reference")):
        return [
            n
            for n in range(1, self.n + 1)
            if self.cls[n] == "prose" and self.region[n] in regions
        ]

    def prose_line_above(self, n):
        k = n - 1
        while k >= 1 and self.cls[k] == "blank":
            k -= 1
        return k if k >= 1 and self.cls[k] == "prose" else None

    def intro_lines(self, n):
        """The introduction of a fence at line n: the run of prose lines
        directly above it, back to the previous heading, fence, table, list or
        blockquote, blank lines skipped.
        """
        out = []
        k = n - 1
        while k >= 1:
            cls = self.cls[k]
            if cls == "blank":
                k -= 1
                continue
            if cls != "prose":
                break
            out.append(k)
            k -= 1
        return list(reversed(out))

    def prose_line_below(self, n):
        k = n + 1
        while k <= self.n and self.cls[k] == "blank":
            k += 1
        return k if k <= self.n and self.cls[k] == "prose" else None

    # ---- blocks ----

    def items_of(self, start, end):
        out = []
        n = start
        while n <= end:
            cls = self.cls[n]
            line = self.lines[n - 1]
            if cls == "fence":
                fence = self.fence_at(n)
                kind = {"source": "C", "figure": "D", "quotation": "Q"}[
                    fence.kind
                ]
                size = (
                    sum(len(u.reproduced) for u in fence.units)
                    if fence.kind == "source"
                    else sum(1 for t in fence.body if t.strip())
                )
                text = (
                    fence.units[0].label
                    if fence.units
                    else (
                        next((t.strip() for t in fence.body if t.strip()), "")
                        if fence.kind != "source"
                        else "```" + fence.info
                    )
                )
                out.append(Item(kind, n, fence.end, size, text))
                n = fence.end + 1
            elif cls == "table":
                j = n
                while j + 1 <= end and self.cls[j + 1] == "table":
                    j += 1
                out.append(Item("T", n, j, j - n + 1, line.strip()))
                n = j + 1
            elif cls == "list":
                j = n
                while j + 1 <= end and self.cls[j + 1] in ("list", "indented"):
                    j += 1
                items = sum(
                    1 for k in range(n, j + 1) if self.cls[k] == "list"
                )
                out.append(Item("L", n, j, items, line.strip()))
                n = j + 1
            elif cls == "heading" and line.startswith("####"):
                out.append(
                    Item(
                        "H",
                        n,
                        n,
                        word_count(HEADING.match(line).group(2)),
                        HEADING.match(line).group(2),
                    )
                )
                n += 1
            elif cls == "prose":
                out.append(Item("P", n, n, word_count(line), line))
                n += 1
            else:
                n += 1
        return out

    def _parse_subsections(self):
        self.subsections = []
        self.preamble_items = []
        details = self.section("DETAILS")
        if details is None:
            return
        starts = [
            (n, text)
            for n, level, text in self.headings
            if level == 3 and details.start < n <= details.end
        ]
        first = starts[0][0] if starts else details.end + 1
        self.preamble_items = self.items_of(details.start + 1, first - 1)
        for k, (n, title) in enumerate(starts):
            end = starts[k + 1][0] - 1 if k + 1 < len(starts) else details.end
            items = self.items_of(n + 1, end)
            self.subsections.append(
                {
                    "line": n,
                    "title": title,
                    "start": n + 1,
                    "end": end,
                    "items": items,
                    "map": " ".join(i.kind for i in items),
                    "words": sum(i.size for i in items if i.kind == "P"),
                    "paragraphs": sum(1 for i in items if i.kind == "P"),
                    "blocks": sum(1 for i in items if i.kind in "CDTQ"),
                    "figures": sum(1 for i in items if i.kind == "D"),
                    "source": sum(i.size for i in items if i.kind == "C"),
                }
            )

    def subsection_of(self, n):
        return next(
            (s for s in self.subsections if s["line"] <= n <= s["end"]), None
        )

    # ---- spans and links ----

    def _parse_links(self):
        self.links = []
        self.spans = {}
        self.span_occurrences = []
        for n, line in enumerate(self.lines, 1):
            if (
                self.fence_at(n) is not None
                or line.startswith(">")
                or line.startswith("## ")
            ):
                continue
            region = "catalog" if self.region[n] == "catalog" else "prose"
            for match in LINK.finditer(line):
                raw, url = match.group(1), match.group(2)
                backticked = (
                    len(raw) > 1 and raw.startswith("`") and raw.endswith("`")
                )
                text = raw[1:-1] if backticked else raw
                self.links.append(
                    self._classify_link(
                        n, match.start(), text, url, backticked
                    )
                )
                if backticked:
                    self._count_span(text, n, region, True, url)
            for match in CODE_SPAN.finditer(
                LINK.sub(
                    lambda m: (
                        " " * len(m.group(0))
                        if m.group(1).startswith("`")
                        else m.group(0)
                    ),
                    line,
                )
            ):
                self._count_span(match.group(0)[1:-1], n, region, False, None)

    def _count_span(self, text, n, region, linked, url):
        summary = self.spans.setdefault(text, SpanSummary(text))
        if region == "prose":
            summary.region = "prose"
        if linked:
            summary.linked += 1
            if url not in summary.urls:
                summary.urls.append(url)
        else:
            summary.bare += 1
            if region == "prose":
                summary.bare_at.append(n)
        self.span_occurrences.append((text, n, region, linked))

    def _classify_link(self, n, col, text, url, backticked):
        config = self.profile
        cited = config.cited_url(url)
        stripped = text.strip().lstrip("&*")
        key = CATALOG_KEY.match(stripped) or (
            BARE_KEY.match(stripped)
            if self.section_of(n).name == "COVERAGE"
            else None
        )
        location = config.location(stripped)
        if not location and cited and not key:
            # a location text whatever its file is called, as in
            # _is_location_link; e.g. `Kconfig.debug:12`
            loose = re.match(r"^([\w./-]+):(\d+)(?:-(\d+))?$", stripped)
            if loose and (
                cited[0] == loose.group(1)
                or cited[0].endswith("/" + loose.group(1))
            ):
                location = (
                    loose.group(1),
                    int(loose.group(2)),
                    (
                        int(loose.group(3))
                        if loose.group(3)
                        else int(loose.group(2))
                    ),
                )
        if key and config.config_re.match(key.group("key").strip()):
            cls, name, tag = (
                "config",
                config.config_re.match(key.group("key").strip()).group(1),
                None,
            )
        elif key:
            cls, name, tag = (
                "catalog",
                symbol_name(key.group("key")),
                symbol_tag(key.group("key")),
            )
        elif location:
            cls, name, tag = "location", None, None
        elif config.is_file_text(stripped) or (
            cited
            and cited[2] is None
            and not key
            and (cited[0] == stripped or cited[0].endswith("/" + stripped))
        ):
            cls, name, tag = "file", None, None
        elif config.config_re.match(stripped):
            cls, name, tag = (
                "config",
                config.config_re.match(stripped).group(1),
                None,
            )
        # a member access: identifiers joined by `->` or `.`, or one member
        # behind a leading `->` or `.`; e.g. `dev->bus->ops`, `resource.start`,
        # `->probe` and `.mmap`
        elif re.match(
            r"^(?:[A-Za-z_]\w*(?:->|\.))+[A-Za-z_]\w*$|^(?:->|\.)"
            r"[A-Za-z_]\w*$",
            stripped,
        ):
            # the field is the last identifier of the chain; e.g. ops of
            # `dev->bus->ops`
            cls, name, tag = (
                "field",
                re.findall(r"[A-Za-z_]\w*", stripped)[-1],
                None,
            )
        # a commit id, 10 to 40 hex digits; e.g. `8d3ae59288f1`
        elif re.fullmatch(r"[0-9a-f]{10,40}", stripped):
            cls, name, tag = "commit", None, None
        elif not backticked:
            cls, name, tag = "plain", None, None
        else:
            cls, name, tag = (
                "symbol",
                symbol_name(stripped),
                symbol_tag(stripped),
            )
        return Link(
            n, col, stripped, url, backticked, cls, name, tag, location, cited
        )

    def links_on(self, n):
        return [link for link in self.links if link.line == n]

    def cited_links(self):
        return [link for link in self.links if link.cited]

    def location_links(self):
        return [
            link
            for link in self.links
            if link.cls == "location" and link.cited
        ]

    def versions(self):
        return collections.Counter(
            link.cited[1] for link in self.links if link.cited
        )

    def version(self):
        found = self.versions()
        return next(iter(found)) if len(found) == 1 else None

    def cited_files(self):
        files = {u.path for u in self.units if u.path}
        files |= {link.cited[0] for link in self.links if link.cited}
        return sorted(files)

    def linked_names_in(self, text):
        out = []
        for match in LINK.finditer(text):
            raw = match.group(1)
            inner = (
                raw[1:-1]
                if raw.startswith("`") and raw.endswith("`") and len(raw) > 1
                else raw
            )
            out.append(symbol_name(inner))
        return out

    # ---- the catalog ----

    def _parse_catalog(self):
        self.catalog = []
        coverage = self.section("COVERAGE")
        if coverage is None:
            return
        for n in range(coverage.start + 1, coverage.end + 1):
            line = self.lines[n - 1]
            match = CATALOG_ENTRY.match(line)
            if not match:
                continue
            traced = CATALOG_KEY.match(match.group(1))
            key = " ".join(
                (traced or BARE_KEY.match(match.group(1))).group("key").split()
            )
            cited = self.profile.cited_url(match.group(2))
            self.catalog.append(
                {
                    "line": n,
                    "text": match.group(1),
                    "key": key,
                    "name": symbol_name(key),
                    "tag": symbol_tag(key),
                    "form": "traced" if traced else "bare",
                    "path": (
                        traced.group("path")
                        if traced
                        else (cited[0] if cited else None)
                    ),
                    "url": match.group(2),
                    "cited_path": cited[0] if cited else None,
                    "cited_line": cited[2] if cited else None,
                }
            )

    @property
    def catalog_keys(self):
        out = []
        for entry in self.catalog:
            if entry["key"] not in out:
                out.append(entry["key"])
        return out

    @property
    def catalog_names(self):
        out = []
        for entry in self.catalog:
            if entry["name"] not in out:
                out.append(entry["name"])
        return out

    def catalog_entry_texts(self):
        return {entry["text"] for entry in self.catalog}

    # ---- tables, legends, outline tables, series ----

    def _parse_tables(self):
        self.tables = []
        n = 1
        while n <= self.n:
            if (
                self.cls[n] == "table"
                and n + 1 <= self.n
                and TABLE_SEPARATOR.match(self.lines[n])
            ):
                header = split_cells(self.lines[n - 1])
                rows = []
                k = n + 2
                while k <= self.n and self.cls[k] == "table":
                    if not TABLE_SEPARATOR.match(self.lines[k - 1]):
                        rows.append((k, split_cells(self.lines[k - 1])))
                    k += 1
                self.tables.append(Table(n, header, rows))
                n = k
            else:
                n += 1
        self.outline_tables = []
        for table in self.tables:
            if not table.header or "piece" not in table.header[0].lower():
                continue
            rows = []
            for line, cells in table.rows:
                if len(cells) < 2:
                    continue
                mark = cells[0].strip()
                if (
                    len(mark) >= 2
                    and mark.startswith("`")
                    and mark.endswith("`")
                ):
                    mark = mark[1:-1]
                text = LINK.sub(r"\1", cells[1]).replace("`", "").strip()
                location = self.profile.location(text)
                if mark and location:
                    rows.append((mark, location[0], location[1], location[2]))
            self.outline_tables.append((table.line, rows))

    def _parse_figures(self):
        self.legends = {}  # fence.start -> [Legend]
        self.drawn_marks = {}  # fence.start -> set of marks on drawing lines
        suffix = (
            "(?:"
            + "|".join(re.escape(s) for s in self.profile.source_suffixes)
            + ")"
        )
        # a legend entry of a figure: group 1 the mark, 2 the function, with or
        # without `()`, 3 the file when the entry names one, 4 the line, 5 the
        # text; e.g. `«A» __handle_mm_fault mm/memory.c:6621  picks the PGD
        # entry` and, the file left out, `«B» __handle_mm_fault :6622  returns
        # the P4D entry`
        entry = re.compile(
            r"^\s*([^\s\u2500-\u257f]\S*)\s+([A-Za-z_]\w*)(?:\(\))"
            r"?\s+(?:([\w./-]+" + suffix + r"))?:(\d+)\b[ \t]*(.*)$"
        )
        for fence in self.figures:
            entries, marks, last_file = [], set(), None
            for k, text in enumerate(fence.body):
                match = entry.match(text)
                n = fence.start + 1 + k
                if match:
                    file = match.group(3) or last_file
                    last_file = file
                    entries.append(
                        Legend(
                            n,
                            match.group(1),
                            match.group(2),
                            file,
                            int(match.group(4)),
                            match.group(5).strip(),
                        )
                    )
                else:
                    marks.update(MARK_CANDIDATE.findall(text))
            self.legends[fence.start] = entries
            self.drawn_marks[fence.start] = marks

    def series(self):
        out = [
            Series(line, "outline", [m for m, _f, _a, _b in rows])
            for line, rows in self.outline_tables
            if rows
        ]
        for fence in self.figures:
            entries = self.legends.get(fence.start) or []
            marks = [e.mark for e in entries]
            marks += sorted(
                self.drawn_marks.get(fence.start, set()) - set(marks),
                key=lambda mark: (mark_index(mark), mark),
            )
            if marks:
                out.append(Series(fence.start, "figure", marks))
        return sorted(out, key=lambda s: s.line)

    # ---- the prose view ----

    def cited_line(self, n):
        """A line that carries words from elsewhere rather than the writer's
        own: every line of OTHER SOURCES, the reader's shelf of cited material,
        and a list entry of SPECIFICATIONS, which names a document and its
        section as the document does (page-model.md, style matching and scope).
        """
        section = self.section_of(n)
        if section is None or section is self.lead:
            return False
        if section.name == "OTHER SOURCES":
            return True
        return section.name == "SPECIFICATIONS" and self.cls[n] == "list"

    def view_rows(self, spans_visible=False):
        """[(line, tag, text, kind, region, level)] of the prose view; kind is
        heading, text or figure; text is the masked line, positions kept."""
        rows = []
        for n, line in enumerate(self.lines, 1):
            if (
                self.fence_at(n) is not None
                or line.startswith(">")
                or line.startswith("## ")
            ):
                continue
            if self.cited_line(n):
                continue
            region = self.region[n]
            if line.startswith("#"):
                match = HEADING.match(line)
                rows.append(
                    (
                        n,
                        "[H] ",
                        match.group(2),
                        "heading",
                        region,
                        len(match.group(1)),
                    )
                )
                continue
            reference_item = region == "reference" and self.cls[n] == "list"
            tag = (
                "[C] "
                if region == "catalog"
                or self.cls[n] == "table"
                or reference_item
                else ""
            )
            rows.append(
                (
                    n,
                    tag,
                    masked_same_length(line, spans_visible),
                    "text",
                    region,
                    0,
                )
            )
        for fence in self.figures:
            for k, text in enumerate(fence.body):
                rows.append(
                    (fence.start + 1 + k, "", text, "figure", "figure", 0)
                )
        return rows

    def printed_view(self, spans_visible=False):
        out = []
        for n, tag, text, kind, _region, _level in self.view_rows(
            spans_visible
        ):
            if kind == "figure":
                continue
            shown = " ".join(text.split()) if kind == "text" else text
            out.append(f"{n}:{tag}{shown}")
        return out

    def skim(self):
        preamble = [i.text for i in self.preamble_items if i.kind == "P"]
        out = {"preamble": [readable(t) for t in preamble], "subsections": []}
        for sub in self.subsections:
            paragraphs = [i for i in sub["items"] if i.kind == "P"]
            out["subsections"].append(
                {
                    "line": sub["line"],
                    "title": sub["title"],
                    "opener": (
                        first_sentence(paragraphs[0].text)
                        if paragraphs
                        else ""
                    ),
                    "closer": (
                        last_sentence(paragraphs[-1].text)
                        if paragraphs
                        else ""
                    ),
                    "recaps": [
                        readable(p.text)
                        for p in paragraphs
                        if RECAP.match(prose_text(p.text))
                    ],
                }
            )
        return out


# ---- claim sentences (page-model.md, claim sentences)
# ------------------------------------------

# a run of digits, a count written in figures; e.g. the `3` of `3 callers`
COUNT_RUN = re.compile(r"\d+")
# a universal word; e.g. `only`, `never`, `every`, `no other`, `the single`
UNIVERSAL = re.compile(
    r"\b(only|sole|solely|never|always|all|every|each|none|no"
    r" other|nothing|anything|everything|whole|exactly|the one|the single)\b",
    re.I,
)
# `once` used as a count: at the end of a clause, or before per, more or again,
# and not in `at once`; e.g. `called once.` and `once per device`, not `once
# the lock is held`
ONCE_COUNT = re.compile(
    r"(?<!\bat\s)\bonce\b(?=\s*(?:[.,;:!?)]|$)|\s+(?:per|more|again)\b)", re.I
)
# two fixed phrases whose `each` and `one` assert nothing; e.g. `the two lists
# point at each other`
FIXED_PHRASES = re.compile(r"\b(?:each other|one another)\b", re.I)
# `whole` where it points at a place and asserts nothing: at the end of a
# clause, or before below, above, here, again, first or last; e.g. `shown whole
# below`
WHOLE_SKIP = re.compile(
    r"\bwhole\b(?=\s*(?:[.,;:!?)]|$)|\s+(?:below|above|here|again|first|last)"
    r"\b)",
    re.I,
)
NUMBER_WORDS = [
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
    "twenty",
    "thirty",
    "forty",
    "fifty",
    "sixty",
    "seventy",
    "eighty",
    "ninety",
    "hundred",
]
# a number written as a word, `one` left to ONE_COUNT; e.g. `three`, `twenty`,
# `thousand`
NUMBER_WORD = re.compile(
    r"\b("
    + "|".join(w for w in NUMBER_WORDS + ["thousand"] if w != "one")
    + r")\b",
    re.I,
)
# a token that mixes a letter or `_` with a digit, an identifier or a version
# and no count; e.g. `x86-64`, `e1000e`, `0x8086`, `CR3`
MIXED_TOKEN = re.compile(r"(?<!\S)(?=\S*[A-Za-z_])(?=\S*\d)\S+")
# a hyphenated compound; e.g. `read-only`, `power-of-two`
HYPHENATED = re.compile(r"\b\w+(?:-\w+)+\b")
ONE_STOP = (
    "of|that|which|who|whose|to|is|was|and|or|in|on|at|for|with|by|as|than|"
    "from|into|the"
)
# `one` used as a count: before a noun or `§`, and not before a stop word such
# as of, that, to or the; e.g. `one caller` and not `one of them`
ONE_COUNT = re.compile(
    r"\bone\b(?=\s+(?:§|(?!(?:" + ONE_STOP + r")\b)[A-Za-z]))", re.I
)


def _count_in(masked_sentence):
    # a version, taken out before counting; e.g. `v7.3`, `v6.15-rc1`
    text = re.sub(r"\bv\d[\w.-]*", " ", masked_sentence)
    # an ordinal, taken out before counting; e.g. `2nd`, `10th`
    text = re.sub(r"\b\d+(st|nd|rd|th)\b", " ", text)
    text = MARK.sub(" ", text)
    text = MIXED_TOKEN.sub(" ", text)
    text = HYPHENATED.sub(" ", text)
    return (
        bool(COUNT_RUN.search(text))
        or bool(NUMBER_WORD.search(text))
        or bool(ONE_COUNT.search(text))
    )


def claim_sentences(page):
    """[(line, readable sentence, kinds)] for every sentence that carries a
    count or a universal word."""
    out = []
    for n in page.prose_lines(("prose", "reference")):
        raw = page.lines[n - 1]
        masked = masked_same_length(raw)
        # a code span hides no number from the count
        visible = masked_same_length(raw, spans_visible=True)
        for start, end in sentence_spans(masked):
            kinds = []
            if _count_in(visible[start:end]):
                kinds.append("COUNT")
            text = WHOLE_SKIP.sub(
                " ",
                FIXED_PHRASES.sub(" ", HYPHENATED.sub(" ", masked[start:end])),
            )
            if UNIVERSAL.search(text) or ONCE_COUNT.search(text):
                kinds.append("UNIVERSAL")
            if kinds:
                out.append((n, readable_slice(raw, start, end).strip(), kinds))
    return out
