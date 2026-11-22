#!/usr/bin/env python3
"""The campaign tool: reads the `kg` fences of a campaign spec
(guidelines/campaign/spec.md), prints a page's content from them and the
pinned tree, and indexes the pages on disk for the planner.

  tools/campaign/run.py validate <spec> [--regions] [--checklist] [--anchors]
  tools/campaign/run.py show <spec> <page>
  tools/campaign/run.py index <spec> [--dir DIR] [--symbol NAME] [--page PAGE]
                              [--conflicts] [--json]
  tools/campaign/run.py content <spec> <page> [--hints] [--out FILE]
                                [--allow-gaps]
  tools/campaign/run.py note <spec> <page> "<text>"
                             [--cluster NAME | --campaign]
  tools/campaign/run.py assign <spec> <symbol> <page> [--cluster NAME]
                               [--force]
  tools/campaign/run.py selftest

Global: --glossary-checkout DIR (default: the checkout holding this file),
--tree DIR (default: the kernel checkout whose .claude directory holds this
repository, TREE_ROOT).

Exit codes: 0 done; 1 an error, a validation failure or a prompt with
unresolved gaps. A spec without a `yaml kg:campaign` block does not validate.

THE BOUNDARY: this tool is an optional implementation of the procedures of
guidelines/campaign/spec.md, and it and the QA engine under tools/qa/ never
depend on each other. Nothing here imports a module of tools/qa/ or runs its
checker, and nothing under tools/qa/ imports this file or runs it. They share
only file formats, each with its own reader: the spec
(guidelines/campaign/spec.md), the page and scope names
(guidelines/page/page-model.md), whose definitions this tool implements as
stated there; where it and the guidelines differ, the tool is wrong. The tool
copies and reports; it never researches the tree: `validate --anchors` only
asks the pinned commit whether each name a scope fence carries exists, and
callers, anchor lines and counts are the writer's.
"""

import argparse
import datetime
import glob
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import yaml

if not __package__:
    # run as a script: make the repository's packages importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.checkout import absolute, tree_default
from tools.tagsfile import entries as tags_entries, head_of

SKILL = str(absolute(__file__).parents[2])

SUBCOMMANDS = (
    "validate",
    "show",
    "index",
    "content",
    "note",
    "assign",
    "selftest",
)
YAML_KINDS = ("campaign", "cluster", "page")
MD_KINDS = (
    "scope",
    "notes",
    "prompt",
    "boundary",
    "bans",
    "cautions",
    "mandatory",
    "rules",
)
ATTRIBUTES = {
    "scope": ("page",),
    "prompt": ("page",),
    "boundary": ("cluster",),
    "notes": ("page", "cluster"),
}
REQUIRED_ATTRIBUTE = {"scope": "page", "prompt": "page", "boundary": "cluster"}
SINGLE_MD = ("bans", "cautions", "mandatory", "rules")
# a line that opens or closes a fence: group 1 the backticks, three or more,
# group 2 the info string; e.g. "```yaml kg:page" gives "```" and `yaml
# kg:page`
FENCE = re.compile(r"^(`{3,})(.*)$")
# a machine-read info string, `<language> kg:<kind>` and what follows: group 1
# the language, 2 the kind, 3 the attributes; e.g. `md kg:scope
# page=rc/portdrv/dpc` gives md, scope and ` page=rc/portdrv/dpc`
INFO = re.compile(r"^\s*([A-Za-z]+)\s+kg:([a-z]+)(.*)$")
# one `page=` or `cluster=` attribute, whose value runs to the next attribute
# or the end of the line and may hold spaces; e.g. ` cluster=Port services
# cluster` gives cluster and `Port services cluster`
ATTRIBUTE = re.compile(r"(page|cluster)=(.+?)(?=\s+(?:page|cluster)=|\s*$)")
# a backticked text, group 1 the text; e.g. "`pci_walk_bridge`" gives
# pci_walk_bridge
SPAN = re.compile(r"`([^`]+)`")
# a traced catalog entry's KEY and PATH (page-model.md [catalog])
# e.g. `'\<pci_walk_bridge\>':'drivers/pci/pcie/err.c'` gives pci_walk_bridge
# and drivers/pci/pcie/err.c
ENTRY = re.compile(r"'\\<([^\\]+?)\\>':'([^']+)'")
# a bare one's KEY and URL
# e.g. "- [`'pci_channel_io_frozen'`](https://x/pci.h#L213): text" gives
# pci_channel_io_frozen and https://x/pci.h#L213
BARE_ENTRY = re.compile(r"^- \[`'([^'\\]+)'`\]\(([^)\s]+)\)")
# a line of a plain fence that opens with a key of a block, the sign of a
# forgotten `kg`; e.g. `page: rc/portdrv/dpc` or `commit: 8d3ae592` at column 0
LOOKS_LIKE_BLOCK = re.compile(r"^(page|assign|commit|tree|version):", re.M)


class CampaignError(Exception):
    pass


def shown(path, skill=SKILL):
    """A path as a message prints it: relative to the glossary checkout when
    inside it, absolute otherwise."""
    path, base = absolute(path), absolute(skill)
    return str(path.relative_to(base) if base in path.parents else path)


# --------------------------------------------------------------------- reading


class StrictLoader(yaml.SafeLoader):
    """YAML's ordinary values, but a repeated key is an error, never a silent
    overwrite."""


def _mapping(loader, node, deep=False):
    loader.flatten_mapping(node)
    out = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in out:
            raise ValueError(
                f"duplicate YAML key `{key}` (line"
                f" {key_node.start_mark.line + 1})"
            )
        out[key] = loader.construct_object(value_node, deep=deep)
    return out


StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping
)


class Fence:
    def __init__(self, number, start, lang, kind, attrs, info):
        (
            self.number,
            self.start,
            self.lang,
            self.kind,
            self.attrs,
            self.info,
        ) = (number, start, lang, kind, attrs, info)
        self.end, self.lines, self.data = None, [], None

    @property
    def body(self):
        return "\n".join(self.lines)

    @property
    def identity(self):
        if self.kind == "campaign":
            return ""
        if self.kind == "cluster":
            return str((self.data or {}).get("name", "?"))
        if self.kind == "page":
            return str((self.data or {}).get("page", "?"))
        return self.attrs.get("page") or self.attrs.get("cluster") or ""

    def __repr__(self):
        who = f" {self.identity}" if self.identity else ""
        return (
            f"{self.lang} kg:{self.kind}{who} (lines {self.start}-{self.end})"
        )


class Spec:
    """Every `kg` fence of one spec, indexed; the errors and warnings its
    reading produced."""

    def __init__(self, path):
        self.path = str(absolute(path))
        self.text = Path(self.path).read_text(encoding="utf-8")
        self.lines = self.text.split("\n")
        self.fences, self.plain = [], []
        self.errors, self.warnings = [], []
        self.campaign = None
        self.clusters, self.pages = [], {}
        self.scopes, self.prompts, self.boundaries = {}, {}, {}
        self.notes_page, self.notes_cluster, self.notes_campaign = {}, {}, []
        self.single = {}
        self._parse()
        self._index()

    # fences
    def _parse(self):
        current, ticks, number = None, 0, 0
        for n, line in enumerate(self.lines, 1):
            found = FENCE.match(line)
            if current is None:
                if not found:
                    continue
                ticks, info = len(found.group(1)), found.group(2)
                kg = INFO.match(info)
                if kg:
                    number += 1
                    lang, kind, rest = (
                        kg.group(1).lower(),
                        kg.group(2),
                        kg.group(3),
                    )
                    attrs = {k: v.strip() for k, v in ATTRIBUTE.findall(rest)}
                    leftover = ATTRIBUTE.sub("", rest).strip()
                    current = Fence(number, n, lang, kind, attrs, info.strip())
                    if leftover:
                        self.errors.append(
                            f"line {n}: unknown attribute text `{leftover}` on"
                            f" {current!r}"
                        )
                else:
                    current = Fence(
                        0,
                        n,
                        (info.strip().split() or [""])[0].lower(),
                        None,
                        {},
                        info.strip(),
                    )
                continue
            if (
                found
                and len(found.group(1)) >= ticks
                and found.group(2).strip() == ""
            ):
                current.end = n
                (self.fences if current.kind else self.plain).append(current)
                current = None
                continue
            current.lines.append(line)
        if current is not None:
            self.errors.append(f"line {current.start}: fence never closed")
            if current.kind:
                current.end = len(self.lines)
                self.fences.append(current)

    def _index(self):
        for f in self.fences:
            if f.lang == "yaml" and f.kind in YAML_KINDS:
                try:
                    f.data = yaml.load(f.body, Loader=StrictLoader) or {}
                except (yaml.YAMLError, ValueError) as error:
                    self.errors.append(
                        f"{f!r}: YAML does not parse:"
                        f" {str(error).splitlines()[0]}"
                    )
                    f.data = {}
                    continue
                if not isinstance(f.data, dict):
                    self.errors.append(f"{f!r}: the block is not a mapping")
                    f.data = {}
                    continue
                if f.kind == "campaign":
                    if self.campaign is not None:
                        self.errors.append(
                            f"{f!r}: a second campaign block; the first is at"
                            f" line {self.campaign.start}"
                        )
                    else:
                        self.campaign = f
                elif f.kind == "cluster":
                    if "name" not in f.data:
                        self.errors.append(
                            f"{f!r}: a cluster block without `name`"
                        )
                    self.clusters.append(f)
                else:
                    page = f.data.get("page")
                    if not page:
                        self.errors.append(
                            f"{f!r}: a page block without `page`"
                        )
                    elif page in self.pages:
                        self.errors.append(
                            f"{f!r}: a second block for {page}; the first is"
                            f" at line {self.pages[page].start}"
                        )
                    else:
                        self.pages[str(page)] = f
            elif f.lang == "md" and f.kind in MD_KINDS:
                allowed = ATTRIBUTES.get(f.kind, ())
                for key in f.attrs:
                    if key not in allowed:
                        self.errors.append(
                            f"{f!r}: attribute `{key}` is not allowed on"
                            f" kg:{f.kind}"
                        )
                need = REQUIRED_ATTRIBUTE.get(f.kind)
                if need and need not in f.attrs:
                    self.errors.append(
                        f"{f!r}: kg:{f.kind} needs {need}=<name>"
                    )
                    continue
                if f.kind == "scope":
                    self.scopes.setdefault(f.attrs["page"], []).append(f)
                elif f.kind == "prompt":
                    self.prompts.setdefault(f.attrs["page"], []).append(f)
                elif f.kind == "boundary":
                    if f.attrs["cluster"] in self.boundaries:
                        self.errors.append(
                            f"{f!r}: a second boundary for the cluster"
                        )
                    self.boundaries[f.attrs["cluster"]] = f
                elif f.kind == "notes":
                    if "page" in f.attrs and "cluster" in f.attrs:
                        self.errors.append(
                            f"{f!r}: notes name a page or a cluster, not both"
                        )
                    elif "page" in f.attrs:
                        self.notes_page.setdefault(f.attrs["page"], []).append(
                            f
                        )
                    elif "cluster" in f.attrs:
                        self.notes_cluster.setdefault(
                            f.attrs["cluster"], []
                        ).append(f)
                    else:
                        self.notes_campaign.append(f)
                else:
                    if f.kind in self.single:
                        self.errors.append(
                            f"{f!r}: a second kg:{f.kind} fence; the first is"
                            f" at line {self.single[f.kind].start}"
                        )
                    else:
                        self.single[f.kind] = f
            else:
                self.errors.append(
                    f"{f!r}: unknown fence kind `{f.lang} kg:{f.kind}`"
                )

    # derived
    def cluster_names(self):
        return [str(c.data.get("name", "?")) for c in self.clusters]

    def clusters_of(self, page):
        return [
            c for c in self.clusters if page in (c.data.get("pages") or [])
        ]

    def assignments(self):
        """(symbol, owner, cluster fence) for every assign row of every
        cluster."""
        rows = []
        for c in self.clusters:
            table = c.data.get("assign") or {}
            if not isinstance(table, dict):
                self.errors.append(f"{c!r}: `assign` is not a mapping")
                continue
            for symbol, owner in table.items():
                rows.append((str(symbol), str(owner), c))
        return rows

    def scope_symbols(self, page):
        """The page's scope names (page-model.md [scope-names]): the names the
        backticked texts of its scope fence give; a family, an expression or a
        field gives none."""
        out = []
        for f in self.scopes.get(page, []):
            for span in SPAN.findall(f.body):
                symbol = scope_name(span)
                if symbol and symbol not in out:
                    out.append(symbol)
        return out

    @property
    def name(self):
        data = (self.campaign.data if self.campaign else {}) or {}
        return str(data.get("campaign") or Path(self.path).stem)

    @property
    def dir(self):
        data = (self.campaign.data if self.campaign else {}) or {}
        return str(data.get("dir") or self.name)

    @property
    def exclude(self):
        """The subdirectories of docs/<dir>/ the index skips (campaign-spec.md
        [campaign], [index])."""
        data = (self.campaign.data if self.campaign else {}) or {}
        value = data.get("exclude") or []
        return (
            [str(e).strip("/") for e in value if str(e).strip("/")]
            if isinstance(value, list)
            else []
        )


def load(path):
    if not Path(path).exists():
        raise CampaignError(f"no such spec: {path}")
    return Spec(path)


# -------------------------------------------------------------------- validate


def subsystem_map(skill):
    """{dir: {name, section6_heading}} of guidelines/subsystems.md, or None
    when the checkout has no such file."""
    path = Path(skill, "guidelines", "subsystems.md")
    if not path.is_file():
        return None
    out = {}
    # one entry of guidelines/subsystems.md, a `## ` heading and the lines up
    # to the next one: group 1 the name, group 2 the entry's lines; e.g. "##
    # PCIe\n\n- tag: `pcie`\n- dir: `pci`\n" gives PCIe and the two list lines
    for m in re.finditer(
        r"^## (.+?)\n(.*?)(?=^## |\Z)",
        path.read_text(encoding="utf-8"),
        re.S | re.M,
    ):
        # the entry's directory line, group 1 the directory; e.g. "- dir:
        # `pci`" gives pci
        d = re.search(r"^- dir: `([^`]+)`", m.group(2), re.M)
        # the entry's section-six line, group 1 the heading; e.g. `-
        # section6_heading: REGISTERS` gives REGISTERS
        s6 = re.search(r"^- section6_heading: (\S+)", m.group(2), re.M)
        if d:
            out[d.group(1)] = {
                "name": m.group(1).strip(),
                "section6_heading": s6.group(1) if s6 else None,
            }
    return out


def _check_subsystem(spec, errors, warnings):
    """The Campaign block says dir and section6 once more than
    guidelines/subsystems.md does: the two must agree."""
    directory = str(
        spec.campaign.data.get("dir")
        or spec.campaign.data.get("campaign")
        or ""
    )
    entries = subsystem_map(Path(spec.path).parent.parent)
    if entries is None or not directory:
        return
    entry = entries.get(directory)
    heading = str(spec.campaign.data.get("section6", "none"))
    if entry is None:
        warnings.append(
            f"{spec.campaign!r}: no entry of guidelines/subsystems.md"
            f" has dir `{directory}`; a new subsystem gets its entry"
            " first"
        )
    elif entry["section6_heading"] and heading != entry["section6_heading"]:
        errors.append(
            f"{spec.campaign!r}: section6 `{heading}` disagrees with"
            f' the {entry["name"]} entry of guidelines/subsystems.md,'
            f' whose section6_heading is {entry["section6_heading"]}'
        )


def _check_reuse(spec, errors):
    reuse = spec.campaign.data.get("reuse") or []
    if not isinstance(reuse, list):
        errors.append(f"{spec.campaign!r}: `reuse` is not a list")
        return
    for row in reuse:
        if (
            not isinstance(row, dict)
            or "source" not in row
            or ":" not in str(row.get("source", ""))
        ):
            errors.append(
                f"{spec.campaign!r}: a reuse row needs a `source` of"
                f" the form <ref>:<path>: {row}"
            )
        for p in (row.get("pages") or []) if isinstance(row, dict) else []:
            if p not in spec.pages:
                errors.append(
                    f"{spec.campaign!r}: reuse row for"
                    f' {row.get("figure")} names an unknown page {p}'
                )


def _check_campaign(spec, errors, warnings):
    """The Campaign block: its pin, its subsystem entry, its reuse rows and
    the directories it excludes."""
    for key in ("tree", "version", "commit"):
        if not spec.campaign.data.get(key):
            errors.append(f"{spec.campaign!r}: the pin needs `{key}`")
    commit = str(spec.campaign.data.get("commit", ""))
    # a full commit id, 40 lowercase hex digits; e.g.
    # `8d3ae59288f1e7d58d76558a6ee96d533bc5019f`, and not the short `8d3ae59`
    if commit and not re.fullmatch(r"[0-9a-f]{40}", commit):
        errors.append(
            f"{spec.campaign!r}: `commit` is not a full 40-character sha"
            f" ({commit})"
        )
    _check_subsystem(spec, errors, warnings)
    _check_reuse(spec, errors)
    exclude = spec.campaign.data.get("exclude") or []
    if not isinstance(exclude, list) or any(
        not isinstance(e, str)
        or not e.strip("/")
        or e.startswith("/")
        or ".." in e.split("/")
        for e in exclude
    ):
        errors.append(
            f"{spec.campaign!r}: `exclude` is not a list of relative"
            f" directory names under docs/{spec.dir}/"
        )


def _check_scope(spec, fence, assigned_names, warnings):
    """What a scope fence should not carry: a suffix shorthand, an errata
    bracket."""
    # a real symbol with one leading underscore is no shorthand
    shorts = [s for s in shorthands(fence.body) if s not in assigned_names]
    if shorts:
        warnings.append(
            f"{fence!r}: {len(shorts)} suffix"
            f' shorthand{"s" if len(shorts) != 1 else ""}'
            f' ({", ".join("`" + x + "`" for x in shorts)}); a scope'
            " names each symbol in full, since the floor and the"
            " seams resolve by name"
        )
    # every errata bracket of a scope fence, counted by its opening; e.g. the
    # `[errata` of "[errata 2026-10-01: `x` is `y`]"
    errata = len(re.findall(r"\[errata\b", fence.body))
    if errata:
        warnings.append(
            f"{fence!r}: {errata} `[errata …]`"
            f' bracket{"s" if errata != 1 else ""}, whose backticked'
            " names count as scope names; a correction is a line of"
            " the page's notes fence, written at the fold-in"
        )


def _check_page(spec, page, f, assigned_names, errors, warnings):
    """One page block: its scope fence, its cluster and its keys."""
    n = len(spec.scopes.get(page, []))
    if n == 0:
        errors.append(f"{f!r}: no `md kg:scope page={page}` fence")
    elif n > 1:
        errors.append(f"{f!r}: {n} scope fences; a page has one")
    if not spec.clusters_of(page):
        warnings.append(f"{page} belongs to no cluster")
    for sf in spec.scopes.get(page, []):
        _check_scope(spec, sf, assigned_names, warnings)
    tag = f.data.get("tag")
    if tag is not None and tag not in ("requested", "curated", "optional"):
        errors.append(
            f"{f!r}: tag `{tag}` is not requested, curated or optional"
        )
    s6 = f.data.get("section6")
    if s6 is not None and str(s6) not in SECTION_SIX:
        errors.append(
            f'{f!r}: section6 `{s6}` is not one of {", ".join(SECTION_SIX)}'
        )
    symbols = f.data.get("symbols") or []
    if not isinstance(symbols, list) or any(
        not isinstance(g, dict) or "names" not in g for g in symbols
    ):
        errors.append(f"{f!r}: `symbols` is a list of {{file, names}} groups")


def _check_names(spec, errors):
    """Every fence that names a page or a cluster names one with a block."""
    for group in (spec.scopes, spec.prompts, spec.notes_page):
        for page, fences in group.items():
            if page not in spec.pages:
                for f in fences:
                    errors.append(f"{f!r}: names a page with no block")
    names = spec.cluster_names()
    for name in list(spec.boundaries) + list(spec.notes_cluster):
        if name not in names:
            errors.append(
                f"kg:boundary or kg:notes cluster={name}: no cluster block"
                " carries that name"
            )


def _check_clusters(spec, errors, warnings):
    seen = {}
    for c in spec.clusters:
        name = str(c.data.get("name", "?"))
        if name in seen:
            errors.append(f"{c!r}: a second cluster named {name}")
        seen[name] = c
        for p in c.data.get("pages") or []:
            if p not in spec.pages:
                errors.append(f"{c!r}: `pages` names {p}, which has no block")
        if name not in spec.boundaries:
            warnings.append(f"cluster {name} has no kg:boundary fence")


def _check_assignments(spec, errors):
    owners = {}
    for symbol, owner, c in spec.assignments():
        if owner not in spec.pages:
            errors.append(
                f"{c!r}: `{symbol}` is assigned to {owner}, which has no block"
            )
        if symbol in owners and owners[symbol] != owner:
            errors.append(
                f"`{symbol}` is assigned to both {owners[symbol]} and {owner}"
            )
        owners.setdefault(symbol, owner)


def validate(spec):
    """(errors, warnings) of a spec, the ones its reading found first."""
    errors, warnings = list(spec.errors), list(spec.warnings)
    if spec.campaign is None:
        errors.append("no `yaml kg:campaign` block")
    else:
        _check_campaign(spec, errors, warnings)
    assigned_names = {symbol for symbol, _owner, _c in spec.assignments()}
    for page, f in spec.pages.items():
        _check_page(spec, page, f, assigned_names, errors, warnings)
    _check_names(spec, errors)
    _check_clusters(spec, errors, warnings)
    _check_assignments(spec, errors)
    for f in spec.plain:
        if f.lang in ("yaml", "md", "markdown") and LOOKS_LIKE_BLOCK.search(
            f.body
        ):
            warnings.append(
                f"lines {f.start}-{f.end}: a `{f.lang}` fence without kg that"
                " looks like a block; add kg:<kind> if a tool should read it"
            )
    return errors, warnings


# above this many names, one pass over the roots' files is cheaper than one
# `git grep` per name
BULK_ANCHORS = 32
# a word of a file's bytes, a run of letters, digits and underscores; e.g.
# pci_walk_bridge, bridge and cb in b"pci_walk_bridge(bridge, cb);"
_WORD = re.compile(rb"\w+")


def anchors(spec, tree, pages=None):
    """Every identifier the scope fences carry, asked of the pinned commit:
    first under the Campaign block's roots, then over the whole tree, as `git
    grep -w -F` answers. Returns (checked, outside, missing): the number of
    distinct names asked, the (page, name, file) rows found only outside the
    roots, and the (page, name) rows found nowhere at the commit. Suffix
    shorthands are skipped. When the checkout sits at the pin and the names are
    many, the roots are read once for all of them (`_held_by_roots`): a catalog
    of three thousand names takes seconds where a `git grep` per name over
    roots of several hundred megabytes takes more than ten minutes."""
    data = spec.campaign.data
    commit = str(data.get("commit"))
    roots = [str(r) for r in data.get("roots") or []]
    # the working tree answers when the checkout sits at the pin (git grep
    # reads files, fast); otherwise the commit itself (blobs, slower)
    rev = "" if git(tree, "rev-parse", "HEAD").strip() == commit else commit
    asked = []
    for page in pages or spec.pages:
        for name in spec.scope_symbols(page):
            if SHORTHAND.match(f"`{name}`"):
                # a suffix shorthand names nothing on its own; validate warns
                # about it already
                continue
            asked.append((page, name))
    names = list(dict.fromkeys(name for _page, name in asked))
    held = (
        _held_by_roots(tree, names, roots)
        if roots and not rev and len(names) > BULK_ANCHORS
        else set()
    )
    seen = {
        name: "" if name in held else _anchor(tree, rev, name, roots)
        for name in names
    }
    outside, missing = [], []
    for page, name in asked:
        where = seen[name]
        if where is None:
            missing.append((page, name))
        elif where:
            outside.append((page, name, where))
    return len(names), outside, missing


def _held_by_roots(tree, names, roots):
    """The plain identifiers among `names` that a tracked text file under
    `roots` carries as a whole word in the working tree, found in one pass over
    those files: what `git grep -I -w -F -e <name> -- <roots>` answers for each
    name alone (a word is a run of letters, digits and underscores; a file with
    a NUL in its first 8000 bytes is binary). A name that is no plain
    identifier is left to that command.
    """
    # a name that is a plain identifier, the only kind the one pass over the
    # files answers; e.g. `pci_walk_bridge`, and not `foo.bar` or `not an
    # identifier`
    left = {n.encode() for n in names if re.fullmatch(r"\w+", n, re.ASCII)}
    run = subprocess.run(
        ["git", "-C", tree, "ls-files", "-z", "--", *roots],
        capture_output=True,
    )
    if run.returncode != 0:
        raise CampaignError(
            f'git ls-files -- {" ".join(roots)} failed in {tree}:'
            f' {run.stderr.decode(errors="replace").strip()}'
        )
    found = set()
    for rel in run.stdout.split(b"\0"):
        if not left:
            break
        path = Path(tree, os.fsdecode(rel))
        if not rel or path.is_symlink():
            continue
        try:
            text = path.read_bytes()
        except OSError:
            # tracked and absent from the working tree: git grep has nothing to
            # read there either
            continue
        if b"\0" in text[:8000]:
            continue
        hit = left.intersection(_WORD.findall(text))
        found |= hit
        left -= hit
    return {n.decode() for n in found}


def _anchor(tree, rev, name, roots):
    """'' when a root holds `name` at `rev` (the working tree when `rev` is
    empty), or the tree does and there are no roots; the first file holding it
    outside the roots; None when no file does.
    """

    def grep(flag, paths=()):
        cmd = (
            ["git", "-C", tree, "grep", "-I", "-w", "-F", flag, "-e", name]
            + ([rev] if rev else [])
            + ["--", *paths]
        )
        run = subprocess.run(cmd, capture_output=True, text=True)
        if run.returncode not in (0, 1):
            raise CampaignError(
                f'git grep -w -F -e {name} {rev or "(working tree)"} failed in'
                f" {tree}: {run.stderr.strip()}"
            )
        return run.returncode == 0, run.stdout

    if roots:
        found, _ = grep("-q", roots)
        if found:
            return ""
    found, out = grep("-l")
    if not found:
        return None
    if not roots:
        return ""
    first = out.split("\n", 1)[0]
    return first.split(":", 1)[1] if ":" in first else first


def regions(spec):
    return [
        f"lines {f.start}-{f.end}: {f.lang} kg:{f.kind}"
        + (f" {f.identity}" if f.identity else "")
        for f in spec.fences
    ]


def checklist(spec):
    rows = []
    for kind in SINGLE_MD:
        rows.append(
            f"campaign {kind}: "
            + ("present" if kind in spec.single else "EMPTY")
        )
    rows.append(f"campaign notes: {len(spec.notes_campaign)} fence(s)")
    reuse = (spec.campaign.data.get("reuse") if spec.campaign else None) or []
    for page, f in spec.pages.items():
        parts = []
        parts.append("scope" if page in spec.scopes else "scope EMPTY")
        n = sum(
            len(g.get("names") or [])
            for g in f.data.get("symbols") or []
            if isinstance(g, dict)
        )
        parts.append(f"symbols {n}" if n else "symbols EMPTY")
        parts.append(
            f"notes {len(spec.notes_page.get(page, []))}"
            if page in spec.notes_page
            else "notes EMPTY"
        )
        clusters = spec.clusters_of(page)
        if clusters:
            name = str(clusters[0].data.get("name"))
            parts.append(f"cluster {name}")
            parts.append(
                "boundary" if name in spec.boundaries else "boundary EMPTY"
            )
            parts.append(
                f"cluster notes {len(spec.notes_cluster.get(name, []))}"
                if name in spec.notes_cluster
                else "cluster notes EMPTY"
            )
        else:
            parts.append("cluster EMPTY")
        parts.append(
            f"prompt additions {len(spec.prompts.get(page, []))}"
            if page in spec.prompts
            else "prompt additions EMPTY"
        )
        pointers = [
            r
            for r in reuse
            if isinstance(r, dict) and page in (r.get("pages") or [])
        ]
        parts.append(f"reuse {len(pointers)}" if pointers else "reuse EMPTY")
        rows.append(f"{page}: " + ", ".join(parts))
    return rows


# ----------------------------------------------------------------------- index


def member_key(key):
    """campaign-spec.md [index]: a key that claims no owner: a member entry's
    key `A.B`, or a malformed key, a declaration such as `bool hotplug_active`
    (page-model.md [catalog]); `struct X`, `enum X`, `union X` and a single
    name are symbols."""
    words = key.split()
    # a member key `A.B`; e.g. `pci_error_handlers.error_detected`
    if re.fullmatch(r"[A-Za-z_]\w*\.[A-Za-z_]\w*", key.strip()):
        return True
    # a tagged type, which is a symbol and no malformed key; e.g. `struct
    # pci_dev`, where `bool hotplug_active` is a declaration
    return (
        len(words) > 1
        and "(" not in key
        and not re.fullmatch(
            r"(?:struct|enum|union) [A-Za-z_]\w*", " ".join(words)
        )
    )


def coverage_entries(page_path):
    """(name, file) of a page's catalog entries, member entries and malformed
    keys aside (campaign-spec.md [index]); a bare entry's file is its URL's."""
    text = Path(page_path).read_text(encoding="utf-8")
    # the COVERAGE section of a page, from its heading to the next `## `
    # heading or the end of the page; e.g. "## COVERAGE\n\n- [...](...)\n\n##
    # DOCUMENTATION\n" gives the section without the next heading
    found = re.search(r"^## COVERAGE.*?(?=^## |\Z)", text, re.S | re.M)
    if not found:
        return []
    out = []
    for line in found.group(0).split("\n"):
        if not line.startswith("- "):
            continue
        traced = ENTRY.findall(line)
        bare = None if traced else BARE_ENTRY.match(line)
        if traced:
            out.extend(
                (symbol_name(key), path)
                for key, path in traced
                if not member_key(key)
            )
        elif bare and not member_key(bare.group(1)):
            path = permalink_path(bare.group(2))
            if path:
                out.append((symbol_name(bare.group(1)), path))
    return out


_PERMALINK = {}


def permalink_path(url, skill=SKILL):
    """The path of a cited URL by the profile's `permalink` template
    (page-model.md [profile]), or None."""
    if skill not in _PERMALINK:
        text = Path(skill, "guidelines", "page", "page-model.md").read_text(
            encoding="utf-8"
        )
        # the body of the profile fence of page-model.md, group 1 the YAML;
        # e.g. "```yaml kg:profile\npermalink: \"https://...\"\n```"
        fence = re.search(
            r"^```yaml kg:profile[ \t]*\n(.*?)^```", text, re.S | re.M
        )
        if not fence:
            raise CampaignError(
                "guidelines/page/page-model.md carries no `yaml kg:profile`"
                " fence"
            )
        template = yaml.safe_load(fence.group(1))["permalink"]
        parts = {
            "#L{line}": r"(?:#L\d+)?",
            "{version}": r"[^/\s)#?]+",
            "{path}": r"(?P<path>[^#)\s?]+)",
            "{line}": r"\d+",
        }
        # a cited URL with its path named: the permalink template cut at its
        # placeholders, each replaced by its pattern; e.g.
        # https://elixir.bootlin.com/linux/v7.2/source/mm/memory.c#L10 gives
        # the path mm/memory.c
        _PERMALINK[skill] = re.compile(
            "".join(
                parts.get(piece, re.escape(piece))
                for piece in re.split(
                    r"(#L\{line\}|\{version\}|\{path\}|\{line\})", template
                )
            )
        )
    found = _PERMALINK[skill].search(url)
    return found.group("path") if found else None


def index(skill, directory, exclude=()):
    """{symbol: [pages]} and {page: [(symbol, file)]} over docs/<dir>/**/*.md,
    the subdirectories `exclude` names skipped (campaign-spec.md [index])."""
    root = Path(skill, "docs", directory)
    by_symbol, by_page = {}, {}
    skipped = tuple(e.strip("/") + "/" for e in exclude if e.strip("/"))
    found = sorted(
        (str(Path(path).relative_to(root))[:-3], path)
        for path in glob.glob(str(root / "**" / "*.md"), recursive=True)
    )
    for page, path in found:
        if page.startswith(skipped):
            continue
        entries = coverage_entries(path)
        by_page[page] = entries
        for name, where in entries:
            by_symbol.setdefault(name, [])
            if (page, where) not in by_symbol[name]:
                by_symbol[name].append((page, where))
    return by_symbol, by_page


def holders(by_symbol, name, where=None, exclude=None):
    """The pages cataloging `name`, as 'page (file)' when two files carry the
    name; `where` keeps the holders of one file, `exclude` drops one page."""
    rows = [
        (p, f)
        for p, f in by_symbol.get(name, [])
        if p != exclude and (where is None or f == where)
    ]
    files = {f for _p, f in by_symbol.get(name, [])}
    return [f"{p} ({f})" if len(files) > 1 else p for p, f in rows]


# subsystems.md's section-six values
SECTION_SIX = (
    "REGISTERS",
    "METHODS",
    "PRIMITIVES",
    "INTERFACES",
    "none",
)
# a suffix shorthand in a scope, a backticked text that opens with one
# underscore and a lowercase letter, with or without `()`; e.g. "`_alloc`" and
# "`_remove_y()`", and not "`__pci_walk_x`" or "`_OSC`"
SHORTHAND = re.compile(r"`(_[a-z][A-Za-z0-9_]*)(?:\(\))?`")


def symbol_name(text):
    """page-model.md [spans]: the identifier before the first `(` when the text
    has one, otherwise its last word with `*`, `&` and a trailing `[]` removed;
    `struct X` names `X`.
    """
    text = text.strip()
    if "(" in text:
        # the identifiers before the first parenthesis, the last of which is
        # the name; e.g. `tb_port_enable(port)` gives tb_port_enable
        found = re.findall(r"[A-Za-z_]\w*", text[: text.index("(")])
        return found[-1] if found else ""
    for word in reversed(text.split()):
        # an array suffix at the end of a word, cut off; e.g. `tmu_rates[]`
        # gives tmu_rates
        word = re.sub(r"\[[^\]]*\]$", "", word.strip("*&"))
        if word:
            return word
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
    """page-model.md [scope-names]: the name a scope text gives, or None. The
    identifier alone, `struct X`, a call that ends the text unless its
    identifier is a C keyword, or an array that ends the text.
    """
    text = " ".join(text.split())
    # a tagged type and nothing else, group 1 its name; e.g. `struct tb_switch`
    # gives tb_switch
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


def shorthands(text):
    """The suffix shorthands a scope carries, `_probe` for `aer_probe`: a span
    that opens with one underscore and a lowercase letter, which names nothing
    the floor or the index can find.
    """
    return [m.group(1) for m in SHORTHAND.finditer(text)]


def seams(spec, page, by_symbol):
    """For a page not on disk, the dispatcher's view of its seams: every symbol
    its scope names and the pages cataloging it today, '-' where none does."""
    symbols = spec.scope_symbols(page)
    if not symbols:
        return [
            f"{page}: not on disk under docs/{spec.dir}/, and the spec names"
            " no scope symbol for it"
        ]
    out = [
        f"{page}: not on disk under docs/{spec.dir}/; its scope names"
        f' {len(symbols)} symbol{"s" if len(symbols) != 1 else ""}, cataloged'
        " today by:"
    ]
    for s in symbols:
        who = holders(by_symbol, s)
        flag = (
            " (suffix shorthand; the floor cannot resolve it)"
            if SHORTHAND.match(f"`{s}`")
            else ""
        )
        out.append(f'  {s}: {", ".join(who) if who else "-"}{flag}')
    return out


def conflicts(spec, by_symbol):
    out = []
    for symbol, rows in sorted(by_symbol.items()):
        per_file = {}
        for page, where in rows:
            per_file.setdefault(where, []).append(page)
        for where, pages in per_file.items():
            if len(pages) > 1:
                out.append(
                    f'{symbol} ({where}): cataloged by {", ".join(pages)}'
                )
    for symbol, owner, _c in spec.assignments():
        pages = [p for p, _f in by_symbol.get(symbol, [])]
        if pages and pages != [owner]:
            out.append(
                f"{symbol}: primary page {owner}; cataloged on disk by"
                f' {", ".join(holders(by_symbol, symbol))}'
            )
    return out


# --------------------------------------------------------------- state on disk


def git(cwd, *args, ok=(0,)):
    """The output of one git command in `cwd`; an exit status outside `ok`
    is a CampaignError that carries git's own words, which every caller
    would otherwise spell out."""
    run = subprocess.run(
        ["git", "-C", cwd, *args], capture_output=True, text=True
    )
    if run.returncode not in ok:
        raise CampaignError(
            f'git {" ".join(args)} failed in {cwd}: {run.stderr.strip()}'
        )
    return run.stdout


def tree_root(spec, override=None, checkout=None):
    """The kernel tree: --tree, else the spec's tree when it is a path, else
    $KG_TREE, else the kernel checkout whose .claude directory holds this
    tool's checkout (TREE_ROOT); a CampaignError when none is there.
    """
    if override:
        return str(absolute(override))
    value = str(
        (spec.campaign.data if spec.campaign else {}).get("tree", "TREE_ROOT")
    )
    if value == "TREE_ROOT":
        found, _how = tree_default(checkout or SKILL)
        if found is None:
            raise CampaignError(
                "the spec says tree: TREE_ROOT, but no .claude directory"
                f" holds {checkout or SKILL}; pass --tree or set KG_TREE"
            )
        return found
    return str(absolute(value))


# ---------------------------------------------------------------------- prompt


def mention_pattern(page, symbols):
    """A page is mentioned by its slug, as `slug` or `slug.md`; a symbol of its
    scope by its backticked name, `name` or `name()`; short names stay out so a
    common word does not match.
    """
    slug = page.rsplit("/", 1)[-1]
    parts = [r"(?<![\w/-])" + re.escape(slug) + r"(?:\.md)?(?![\w-])"]
    parts += [
        r"`" + re.escape(s) + r"(?:\(\))?`" for s in symbols if len(s) >= 4
    ]
    # a mention of the page or of a symbol of its scope: the slug as a word of
    # its own, with or without `.md`, or a scope symbol of four characters or
    # more in backticks, with or without `()`; e.g. for the slug error-recovery
    # and the symbol pcie_do_recovery: `error-recovery.md walks it` and
    # "`pcie_do_recovery()`", and not `aer-error-recovery`
    return re.compile("|".join(parts))


TAG_KIND_NAMES = {
    "f": "definition",
    "p": "prototype",
    "v": "variable",
    "x": "extern",
    "d": "macro",
    "m": "member",
    "s": "struct",
    "u": "union",
    "g": "enum",
    "e": "enumerator",
    "t": "typedef",
}
PACK_CENSUS_CAP = 40
PACK_CALLERS_CAP = 12


def _readtags(tree, tags, name):
    """(path, line, kind) per entry of the tags file for name, each settled to
    a line of its file by tools/tagsfile.py (the tags file carries search
    patterns, not line numbers).
    """
    return [
        (path, line_no, kind)
        for path, line_no, kind, _fields in tags_entries(tree, tags, name)
    ]


_OWN_DEFINITIONS = (
    "struct ",
    "union ",
    "enum ",
    "typedef ",
    "macro ",
    "variable ",
    "tracepoint ",
)


def _rank_defs(defs):
    """The definition lines of one name in reading order: function definitions,
    a .c body before a header's, then the stubs, then the lines on which the
    name is the defined identifier of a type, a macro or a variable, then what
    only declares or contains it (a prototype, an extern, a member, an
    enumerator), each group in the order it was found.
    """
    functions = sorted(
        (d for d in defs if d.startswith("definition ")),
        key=lambda d: not d.split()[1].partition(":")[0].endswith(".c"),
    )
    stubs = [d for d in defs if d.startswith("stub definition ")]
    own = [d for d in defs if d.startswith(_OWN_DEFINITIONS)]
    rest = [
        d
        for d in defs
        if d not in functions and d not in stubs and d not in own
    ]
    return functions + stubs + own + rest


_FILE_LINES = {}


def _file_lines(tree, path):
    """The lines of a tree file, cached per path; [] when it cannot be read."""
    if (tree, path) not in _FILE_LINES:
        try:
            _FILE_LINES[(tree, path)] = (
                Path(tree, path)
                .read_text(encoding="utf-8", errors="replace")
                .split("\n")
            )
        except OSError:
            _FILE_LINES[(tree, path)] = []
    return _FILE_LINES[(tree, path)]


def _code_only(line, in_comment):
    """(text, in_comment): the line with its comments and its string and
    character literals blanked, so that a brace or a semicolon inside them does
    not count."""
    out, i, n = [], 0, len(line)
    while i < n:
        if in_comment:
            k = line.find("*/", i)
            if k < 0:
                return "".join(out), True
            i, in_comment = k + 2, False
            continue
        if line.startswith("/*", i):
            i, in_comment = i + 2, True
            continue
        if line.startswith("//", i):
            break
        if line[i] in "\"'":
            quote, i = line[i], i + 1
            while i < n and line[i] != quote:
                i += 2 if line[i] == "\\" else 1
            i += 1
            continue
        out.append(line[i])
        i += 1
    return "".join(out), in_comment


def _function_end(lines, start, strict=False):
    """The last line (1-based) of the function whose definition begins at line
    start of lines: the line on which the brace that opened its body closes,
    the same line for a one-line body. None when a `;` ends the declaration
    before any body opens (a prototype, a macro invocation) or no body closes.
    Under strict, for a candidate that is a macro invocation (PAGEFLAG(Locked,
    locked, PF_NO_TAIL), INTERVAL_TREE_DEFINE(...)), a blank line or a new
    column-0 line before the body opens also means no body: such a line ends
    with no `;`, and without this rule it swallowed every function down to the
    next brace that closed.
    """
    depth, opened, in_comment = 0, False, False
    for number in range(start, len(lines) + 1):
        if strict and number > start and not opened:
            raw = lines[number - 1]
            if not raw.strip() or (
                raw[:1] not in " \t"
                and not raw.startswith(("{", ")", "#", "/", "*"))
            ):
                return None
        text, in_comment = _code_only(lines[number - 1], in_comment)
        for ch in text:
            if ch == "{":
                depth, opened = depth + 1, True
            elif ch == "}":
                depth -= 1
                if opened and depth == 0:
                    return number
            elif ch == ";" and not opened:
                return None
    return None


def _brace_end(tree, path, start):
    """The last line of the function whose definition line is start, or start
    when no body closes."""
    return _function_end(_file_lines(tree, path), start) or start


def _head(tree, path, number):
    """The first line of the signature whose name line is number: the
    return-type line of a split signature (`static int` above
    `copy_pte_range(...)`), the definition line links.definition-line names,
    else number.
    """
    return head_of(_file_lines(tree, path), number)


_FUNCTION_INDEX = {}
# the type may stand on the line above
# a column-0 line that opens a function: optional type words, then the name
# before `(`, group 1 the name; e.g. `static int pci_walk_bus(struct pci_bus
# *top,` gives pci_walk_bus
_DEFINITION = re.compile(r"^(?:[A-Za-z_][\w \t*]*?\b)?([A-Za-z_]\w*)\s*\(")
_NOT_A_DEFINITION = ("#", "/", "*", "}", "typedef")
# a macro-style name, capitals, digits and underscores after optional leading
# underscores; e.g. `SYSCALL_DEFINE4`, `__SETUP`
_MACRO_NAME = re.compile(
    r"_*[A-Z][A-Z0-9_]*"
    # a column-0 macro invocation: it defines a function only when its body
    # opens at once (SYSCALL_DEFINE4)
)


def _function_index(tree, path):
    """[(name, start, end)] of the functions a C file defines, by their
    column-0 definition lines and the brace that closes each body: a one-line
    body ends on its own line, a function returning a struct pointer is a
    function, and a prototype or a macro invocation that ends in `;` is no
    function; cached per file.
    """
    if (tree, path) in _FUNCTION_INDEX:
        return _FUNCTION_INDEX[(tree, path)]
    index, lines, number = [], _file_lines(tree, path), 1
    while number <= len(lines):
        line = lines[number - 1]
        found = _DEFINITION.match(line)
        if (
            found
            and not line.rstrip().endswith(";")
            and not line.startswith(_NOT_A_DEFINITION)
        ):
            end = _function_end(
                lines,
                number,
                strict=_MACRO_NAME.fullmatch(found.group(1)) is not None,
            )
            if end is not None:
                syscall = _SYSCALL.match(
                    line
                    # SYSCALL_DEFINE4(migrate_pages, ...) defines
                    # sys_migrate_pages, not a function named SYSCALL_DEFINE4
                )
                index.append(
                    (
                        (
                            ("compat_sys_" if syscall.group(1) else "sys_")
                            + syscall.group(2)
                            if syscall
                            else found.group(1)
                        ),
                        number,
                        end,
                    )
                )
                number = end + 1
                continue
        number += 1
    _FUNCTION_INDEX[(tree, path)] = index
    return index


# ` * text`, ` */`, `/* ...`; not `*fpin = f(...)`
# a comment line: it opens with `/*` or `//`, or with a `*` that a space, a `/`
# or the end of the line follows
_COMMENT_LINE = re.compile(r"^\s*(/\*|//|\*(\s|/|$))")


def _comment_line(text):
    """Whether a census line's text is a comment line in the kernel's style, a
    mention no call is made on."""
    return _COMMENT_LINE.match(text) is not None


def _enclosing(tree, path, number):
    """(name, start, end) of the function that holds line number of path, or
    None."""
    for name, start, end in _function_index(tree, path):
        if start <= number <= end:
            return name, start, end
    return None


# a name with more mentions than this is too common for a census or a caller
# list here
PACK_COMMON_CAP = 200
# a name defined more often than this tree-wide (flags, lock, next) keeps the
# definitions under the roots and a count of the rest
PACK_DEFS_CAP = 40
PACK_ASIDE = ("Documentation/", "tools/", "samples/", "scripts/")
_ARCH_WORDS = {
    "x86": "x86",
    "x86-64": "x86",
    "x86_64": "x86",
    "i386": "x86",
    "arm64": "arm64",
    "aarch64": "arm64",
    "arm": "arm",
    "powerpc": "powerpc",
    "ppc": "powerpc",
    "ppc64": "powerpc",
    "riscv": "riscv",
    "s390": "s390",
    "mips": "mips",
    "loongarch": "loongarch",
    "sparc": "sparc",
    "parisc": "parisc",
    "alpha": "alpha",
    "m68k": "m68k",
    "sh": "sh",
    "xtensa": "xtensa",
    "um": "um",
    "openrisc": "openrisc",
    "microblaze": "microblaze",
    "nios2": "nios2",
    "csky": "csky",
    "hexagon": "hexagon",
    "arc": "arc",
}
# a macro definition, group 1 its name; e.g. `#define PCI_EXP_FLAGS 0x02` gives
# PCI_EXP_FLAGS and `# define FOO(x) (x)` gives FOO
_MACRO = re.compile(r"^#\s*define\s+([A-Za-z_]\w*)")
# a column-0 line that opens or names a struct, union or enum: group 1 the
# keyword, 2 the tag, 3 `{` or the end of the line; e.g. `struct pci_dev {` and
# `enum pci_ers_result`
_TAGGED = re.compile(r"^(struct|union|enum)\s+([A-Za-z_]\w*)\s*(\{|$)")
# a forward declaration of a tagged type; e.g. `struct pci_dev;`
_FORWARD = re.compile(r"^(struct|union|enum)\s+([A-Za-z_]\w*)\s*;")
# a typedef that ends on its line, group 1 the name it defines; e.g. `typedef
# unsigned int pci_ers_result_t;` gives pci_ers_result_t
_TYPEDEF = re.compile(r"^typedef\b.*\b([A-Za-z_]\w*)\s*;\s*$")
# a column-0 variable: optional type words, the name, optional array brackets,
# then `=` or `;`, group 1 the name; e.g. `int pcibios_last_bus = -1;` and
# `static const char * const pci_power_names[] = {` give pcibios_last_bus and
# pci_power_names
_VARIABLE = re.compile(
    r"^(?:[A-Za-z_][\w \t*]*?\b)?([A-Za-z_]\w*)(?:\[[^\]]*\])*\s*(=|;)"
)
# an object a macro defines: group 1 the macro, group 2 its arguments to the
# end of the line; e.g. `static DEFINE_MUTEX(pci_slot_mutex);` gives
# DEFINE_MUTEX and `pci_slot_mutex);`, and `TRACE_EVENT(mm_migrate_pages,`
# gives TRACE_EVENT
_MACRO_OBJECT = re.compile(
    r"^(?:static\s+)?(?:__?[a-z_]+\s+)*((?:DEFINE|DECLARE)_[A-Z0-9_]+|"
    r"TRACE_EVENT[A-Z_]*|[A-Z0-9_]+_HEAD)\s*\((.*)$"
    # DEFINE_STATIC_KEY_MAYBE(CONFIG_DEBUG_VM, name); the arguments run to the
    # matching parenthesis or, for a TRACE_EVENT that continues on the next
    # lines, to the end of the line; the same macros as anchors.py's shape
)


def _macro_args(inner):
    """The comma-separated arguments of a macro invocation whose text after `(`
    is inner, read to the parenthesis that closes it or to the end of the line
    when it does not close there (DEFINE_EVENT(class, name, TP_PROTO(...
    """
    depth = 0
    for i, ch in enumerate(inner):
        if ch == "(":
            depth += 1
        elif ch == ")":
            if depth == 0:
                inner = inner[:i]
                break
            depth -= 1
    return [arg.strip() for arg in inner.split(",") if arg.strip()]


_C_TYPE_WORDS = {
    "int",
    "long",
    "short",
    "char",
    "void",
    "bool",
    "unsigned",
    "signed",
    "float",
    "double",
    "struct",
    "union",
    "enum",
    "const",
    "volatile",
    "u8",
    "u16",
    "u32",
    "u64",
    "s8",
    "s16",
    "s32",
    "s64",
    "__u8",
    "__u16",
    "__u32",
    "__u64",
    "__s8",
    "__s16",
    "__s32",
    "__s64",
}
# a syscall definition: group 1 `COMPAT_` when present, group 2 the syscall's
# name; e.g. `SYSCALL_DEFINE4(migrate_pages, pid_t, pid,` gives migrate_pages
_SYSCALL = re.compile(r"^(COMPAT_)?SYSCALL_DEFINE\d\s*\(\s*([A-Za-z_]\w*)")


def _campaign_arches(spec):
    """The architecture directories a campaign documents: those its roots lie
    under and those its `architecture` text names; empty when it names none,
    and then no architecture is set aside.
    """
    arches = {
        str(r).split("/")[1]
        for r in spec.campaign.data.get("roots") or []
        if str(r).startswith("arch/")
        and str(r).count("/") >= 1
        and len(str(r).split("/")) > 1
    }
    # the words of the Campaign block's architecture text, each looked up among
    # the architecture names; e.g. `x86-64 with ACPI` gives x86-64, with and
    # ACPI
    for word in re.findall(
        r"[A-Za-z][\w-]*", str(spec.campaign.data.get("architecture") or "")
    ):
        if word.lower() in _ARCH_WORDS:
            arches.add(_ARCH_WORDS[word.lower()])
    return arches


def _indexed_definition(tree, path, number, name):
    """("definition", end) when the function index has `name` beginning at
    the line, else None."""
    for fn, start, end in _function_index(tree, path):
        if fn == name and start == number:
            return ("definition", end)
    return None


def _macro_object_kind(macro, args, name):
    """What a kernel macro makes of `name` among its arguments: a tracepoint,
    a declaration or a variable; None when the name is no object the macro
    defines."""
    if (
        name not in args
        or name.startswith("CONFIG_")
        or name in _C_TYPE_WORDS
        or name.endswith("_t")
        # a config option, a C type or a typedef among the arguments is no
        # object the macro defines
    ):
        return None
    # DEFINE_EVENT(class, name, ...): the class is another macro's object
    if macro.startswith("DEFINE_EVENT"):
        return (
            ("tracepoint", None) if len(args) > 1 and args[1] == name else None
        )
    # TRACE_EVENT(name, ...), DECLARE_EVENT_CLASS(name, ...)
    if "EVENT" in macro or "TRACE" in macro:
        return ("tracepoint", None) if args[0] == name else None
    return (
        ("declaration", None)
        if macro.startswith("DECLARE_")
        and not macro.startswith(
            (
                "DECLARE_WAIT_QUEUE_HEAD",
                "DECLARE_RWSEM",
                "DECLARE_COMPLETION",
            )
        )
        else ("variable", None)
    )


def _function_kind(tree, path, number, line, name):
    """What a line shaped like the first line of the function `name` is: a
    prototype, or a definition when the function index has it there."""
    if line.endswith(";") or line.startswith("extern"):
        return ("prototype", None)
    return _indexed_definition(tree, path, number, name) or (
        ("prototype", None)
        if path.endswith(".h")
        and not line.startswith(
            ("static", "inline", "__always_inline", "__maybe_unused")
        )
        else None
    )


def _definition_of(tree, path, number, text, name):
    """(kind, end) when the column-0 line number of path defines name: a
    function definition with the line its body closes on, a prototype or extern
    declaration, a macro, a struct, union or enum, a typedef, a variable or an
    object a kernel macro defines (DEFINE_PER_CPU, DEFINE_STATIC_KEY_MAYBE,
    LIST_HEAD; a DEFINE_EVENT is a tracepoint); None when the line only
    mentions the name (a parameter type, an EXPORT_SYMBOL, a call).
    """
    t = text.rstrip()
    if not t or t[:1].isspace() or t.startswith(("/", "*", "}")):
        return None
    found = _MACRO.match(t)
    if found:
        return ("macro", None) if found.group(1) == name else None
    if _FORWARD.match(t):
        return None
    found = _TAGGED.match(t)
    if found:
        return (found.group(1), None) if found.group(2) == name else None
    found = _TYPEDEF.match(t)
    if found:
        return ("typedef", None) if found.group(1) == name else None
    # an object a kernel macro defines: DEFINE_PER_CPU(type, name),
    # LIST_HEAD(name), DEFINE_EVENT(class, name, ...)
    found = _MACRO_OBJECT.match(t)
    if found:
        return _macro_object_kind(
            found.group(1), _macro_args(found.group(2)), name
        )
    # SYSCALL_DEFINE4(migrate_pages, ...) defines sys_migrate_pages, the name
    # the function index gives it
    syscall = _SYSCALL.match(t)
    if syscall:
        prefix = "compat_sys_" if syscall.group(1) else "sys_"
        if name != prefix + syscall.group(2):
            return None
        return _indexed_definition(tree, path, number, name)
    found = _DEFINITION.match(t)
    if found:
        if found.group(1) != name:
            return None
        return _function_kind(tree, path, number, t, name)
    found = _VARIABLE.match(t)
    if (
        found
        and found.group(1) == name
        and not t.startswith(("return", "goto", "case"))
    ):
        return ("declaration" if t.startswith("extern") else "variable", None)
    return None


def _under(path, roots):
    return any(
        path == r or path.startswith(r.rstrip("/") + "/") for r in roots
    )


def _def_path(definition):
    """The tree path of one research-pack definition line, `definition
    mm/vmscan.c:6516-6529 (14 lines)` or `member include/linux/mmzone.h:412:
    ...`."""
    # the path of a definition line, what stands before the first `:digits`;
    # e.g. `definition mm/vmscan.c:6516-6529 (14 lines)` gives mm/vmscan.c
    found = re.search(r"(\S+?):\d+", definition)
    return found.group(1) if found else ""


def _cap_defs(defs, roots):
    """A name defined more than PACK_DEFS_CAP times tree-wide keeps the
    definitions under the roots and a count of the rest: `flags` has fourteen
    thousand, and listing them made one brief half a megabyte on one line.
    """
    if len(defs) <= PACK_DEFS_CAP:
        return defs
    kept = [d for d in defs if _under(_def_path(d), roots)][:PACK_DEFS_CAP]
    return kept + [
        f"{len(defs) - len(kept)} more definitions tree-wide not listed, a"
        " name this common is read by hand with a pathspec"
    ]


def _grep_defs(tree, lines, name):
    """(defs, has_function) from `git grep -n` lines: the column-0 lines of .c,
    .h and .S files on which the name is the defined identifier, a function
    with its range, the other kinds with their line.
    """
    defs, has_function = [], False
    for line in lines:
        path, _, rest = line.partition(":")
        number, _, text = rest.partition(":")
        if not number.isdigit() or not path.endswith((".c", ".h", ".S")):
            continue
        kind = _definition_of(tree, path, int(number), text, name)
        if kind is None:
            continue
        if kind[0] == "definition":
            head = _head(tree, path, int(number))
            lines_of = kind[1] - head + 1
            label = "stub definition" if lines_of <= 2 else "definition"
            defs.append(f"{label} {path}:{head}-{kind[1]} ({lines_of} lines)")
            has_function = True
        else:
            defs.append(f"{kind[0]} {path}:{number}: {text.strip()[:100]}")
    return defs, has_function


def _aside(path, roots, arches):
    """Where a census line outside the printed set belongs: None for a line
    under the roots or in the rest of the tree's code, else the group it is
    summarized under (another architecture, tools/, Documentation/, samples/,
    scripts/)."""
    if _under(path, roots):
        return None
    for prefix in PACK_ASIDE:
        if path.startswith(prefix):
            return prefix
    if (
        arches
        and path.startswith("arch/")
        and path.split("/")[1] not in arches
    ):
        return "other architectures"
    return None


def _ctags_roots(tree, roots):
    """name -> [(kind, path, line, end)] from Universal Ctags over the roots:
    the typedefs, members, enumerators and tagged types the column-0 pass
    cannot see; empty without a Universal Ctags on PATH.
    """
    out = {}
    probe = subprocess.run(
        ["ctags", "--version"], capture_output=True, text=True
    )
    if probe.returncode != 0 or "Universal Ctags" not in probe.stdout:
        return out
    files = [
        r
        for r in roots
        if Path(tree, r).is_file() and r.endswith((".c", ".h"))
    ]
    if not files:
        return out
    done = subprocess.run(
        ["ctags", "--output-format=json", "--fields=+ne", "-o", "-", *files],
        cwd=tree,
        capture_output=True,
        text=True,
    )
    for line in done.stdout.splitlines():
        try:
            tag = json.loads(line)
        except ValueError:
            continue
        if tag.get("_type") != "tag":
            continue
        out.setdefault(tag.get("name"), []).append(
            (
                tag.get("kind"),
                tag.get("path"),
                tag.get("line"),
                tag.get("end"),
                tag.get("scope"),
            )
        )
    return out


def _second_pass(tree, roots, ctags_map, name):
    """Definitions of name the column-0 pass missed: Universal Ctags over the
    roots (a typedef whose name closes a multi-line definition, a struct
    member, an enumerator, a typedef'd struct), the Kconfig option `config
    name`, and the definition shapes outside the roots (a tagged type, a
    typedef, a macro) found by git grep over the tree's code.
    """
    defs = []
    for kind, path, line_no, end, scope in ctags_map.get(name, []):
        if kind in ("function",) and end:
            head = _head(tree, path, line_no)
            lines_of = end - head + 1
            defs.append(
                f'{"stub definition" if lines_of <= 2 else "definition"}'
                f" {path}:{head}-{end} ({lines_of} lines)"
            )
        elif kind == "member":
            defs.append(
                f"member {path}:{line_no} of"
                f' {str(scope or "").split(":")[-1] or "a struct"}'
            )
        elif kind:
            defs.append(f"{kind} {path}:{line_no}")
    for line in git(
        tree,
        "grep",
        "-n",
        "-E",
        "-e",
        r"^(menu)?config\s+" + re.escape(name) + r"\s*$",
        "--",
        "*Kconfig*",
        ok=(0, 1),
    ).split("\n"):
        if line:
            path, _, rest = line.partition(":")
            defs.append(
                f'kconfig {path}:{rest.partition(":")[0]}:'
                f' {rest.partition(":")[2].strip()}'
            )
    if not defs:
        shapes = (
            r"^(struct|union|enum)\s+" + re.escape(name) + r"\s*\{",
            r"^typedef\b.*\b" + re.escape(name) + r"\s*;",
            r"^\}\s*" + re.escape(name) + r"\s*;",
            r"^#\s*define\s+" + re.escape(name) + r"\b",
        )
        for shape in shapes:
            for line in git(
                tree,
                "grep",
                "-n",
                "-E",
                "-e",
                shape,
                "--",
                "*.c",
                "*.h",
                ok=(0, 1),
            ).split("\n"):
                if line and _aside(line.partition(":")[0], roots, ()) is None:
                    path, _, rest = line.partition(":")
                    defs.append(
                        "definition outside the roots"
                        f' {path}:{rest.partition(":")[0]}:'
                        f' {rest.partition(":")[2].strip()[:100]}'
                    )
    return defs[:6]


def _have_readtags():
    return any(
        os.access(Path(d, "readtags"), os.X_OK)
        for d in os.environ.get("PATH", "").split(os.pathsep)
        if d
    )


PACK_BULK = 64
# a name that is a plain identifier to its end, one that an alternation can ask
# for; e.g. `pci_walk_bridge`, and not `foo.bar`
_PLAIN_NAME = re.compile(r"[A-Za-z0-9_]+\Z")
# a word as `git grep -w` counts one in ASCII text; e.g. foo and bar_x in
# `foo(bar_x)`
_ASCII_WORD = re.compile(r"[A-Za-z0-9_]+")
# the head of a line `git grep -n` prints, `path:line:`, for a path git did not
# quote; e.g. the `mm/vmscan.c:6516:` of `mm/vmscan.c:6516:static void
# shrink_node(`
_GREP_HIT = re.compile(r'[^:"][^:]*:\d+:')
# the line `git grep` prints for a binary file, group 1 its path; e.g. `Binary
# file b.bin matches` gives b.bin
_GREP_BINARY = re.compile(r"Binary file ([^\"].*) matches\Z")


def _census_of(tree, name):
    """The lines `git grep -n -w <name>` prints over the whole tree."""
    return [
        hit
        for hit in git(tree, "grep", "-n", "-w", name, ok=(0, 1)).split("\n")
        if hit
    ]


def _shared_census(tree, names):
    """{name: lines} for plain identifiers, each list what `git grep -n -w
    <name>` prints for that name alone, from one grep that asks for them all;
    None when that grep fails or prints a line this function cannot place,
    and the caller then asks name by name.

    The names are asked as one pattern, an alternation: given one pattern a
    name, git looks ahead in the rest of a file for every pattern again at
    each hit, which took 19 minutes for 64 names where the alternation takes
    4 seconds. A plain identifier matches under -w exactly where it stands
    as a whole word, so a hit is the name's when the name is one of the
    words of the line's text. A binary file is reported without its line, so
    which names it holds is asked again of the binary files alone.
    """
    run = subprocess.run(
        ["git", "-C", tree, "grep", "-n", "-w", "-E", "-e", "|".join(names)],
        capture_output=True,
        text=True,
    )
    if run.returncode not in (0, 1):
        return None
    wanted = set(names)
    hits, binaries = [], []
    for hit in run.stdout.split("\n"):
        if not hit:
            continue
        text = _GREP_HIT.match(hit)
        if text:
            words = wanted.intersection(_ASCII_WORD.findall(hit, text.end()))
            hits.append((hit, words))
            continue
        binary = _GREP_BINARY.match(hit)
        if not binary:
            return None
        hits.append((hit, None))
        binaries.append(binary.group(1))
    in_binaries = {}
    if binaries:
        if len(binaries) > PACK_COMMON_CAP:
            return None
        paths = [":(literal)" + path for path in binaries]
        for name in names:
            in_binaries[name] = set(
                git(
                    tree,
                    "grep",
                    "-n",
                    "-w",
                    "-e",
                    name,
                    "--",
                    *paths,
                    ok=(0, 1),
                ).split("\n")
            )
    census = {name: [] for name in names}
    for hit, words in hits:
        for name in names if words is None else words:
            if words is not None or hit in in_binaries[name]:
                census[name].append(hit)
    return census


def _census(tree, names):
    """{name: lines}: for every name the lines `git grep -n -w <name>` prints
    over the whole tree, in its order, asked in one grep for up to PACK_BULK
    plain identifiers at a time instead of one grep a name."""
    census = {}
    plain = [name for name in dict.fromkeys(names) if _PLAIN_NAME.match(name)]
    for start in range(0, len(plain), PACK_BULK):
        shared = _shared_census(tree, plain[start : start + PACK_BULK])
        census.update(shared or {})
    for name in names:
        if name not in census:
            census[name] = _census_of(tree, name)
    return census


class _Pack:
    """What the research pack asks of one tree for one campaign: the roots,
    the architectures set aside, where the definitions come from, and the
    census of the names it was given."""

    def __init__(self, spec, tree, names=()):
        self.tree = tree
        self.census = _census(tree, names)
        self.tags = str(Path(tree, "tags"))
        self.use_tags = _have_readtags() and Path(self.tags).exists()
        self.roots = [str(r) for r in spec.campaign.data.get("roots") or []]
        self.arches = _campaign_arches(spec)
        self.ctags_map = (
            {} if self.use_tags else _ctags_roots(tree, self.roots)
        )

    def header(self):
        how = (
            "the definition lines from readtags on the tree's tags file, each"
            " entry's search pattern settled to its line on disk, and for a"
            " name the tags file lacks (ctags skips a function now and then)"
            " the column-0 lines of a `git grep -n -w` on which the name is"
            " the defined identifier, in the roots and then in the rest of the"
            " tree's code"
            if self.use_tags
            else (
                "the column-0 lines of a `git grep -n -w` on which the name is"
                " the defined identifier, in the roots and then in the rest of"
                " the tree's code (no readtags or tags file on this machine),"
                " and for a name that pass misses, Universal Ctags over the"
                " roots (typedefs, members, enumerators, typedef'd structs),"
                " the Kconfig files for `config name`, and the definition"
                " shapes outside the roots"
            )
        )
        aside = ", ".join(
            ["another architecture"] * bool(self.arches)
            + ["tools/", "Documentation/", "samples/", "scripts/"]
        )
        return (
            "- RESEARCH PACK, computed on the pinned tree for every name the"
            f" scope and the page's `symbols` give: {how}, a function's range"
            " from its definition line to the brace that closes its body (a"
            " body of one or two lines is a stub definition), and a tree-wide"
            " `git grep -n -w` census counted whole, printed for the roots and"
            " then the rest of the tree's code up to"
            f" {PACK_CENSUS_CAP} lines per name, with what lies under {aside}"
            " counted in one line and not printed (a name mentioned more than"
            f" {PACK_COMMON_CAP} times gets its count only, and a name defined"
            f" more than {PACK_DEFS_CAP} times keeps the definitions under the"
            " roots and a count of the rest), followed by the callers by"
            " function (the call sites, where the name stands before `(`; a"
            " function pointer, a SYSCALL_DEFINE argument or an EXPORT_SYMBOL"
            " counts in the census and not here), each caller named with its"
            " range so that a stage excerpt can be cut without another"
            " lookup. Every line is a hint to re-verify in one batched command"
            " before it is cited, never a citation; a range or a census that"
            " differs on the tree is corrected in the notes before use:"
        )

    def tag_definitions(self, name):
        """(definitions, whether one is a function) from the tags file."""
        defs, has_function = [], False
        for path, line_no, kind in _readtags(self.tree, self.tags, name):
            if kind == "f":
                end = _brace_end(self.tree, path, line_no)
                lines_of = end - line_no + 1
                # `{ }` or `{ return -ENODEV; }`, a header or weak stub
                label = "stub definition" if lines_of <= 2 else "definition"
                defs.append(
                    f"{label} {path}:{line_no}-{end} ({lines_of} lines)"
                )
                has_function = True
            else:
                lines = _file_lines(self.tree, path)
                text = (
                    lines[line_no - 1].strip()[:100]
                    if 0 < line_no <= len(lines)
                    else ""
                )
                defs.append(
                    f'{TAG_KIND_NAMES.get(kind, kind or "tag")}'
                    f" {path}:{line_no}: {text}"
                )
        return _cap_defs(_rank_defs(defs), self.roots), has_function

    def grep_definitions(self, name, census, defs):
        """(definitions, whether one is a function) with the definition lines
        of the census added: those under the roots, else, for a name that is
        not common, those in the rest of the tree's code."""
        roots = self.roots
        code = [
            hit
            for hit in census
            if _aside(hit.partition(":")[0], roots, self.arches) is None
        ]
        more, found_function = _grep_defs(
            self.tree,
            [hit for hit in code if _under(hit.partition(":")[0], roots)],
            name,
        )
        # then the rest of the tree's code, a common name excepted
        if not more and len(census) <= PACK_COMMON_CAP:
            more, found_function = _grep_defs(
                self.tree,
                [
                    hit
                    for hit in code
                    if not _under(hit.partition(":")[0], roots)
                ],
                name,
            )
        defs = _cap_defs(
            _rank_defs(defs + [d for d in more if d not in defs]), roots
        )
        return defs, found_function

    def census_lines(self, census):
        """(lines, counts): the census lines of the tree's code, those under
        the roots first, and how many lines lie under each group that is set
        aside."""
        shown, counts = [], {}
        for line in census:
            group = _aside(line.partition(":")[0], self.roots, self.arches)
            if group is None:
                shown.append(line)
            else:
                counts[group] = counts.get(group, 0) + 1
        in_roots = [
            hit
            for hit in shown
            if _aside(hit.partition(":")[0], (), ()) is None
            and any(
                hit.partition(":")[0] == r
                or hit.partition(":")[0].startswith(r.rstrip("/") + "/")
                for r in self.roots
            )
        ]
        return in_roots + [hit for hit in shown if hit not in in_roots], counts

    def caller_line(self, name, shown):
        """The line that names the functions calling `name`, each with its
        range and its call sites, or None when the census shows no call."""
        callers = {}
        for line in shown:
            path, _, rest = line.partition(":")
            number, _, text = rest.partition(":")
            if (
                not number.isdigit()
                or not path.endswith((".c", ".h"))
                or _comment_line(text)
                # a comment makes no call; a header's prototypes and macros
                # index no function, its static inlines do
            ):
                continue
            # the name followed by `(`, a call site; e.g. for pci_walk_bridge:
            # `pci_walk_bridge(bridge, cb, &status);`, and not `.cb =
            # pci_walk_bridge,`
            if (
                not re.search(r"\b" + re.escape(name) + r"\s*\(", text)
                or text.lstrip().startswith("#")
                or "EXPORT_SYMBOL" in text
                # a call site names the function before `(`; a SYSCALL_DEFINE
                # argument, a function pointer or an export does not
            ):
                continue
            holder = _enclosing(self.tree, path, int(number))
            if holder and holder[0] != name:
                callers.setdefault(
                    (path, holder[0], holder[1], holder[2]), []
                ).append(int(number))
        if not callers:
            return None
        shown_callers = list(callers.items())[:PACK_CALLERS_CAP]
        return (
            "    callers by function: "
            + "; ".join(
                f"{fn} {path}:{_head(self.tree, path, start)}-{end} (at :"
                + ", :".join(str(n) for n in nums)
                + ")"
                for (path, fn, start, end), nums in shown_callers
            )
            + (
                f"; ... {len(callers) - PACK_CALLERS_CAP} more functions"
                if len(callers) > PACK_CALLERS_CAP
                else ""
            )
        )

    def entry(self, name):
        """The lines of one name: its definitions and its count, then its
        census and its callers unless the name is common."""
        defs, has_function = [], False
        if self.use_tags:
            defs, has_function = self.tag_definitions(name)
        census = self.census.get(name)
        if census is None:
            census = _census_of(self.tree, name)
        # no tags file, a name the tags file lacks (ctags skips a function now
        # and then), or a tags file that knows only a stub or a prototype
        # (css_put: its definition stands behind CGROUP_REF_FN_ATTRS)
        if not any(d.startswith("definition ") for d in defs):
            defs, found_function = self.grep_definitions(name, census, defs)
            has_function = has_function or found_function
        if not defs and not self.use_tags:
            defs = _second_pass(self.tree, self.roots, self.ctags_map, name)
        head = (
            f"  {name}: "
            + (
                "; ".join(defs)
                if defs
                else "no definition found at the pinned tree"
            )
            + f"; mentions {len(census)} tree-wide"
        )
        if len(census) > PACK_COMMON_CAP:
            return [
                head
                + "; a name this common gets no census and no callers here,"
                " take its census by hand with a pathspec"
            ]
        shown, counts = self.census_lines(census)
        out = [head + (":" if shown or counts else "")]
        out += ["    " + line[:160] for line in shown[:PACK_CENSUS_CAP]]
        tail = []
        if len(shown) > PACK_CENSUS_CAP:
            tail.append(
                f"{len(shown) - PACK_CENSUS_CAP} more in the tree's code"
            )
        tail += [
            f"{n} under {g}"
            for g, n in sorted(counts.items(), key=lambda kv: -kv[1])
        ]
        if tail:
            out.append("    ... " + ", ".join(tail))
        callers = self.caller_line(name, shown) if has_function else None
        if callers:
            out.append(callers)
        return out


def research_pack(spec, page, tree, symbols):
    """The RESEARCH PACK of the prompt (guidelines/campaign/spec.md [prompt]):
    for every name the scope and the page's `symbols` give, the lines that
    define it, a function's range and a census, each a hint the writer
    re-verifies in one batched command. Definitions come from readtags on
    <tree>/tags when both exist, and for a name the tags file lacks, or when
    there is no tags file, from the column-0 lines of a git grep on which the
    name is the defined identifier, in the roots and then in the rest of the
    tree's code (a common name excepted). The census counts the whole tree,
    prints the roots and the rest of the tree's code up to a cap, and
    summarizes what lies under another architecture, tools/, Documentation/,
    samples/ or scripts/; a name mentioned more often than PACK_COMMON_CAP gets
    its count only, and a name defined more often than PACK_DEFS_CAP keeps the
    definitions under the roots and a count of the rest.
    """
    names = list(symbols)
    for group_ in spec.pages[page].data.get("symbols") or []:
        for name in group_.get("names") or []:
            bare = str(name).split()[-1]
            if bare not in names:
                names.append(bare)
    pack = _Pack(spec, tree, names)
    out = [pack.header()]
    if not names:
        out.append("  the scope names no backticked symbol")
    for name in names:
        out += pack.entry(name)
    return out


def _quoted(fences, sources):
    """The bodies of fences, each fence recorded among the sources."""
    sources.extend(f"{f!r}" for f in fences)
    return [f.body for f in fences]


def _scope_lines(spec, page, sources, gaps):
    out = [
        "MISSION. The scope, verbatim from the campaign spec (any line number"
        " in it is a hint; the disk is ground truth, and a hint you cannot"
        " reproduce is reported, never written around):",
        "",
    ]
    out += _quoted(spec.scopes.get(page, []), sources)
    if page not in spec.scopes:
        gaps.append(f"no kg:scope fence for {page}")
        out.append("GAP: the spec carries no scope for this page.")
    out.append("")
    return out


def _page_note_lines(spec, page, sources):
    out = [
        "Notes for this page, facts from the spec, each a hint to re-verify:"
    ]
    if spec.notes_page.get(page):
        out += _quoted(spec.notes_page[page], sources)
    else:
        out.append("- none recorded")
    out.append("")
    return out


def _other_note_lines(spec, page, mentions, own, sources):
    """The lines of other pages' notes and other clusters' notes that name
    this page or a symbol of its scope."""
    others = [
        f
        for p, fences in spec.notes_page.items()
        if p != page
        for f in fences
        if mentions.search(f.body)
    ]
    others += [
        f
        for name, fences in spec.notes_cluster.items()
        if name not in own
        for f in fences
        if mentions.search(f.body)
    ]
    if not others:
        return []
    out = [
        "Notes of other pages and clusters that name this page or a symbol"
        " of its scope (facts settled elsewhere that bind here; each a"
        " hint to re-verify):"
    ]
    seen = set()
    for f in others:
        lines = [
            row for row in f.body.split("\n") if mentions.search(row)
        ] or [f.body]
        # a ledger attached to two clusters prints once
        fresh = [row for row in lines if row.strip() not in seen]
        seen.update(row.strip() for row in lines)
        if not fresh:
            continue
        out.append(f"  from {f!r}:")
        out.extend("  " + row for row in fresh)
        sources.append(f"{f!r}")
    out.append("")
    return out


def _seam_lines(spec, mentions, own, sources):
    """The sentences of other clusters' boundary statements that name this
    page or a symbol of its scope."""
    found = []
    for name, f in spec.boundaries.items():
        if name in own:
            continue
        # cuts a boundary statement into sentences: after a period, at
        # whitespace that a capital, a backtick or a bracket follows; e.g.
        # "portdrv owns the framework. `pcie_do_recovery` is a seam." gives two
        # sentences, and `owns err.c; edr owns edr.c` is not cut
        hits = [
            sentence.strip()
            for sentence in re.split(r"(?<=\.)\s+(?=[A-Z`\[])", f.body)
            if mentions.search(sentence)
        ]
        if hits:
            found.append((name, f, hits))
    if not found:
        return []
    out = [
        "Seams of other clusters that name this page or a symbol of its"
        " scope (the sentences of their boundary statements, verbatim):"
    ]
    for name, f, hits in found:
        out.append(f"  {name}:")
        out.extend("  " + h for h in hits)
        sources.append(f"{f!r}")
    out.append("")
    return out


def _cluster_lines(spec, clusters, sources):
    if not clusters:
        return [
            "This page belongs to no cluster in the spec; the boundary rules"
            " that bind every page are under CAMPAIGN FACTS.",
            "",
        ]
    out = []
    for c in clusters:
        name = str(c.data.get("name"))
        out.append(
            f"Cluster: {name}. Its pages:"
            f' {", ".join(str(p) for p in c.data.get("pages") or [])}.'
        )
        if name in spec.boundaries:
            out.append("The boundary statement, a floor, verbatim:")
            out += _quoted([spec.boundaries[name]], sources)
        else:
            out.append("The cluster has no boundary statement in the spec.")
        if spec.notes_cluster.get(name):
            out.append("Notes for every page of the cluster:")
            out += _quoted(spec.notes_cluster[name], sources)
        out.append("")
    return out


def _assignment_lines(spec, page, clusters, symbols):
    rows = [
        (s, o, c)
        for s, o, c in spec.assignments()
        if c in clusters or o == page or s in symbols
    ]
    out = [
        "Assignments from the spec's assign tables: every row of this page's"
        " clusters, and any row elsewhere that names this page or a symbol of"
        " its scope (symbol: primary page; another assignment does not prevent"
        " cataloging a symbol here when needed):"
    ]
    if rows:
        for s, o, c in sorted(rows):
            out.append(f'  {s}: {o}  [{c.data.get("name")}]')
    else:
        out.append("  none")
    out.append("")
    return out


# the campaign fields the first line of CAMPAIGN FACTS states, with the
# words it introduces each by
FACT_FIELDS = (
    ("architecture", "Architecture scope"),
    ("configs", "CONFIG assumptions to state where behavior depends on them"),
    ("tooling", "Research tooling"),
)


def _in_tree(path, tree):
    """A path of the spec as a prompt prints it: under the tree unless it is
    absolute."""
    path = str(path)
    return path if Path(path).is_absolute() else str(Path(tree, path))


def _fact_value(value, tree):
    """One campaign field as CAMPAIGN FACTS prints it: a list joined by `; `,
    a mapping as `key value` pairs with the paths of its tools resolved
    against the tree, anything else as it stands."""
    if isinstance(value, list):
        return "; ".join(str(v) for v in value)
    if not isinstance(value, dict):
        return str(value)
    parts = []
    for k, v in value.items():
        if isinstance(v, dict):
            text = ", ".join(
                f"{kk} {_in_tree(vv, tree) if kk == 'path' else vv}"
                for kk, vv in v.items()
            )
        elif k == "tags":
            text = _in_tree(v, tree)
        else:
            text = str(v)
        parts.append(f"{k} {text}")
    return "; ".join(parts)


def _tree_fact_line(data, tree):
    version, commit = str(data["version"]), str(data["commit"])
    facts = [
        f"Documented tree: {tree}, version {version}, commit {commit}. Every"
        " Elixir link uses"
        f" https://elixir.bootlin.com/linux/{version}/source/...."
    ]
    for key, label in FACT_FIELDS:
        if data.get(key):
            facts.append(f"{label}: {_fact_value(data[key], tree)}.")
    return "- " + " ".join(facts)


def _binding_lines(spec, page, sources):
    """The section-six heading, the four fences that bind every page and the
    campaign-wide notes."""
    data = spec.campaign.data
    page_s6 = spec.pages[page].data.get("section6")
    if page_s6 is not None:
        out = [
            f"- Section-six heading: {page_s6} (this page's value; the"
            f' campaign\'s is {data.get("section6", "omit")}).'
        ]
    else:
        out = [f'- Section-six heading: {data.get("section6", "omit")}.']
    for kind, label in (
        ("bans", "Project-specific bans"),
        ("mandatory", "Mandatory page features"),
        ("cautions", "Write-time cautions"),
        ("rules", "Rules that bind every page"),
    ):
        if kind in spec.single:
            out.append(f"- {label}, verbatim from the campaign spec:")
            out += _quoted([spec.single[kind]], sources)
        else:
            out.append(f"- {label}: none recorded in the spec.")
    if spec.notes_campaign:
        out.append("- Campaign-wide notes, facts every prompt carries:")
        out += _quoted(spec.notes_campaign, sources)
    return out


def _reuse_lines(data, page, skill, gaps):
    """The figure reuse pointers of the page; a source git cannot read in the
    glossary checkout is a gap."""
    pointers = [
        r
        for r in data.get("reuse") or []
        if isinstance(r, dict) and page in (r.get("pages") or [])
    ]
    if not pointers:
        return ["- Figure reuse pointers for this page: none."]
    out = [
        "- Figure reuse pointers for this page (Scope decisions on prior"
        " figures; a reused figure is redrawn under [registers] and"
        " re-verified bit by bit on the pinned tree):"
    ]
    for r in pointers:
        source = str(r.get("source"))
        try:
            git(skill, "cat-file", "-e", source)
            state = (
                f"readable: `git show {source}` inside the glossary checkout"
            )
        except CampaignError:
            state = "NOT readable in this repository"
            gaps.append(
                f'reuse source {source} for figure {r.get("figure")} is'
                " not readable"
            )
        out.append(
            f'  - {r.get("figure")}: source {source} ({state});'
            f' verification note: {r.get("note", "none")}'
        )
    return out


# the campaign fields the content states in words of its own
STATED_FIELDS = (
    "campaign",
    "dir",
    "tree",
    "version",
    "commit",
    "roots",
    "exclude",
    "section6",
    "architecture",
    "configs",
    "tooling",
    "reuse",
)


def _extra_field_lines(data):
    extra = {k: v for k, v in data.items() if k not in STATED_FIELDS}
    if not extra:
        return []
    return [
        "- Additional campaign fields, preserved as written:",
        yaml.safe_dump(extra, sort_keys=False, allow_unicode=True).rstrip(
            "\n"
        ),
    ]


def _page_content(
    spec, page, skill, tree, hints=False, sources=None, gaps=None
):
    """The lines of a page's campaign content: MISSION (the scope, the notes,
    the seams, the cluster, the assignments) and CAMPAIGN FACTS (the pin, the
    architecture, the configuration, the bans, the mandatory features, the
    cautions, the rules, the campaign-wide notes, the reuse pointers and,
    under hints, the research pack). No page on disk is read for it: the
    content of a page is the same whatever else has been written. No
    directive: what a process tells its writer is the process's own.
    """
    sources = [] if sources is None else sources
    gaps = [] if gaps is None else gaps
    data = spec.campaign.data
    clusters = spec.clusters_of(page)
    symbols = spec.scope_symbols(page)
    mentions = mention_pattern(page, symbols)
    own = {str(c.data.get("name")) for c in clusters}
    out = _scope_lines(spec, page, sources, gaps)
    out += _page_note_lines(spec, page, sources)
    out += _other_note_lines(spec, page, mentions, own, sources)
    out += _seam_lines(spec, mentions, own, sources)
    out += _cluster_lines(spec, clusters, sources)
    out += _assignment_lines(spec, page, clusters, symbols)
    out.append("CAMPAIGN FACTS:")
    out.append(_tree_fact_line(data, tree))
    out += _binding_lines(spec, page, sources)
    out += _reuse_lines(data, page, skill, gaps)
    out += _extra_field_lines(data)
    if hints:
        out.extend(research_pack(spec, page, tree, symbols))
    out.append("")
    return out


def content(spec, page, skill, tree, hints=False):
    """(text, gaps): the page's campaign content alone
    (guidelines/campaign/spec.md [prompt]), for a process that assembles its
    own writer prompt: MISSION, CAMPAIGN FACTS, the spec's prompt fences and a
    SOURCES line.
    """
    if page not in spec.pages:
        raise CampaignError(f"{page} has no page block in {spec.path}")
    gaps, sources = [], []
    out = _page_content(spec, page, skill, tree, hints, sources, gaps)
    if spec.prompts.get(page):
        out.append("ADDITIONS, from the spec's prompt fences, verbatim:")
        out.append("")
        for f in spec.prompts[page]:
            out.append(f.body)
            sources.append(f"{f!r}")
        out.append("")
    data = spec.campaign.data
    today = datetime.date.today().isoformat()
    out.append(
        f"SOURCES. Assembled {today} by tools/campaign/run.py content from"
        f" {shown(spec.path, skill)} ("
        + "; ".join(sources)
        + f"); tree {tree} at commit"
        f' {data["commit"]}. Gaps: '
        + ("; ".join(gaps) if gaps else "none")
        + "."
    )
    return "\n".join(out) + "\n", gaps


# ------------------------------------------------------------------------ show


def show(spec, page):
    if page not in spec.pages:
        raise CampaignError(f"{page} has no page block in {spec.path}")
    out = []

    def dump(f):
        out.append(f"--- {f!r}")
        out.append(f.body)
        out.append("")

    dump(spec.pages[page])
    for f in (
        spec.scopes.get(page, [])
        + spec.notes_page.get(page, [])
        + spec.prompts.get(page, [])
    ):
        dump(f)
    for c in spec.clusters_of(page):
        name = str(c.data.get("name"))
        dump(c)
        if name in spec.boundaries:
            dump(spec.boundaries[name])
        for f in spec.notes_cluster.get(name, []):
            dump(f)
    if spec.campaign:
        dump(spec.campaign)
    for kind in SINGLE_MD:
        if kind in spec.single:
            dump(spec.single[kind])
    for f in spec.notes_campaign:
        dump(f)
    return "\n".join(out)


# ------------------------------------------------------------- note and assign


def _write(spec, lines):
    Path(spec.path).write_text("\n".join(lines), encoding="utf-8")


def note(spec, target, text, cluster=None, campaign=False):
    """Append a note to the page's, the cluster's or the campaign's notes
    fence, creating the fence after its anchor when none exists; a
    campaign-wide note anchors after the last campaign-level fence. A note
    carries no date (campaign-spec.md [protocol])."""
    line = f"- {text}"
    lines = list(spec.lines)
    if campaign:
        fences = spec.notes_campaign
        level = [
            f
            for f in spec.fences
            if f.kind in ("campaign", "bans", "cautions", "mandatory", "rules")
            and not f.attrs
        ]
        if not level:
            raise CampaignError(
                "no campaign block to anchor a campaign-wide note"
            )
        anchor = max(level, key=lambda f: f.end)
        header = "```md kg:notes"
    elif cluster:
        if cluster not in spec.cluster_names():
            raise CampaignError(f"no cluster named {cluster}")
        fences = spec.notes_cluster.get(cluster, [])
        anchor = spec.boundaries.get(cluster) or next(
            c for c in spec.clusters if str(c.data.get("name")) == cluster
        )
        header = f"```md kg:notes cluster={cluster}"
    else:
        if target not in spec.pages:
            raise CampaignError(f"{target} has no page block")
        fences = spec.notes_page.get(target, [])
        anchor = (spec.scopes.get(target) or [spec.pages[target]])[0]
        header = f"```md kg:notes page={target}"
    if fences:
        f = fences[0]
        lines.insert(f.end - 1, line)
        where = f"appended to {f!r}"
    else:
        lines[anchor.end : anchor.end] = ["", header, line, "```"]
        where = f"new notes fence after {anchor!r}"
    _write(spec, lines)
    return where


def assign(spec, symbol, owner, cluster=None, force=False):
    if owner not in spec.pages:
        raise CampaignError(f"{owner} has no page block")
    if cluster:
        targets = [
            c for c in spec.clusters if str(c.data.get("name")) == cluster
        ]
        if not targets:
            raise CampaignError(f"no cluster named {cluster}")
    else:
        targets = spec.clusters_of(owner)
        if not targets:
            raise CampaignError(
                f"{owner} belongs to no cluster; name one with --cluster"
            )
    target = targets[0]
    previous = [(o, c) for s, o, c in spec.assignments() if s == symbol]
    lines = list(spec.lines)
    if previous:
        old_owner, old_cluster = previous[0]
        if old_owner == owner:
            return f"`{symbol}` is already assigned to {owner}"
        if not force:
            raise CampaignError(
                f"`{symbol}` is assigned to {old_owner} in cluster"
                f' {old_cluster.data.get("name")}; use --force to move it'
            )
        for n in range(old_cluster.start, old_cluster.end - 1):
            # the assign row of this symbol: indentation, the symbol, a colon;
            # e.g. `  aer_probe: rc/portdrv/aer` for the symbol aer_probe
            if re.match(rf"^\s+{re.escape(symbol)}:\s", lines[n] + " "):
                # the row's owner, everything from the colon on, replaced; e.g.
                # `  aer_probe: rc/portdrv/aer` becomes `  aer_probe:
                # rc/portdrv/dpc`
                lines[n] = re.sub(r":\s.*$", f": {owner}", lines[n])
                _write(spec, lines)
                return (
                    f"`{symbol}` moved from {old_owner} to {owner} (was in"
                    f' cluster {old_cluster.data.get("name")})'
                )
        raise CampaignError(
            f"could not find the assign row of `{symbol}` in cluster"
            f' {old_cluster.data.get("name")}; is the table written inline?'
        )
    # 0-based indices of body lines are start..end-2
    for n in range(target.start, target.end - 1):
        # the `assign:` line of a table written one row a line; e.g. `assign:`
        # alone on its line
        if re.match(r"^assign:\s*$", lines[n]):
            lines.insert(n + 1, f"  {symbol}: {owner}")
            _write(spec, lines)
            return (
                f"`{symbol}` assigned to {owner} in cluster"
                f' {target.data.get("name")}'
            )
        # an assign table written inline, which the tool does not edit; e.g.
        # `assign: {aer_probe: rc/portdrv/aer}`
        if re.match(r"^assign:\s*\{", lines[n]):
            raise CampaignError(
                f'cluster {target.data.get("name")} writes `assign` inline;'
                " expand it to one row per line first"
            )
    lines[target.end - 1 : target.end - 1] = [
        "assign:",
        f"  {symbol}: {owner}",
    ]
    _write(spec, lines)
    return (
        f'`{symbol}` assigned to {owner} in cluster {target.data.get("name")}'
        " (assign table created)"
    )


# -------------------------------------------------------------------- selftest


def interface():
    """The commands and the long options of the command line, read from its
    parser: what the tool's README has to name."""
    names, options = [], set()
    # argparse keeps a parser's arguments in `_actions` and offers no public
    # way to list them
    for action in command_line()._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                names.append(name)
                for argument in sub._actions:
                    options.update(argument.option_strings)
        else:
            options.update(action.option_strings)
    return names, sorted(
        o for o in options if o.startswith("--") and o != "--help"
    )


def unnamed(readme):
    """The commands and the options the tool's README does not name. The
    standard names no tool, so that file is where an option is learned; one it
    leaves out is one nobody finds."""
    path = Path(readme)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    names, options = interface()
    missing = [
        name
        for name in names
        # a code span that opens with the command; e.g. "`validate <spec>`"
        # for validate and "`selftest`" for selftest, and not "the fences to
        # show" for show
        if not re.search(rf"`{name}[ `]", text)
    ]
    missing += [
        option
        for option in options
        # the option as a whole word; e.g. "`--out <file>`" for --out, and not
        # "--outline"
        if not re.search(rf"(?<![\w-]){re.escape(option)}(?![\w-])", text)
    ]
    return missing


def selftest(skill):
    import unittest

    campaign = Path(skill, "tools", "campaign")
    suite = unittest.defaultTestLoader.discover(
        str(campaign / "tests"),
        pattern="test_campaign*.py",
        top_level_dir=str(campaign),
    )
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    failures = len(result.failures) + len(result.errors)
    named = set()
    documents = [
        *Path(skill, "guidelines").rglob("*.md"),
        *Path(skill, "tools").rglob("README.md"),
        Path(skill, "README.md"),
        Path(skill, "CLAUDE.md"),
        *Path(skill, "skills").glob("*/SKILL.md"),
    ]
    for path in documents:
        if path.exists():
            # every subcommand a document names after the tool's path; e.g.
            # `tools/campaign/run.py validate <spec>` gives validate
            named.update(
                re.findall(
                    r"tools/campaign/run\.py ([a-z]+)\b",
                    path.read_text(encoding="utf-8"),
                )
            )
    unknown = sorted(w for w in named if w not in SUBCOMMANDS)
    print(
        "subcommands the documents name:"
        f' {", ".join(sorted(named & set(SUBCOMMANDS))) or "none"}; names with'
        f' no subcommand: {", ".join(unknown) or "none"}'
    )
    missing = unnamed(Path(skill, "tools", "campaign", "README.md"))
    print(
        "commands and options tools/campaign/README.md does not name:"
        f' {", ".join(missing) or "none"}'
    )
    passed = result.testsRun and not failures and not unknown and not missing
    return 0 if passed else 1


# ------------------------------------------------------------------------ main


def command_line():
    """The parser of the command line: the two global options and one
    subparser per command."""
    parser = argparse.ArgumentParser(
        prog="tools/campaign/run.py", description=__doc__.split("\n\n")[0]
    )
    parser.add_argument(
        "--glossary-checkout",
        dest="skill",
        default=SKILL,
        help=(
            "the checkout of this repository to work in (default: the one"
            " holding this file)"
        ),
    )
    parser.add_argument(
        "--tree",
        default=None,
        help=(
            "the kernel checkout (default: TREE_ROOT, the kernel checkout"
            " whose .claude directory holds this repository)"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("validate")
    s.add_argument("spec")
    s.add_argument("--regions", action="store_true")
    s.add_argument("--checklist", action="store_true")
    s.add_argument(
        "--anchors",
        action="store_true",
        help="ask the pinned commit whether every scope anchor exists",
    )
    s = sub.add_parser("show")
    s.add_argument("spec")
    s.add_argument("page")
    s = sub.add_parser("index")
    s.add_argument("spec")
    s.add_argument(
        "--dir", help="the docs directory (default: the Campaign block)"
    )
    s.add_argument("--symbol")
    s.add_argument("--page")
    s.add_argument("--conflicts", action="store_true")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("content")
    s.add_argument("spec")
    s.add_argument("page")
    s.add_argument("--hints", action="store_true")
    s.add_argument("--out")
    s.add_argument("--allow-gaps", action="store_true")
    s = sub.add_parser("note")
    s.add_argument("spec")
    s.add_argument(
        "page", help="the page, or '-' with --cluster or --campaign"
    )
    s.add_argument("text")
    s.add_argument("--cluster")
    s.add_argument(
        "--campaign", action="store_true", help="a campaign-wide note"
    )
    s = sub.add_parser("assign")
    s.add_argument("spec")
    s.add_argument("symbol")
    s.add_argument("page")
    s.add_argument("--cluster")
    s.add_argument("--force", action="store_true")
    sub.add_parser("selftest")
    return parser


def report_anchors(spec, tree, warnings):
    """Ask the tree for every scope anchor and print the answer; a missing
    anchor joins the warnings."""
    commit = str(spec.campaign.data.get("commit", ""))
    checked, outside, missing = anchors(spec, tree)
    for page, name, where in outside:
        print(f"anchor outside the roots: {page}: `{name}` in {where}")
    for page, name in missing:
        warnings.append(
            f"{page}: scope anchor `{name}` is not in the tree at"
            f" {commit[:12]}"
        )
        print(f"warning: {warnings[-1]}")
    print(
        f"anchors: {checked} names asked of the tree at"
        f" {commit[:12]}; {len(outside)} outside the roots,"
        f" {len(missing)} missing"
    )


def cmd_validate(args, spec, skill, errors, warnings):
    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"error: {e}")
    if args.regions:
        print("\n".join(regions(spec)))
    if args.checklist:
        print("\n".join(checklist(spec)))
    if args.anchors and spec.campaign is not None:
        report_anchors(spec, tree_root(spec, args.tree), warnings)
    print(
        f"{shown(spec.path, skill)}: {len(spec.fences)} kg fences,"
        f" {len(spec.pages)} pages, {len(spec.clusters)} clusters,"
        f" {len(spec.assignments())} assignments; {len(errors)}"
        f" errors, {len(warnings)} warnings"
    )
    return 1 if errors else 0


def cmd_index(args, spec, skill):
    by_symbol, by_page = index(skill, args.dir or spec.dir, spec.exclude)
    if args.json:
        print(
            json.dumps({"by_symbol": by_symbol, "by_page": by_page}, indent=1)
        )
    elif args.symbol:
        held_by = ", ".join(holders(by_symbol, args.symbol))
        print(f"{args.symbol}: {held_by or 'no page on disk catalogs it'}")
    elif args.page:
        for name, where in by_page.get(args.page, []):
            others = holders(by_symbol, name, exclude=args.page)
            print(
                f"{name}  ({where})  also:"
                f' {", ".join(others) if others else "-"}'
            )
        if args.page not in by_page:
            print("\n".join(seams(spec, args.page, by_symbol)))
    elif args.conflicts:
        rows = conflicts(spec, by_symbol)
        print(
            "\n".join(rows)
            if rows
            else (
                "no symbol is cataloged by two pages, and every"
                " assignment matches the disk"
            )
        )
    else:
        for name in sorted(by_symbol):
            print(f'{name}: {", ".join(holders(by_symbol, name))}')
    print(
        f"-- {len(by_page)} pages,"
        f" {sum(len(e) for e in by_page.values())} entries,"
        f" {len(by_symbol)} symbols under"
        f" docs/{args.dir or spec.dir}/",
        file=sys.stderr,
    )
    return 0


def cmd_content(args, spec, skill, warnings):
    text, gaps = content(
        spec,
        args.page,
        skill,
        tree_root(spec, args.tree),
        hints=args.hints,
    )
    if gaps and not args.allow_gaps:
        for g in gaps:
            print(f"gap: {g}", file=sys.stderr)
        print(
            "the content was not written; resolve the gaps or pass"
            " --allow-gaps to carry them as named gaps",
            file=sys.stderr,
        )
        return 1
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(
            f"{args.out}: {len(text)} bytes"
            + (f"; {len(gaps)} gap(s) carried" if gaps else ""),
            file=sys.stderr,
        )
    else:
        sys.stdout.write(text)
    # a warning that names this page: the page id with no word character or
    # hyphen after it; e.g. for rc/portdrv/dpc: `md kg:scope rc/portdrv/dpc:
    # ...`, and not a warning on rc/portdrv/dpc-events
    own = [
        w
        for w in warnings
        if re.search(re.escape(args.page) + r"(?![\w-])", w)
    ]
    for w in own:
        print(f"warning: {w}", file=sys.stderr)
    rest = len(warnings) - len(own)
    if rest:
        print(
            f'{rest} other warning{"s" if rest != 1 else ""} on the'
            " spec; campaign validate lists them",
            file=sys.stderr,
        )
    return 0


def cmd_edit(args, spec):
    """`note` or `assign`: edit the spec, then say what no longer
    validates."""
    if args.command == "note":
        print(
            note(
                spec,
                None if args.campaign or args.cluster else args.page,
                args.text,
                cluster=args.cluster,
                campaign=args.campaign,
            )
        )
    else:
        print(
            assign(
                spec,
                args.symbol,
                args.page,
                cluster=args.cluster,
                force=args.force,
            )
        )
    errors, _warnings = validate(load(spec.path))
    for e in errors:
        print(f"error after the edit: {e}", file=sys.stderr)
    return 1 if errors else 0


def execute(args, skill):
    """One command; its exit status. Every command but `validate` refuses a
    spec that does not validate."""
    if args.command == "selftest":
        return selftest(skill)
    spec = load(args.spec)
    errors, warnings = validate(spec)
    if args.command == "validate":
        return cmd_validate(args, spec, skill, errors, warnings)
    if errors:
        for e in errors:
            print(f"error: {e}", file=sys.stderr)
        print(
            f"{shown(spec.path, skill)} does not validate; fix the errors"
            " first",
            file=sys.stderr,
        )
        return 1
    if args.command == "show":
        print(show(spec, args.page))
        return 0
    if args.command == "index":
        return cmd_index(args, spec, skill)
    if args.command == "content":
        return cmd_content(args, spec, skill, warnings)
    return cmd_edit(args, spec)


def main(argv=None):
    args = command_line().parse_args(argv)
    skill = str(absolute(args.skill))
    try:
        status = execute(args, skill)
    except CampaignError as error:
        raise SystemExit(f"tools/campaign/run.py: {error}")
    if status:
        raise SystemExit(status)


if __name__ == "__main__":
    main()
