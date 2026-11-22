"""tools/campaign/run.py, tested on a campaign this skill ships and nothing
invented. Every World is a shared clone of the skill repository at HEAD
(campaigns/v7.2-pci.md, its pages under docs/pci/rc/ and the repository's
history); the states under test are made by editing that clone, and a removed
revision or a reuse source under test names a commit of that clone, so no tag
and no history beyond HEAD is needed; the tree is the pinned kernel checkout
when KG_TREE or the checkout this repository lives in provides one, and the
tests that read the tree skip otherwise."""

import contextlib
import io
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

if not __package__:
    # run as a script: make the repository's packages importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.campaign import run as campaign
from tools.checkout import tree_default

TOOLS = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
SKILL = os.path.dirname(TOOLS)

SPEC = os.path.join(SKILL, "campaigns", "v7.2-pci.md")
DIR = "pci"
NAME = "v7.2-pci"  # the campaign name, which also names its workspace
PIN = "8d3ae59288f1e7d58d76558a6ee96d533bc5019f"
SUBSYSTEM = "PCIe"  # the entry of guidelines/subsystems.md with this dir
PAGES = "docs/pci/rc"  # what a World checks out: the pages of both clusters
CLUSTER = "Port services cluster"
OTHER_CLUSTER = "Native hotplug cluster"
PAGE = (  # on disk, with a notes fence, named by no reuse pointer
    "rc/portdrv/error-recovery"
)
SIBLING = (  # on disk, same cluster, with a notes fence of its own
    "rc/portdrv/dpc"
)
OTHER = "rc/portdrv/edr"  # in the cluster, never created on disk
ASSIGNED = "aer_probe"  # an assign row of the cluster, owned by another page
ASSIGNED_OWNER = "rc/portdrv/aer"
UNASSIGNED = "report_resume"  # a scope name of PAGE in no assign table
FILE = "drivers/pci/pcie/err.c"
FUNC = "pcie_do_recovery"  # defined in FILE, assigned to PAGE, its alone
CALLED = "pci_walk_bridge"  # static in FILE, where FUNC calls it
STRUCT = "pci_error_handlers"  # assigned to PAGE, defined in STRUCT_FILE
STRUCT_FILE = "include/linux/pci.h"
MEMBER = "pci_error_handlers.error_detected"
EXPORTED = "pcie_port_service_register"  # exported; Documentation/ names it
EXPORTED_FILE = "drivers/pci/pcie/portdrv.c"
OUTSIDE = "acpi_ec_space_handler"  # defined outside the campaign's roots
OUTSIDE_FILE = "drivers/acpi/ec.c"
ENTRY = (
    "- [`'\\<{name}\\>':'{path}'`](https://elixir.bootlin.com/linux/v7.2/sour"
    "ce/{path}#L{line}):"
    " {text}"
)
BARE_ENTRY = (
    "- [`'{name}'`](https://elixir.bootlin.com/linux/v7.2/source/{path}#L{lin"
    "e}):"
    " {text}"
)


def kernel_tree():
    """The pinned tree: KG_TREE, else the kernel checkout whose .claude
    directory holds this repository, the rule of tools/checkout.py; None when
    neither holds the subsystem."""
    root, _how = tree_default(SKILL)
    if root and os.path.exists(os.path.join(root, FILE)):
        return os.path.abspath(root)
    return None


TREE = kernel_tree()


def git(cwd, *args):
    return subprocess.run(
        [
            "git",
            "-C",
            cwd,
            "-c",
            "user.name=kg",
            "-c",
            "user.email=kg@example.org",
            *args,
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def run_main(argv):
    """(exit status, standard output, standard error) of one run of the tool,
    as a shell sees them: a message the tool leaves with is printed and
    counts as status 1."""
    out, err = io.StringIO(), io.StringIO()
    code = 0
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            campaign.main(argv)
        except SystemExit as stop:
            code = stop.code or 0
            if isinstance(code, str):
                print(code, file=sys.stderr)
                code = 1
    return code, out.getvalue(), err.getvalue()


class World:
    """A shared clone of the skill with the test campaign and its pages."""

    def __init__(self):
        self.root = tempfile.mkdtemp()
        self.skill = os.path.join(self.root, "skill")
        git(
            self.root,
            "clone",
            "-q",
            "--shared",
            "--no-checkout",
            SKILL,
            "skill",
        )
        # Keep this test's real campaign fixture; unrelated docs need not be
        # checked out.
        git(
            self.skill,
            "sparse-checkout",
            "set",
            "--cone",
            "--sparse-index",
            "guidelines",
            "tools",
            "campaigns",
            PAGES,
        )
        git(self.skill, "checkout", "-q")
        self.head = git(self.skill, "rev-parse", "HEAD").strip()
        self.spec = os.path.join(self.skill, "campaigns", NAME + ".md")
        self.page = self.path(PAGE)
        # the prompt prints the tree's path; only --hints reads the tree
        self.tree = TREE or self.skill

    def path(self, page):
        return os.path.join(self.skill, "docs", DIR, page + ".md")

    def load(self):
        return campaign.load(self.spec)

    def text(self):
        return Path(self.spec).read_text(encoding="utf-8")

    def write(self, text):
        Path(self.spec).write_text(text, encoding="utf-8")

    def edit(self, old, new, count=1):
        text = self.text()
        assert old in text, old
        self.write(text.replace(old, new, count))

    def remove(self, page):
        git(
            self.skill,
            "rm",
            "-q",
            os.path.relpath(self.path(page), self.skill),
        )

    def reuse(self, source, figure="the recovery steps"):
        """Give the Campaign block one reuse pointer, the first of its list
        when it has one (guidelines/campaign/spec.md [campaign])."""
        row = (
            f'  - {{figure: "{figure}", source: "{source}", note: "a test'
            f' pointer", pages: [{PAGE}]}}\n'
        )
        text = self.text()
        # the `reuse:` line of the Campaign block, with whatever follows the
        # key on its line; e.g. `reuse:    # figure pointers`
        head = re.search(r"^reuse:.*\n", text, re.M)
        if head:
            self.write(text[: head.end()] + row + text[head.end() :])
        else:
            self.edit(
                "section6: REGISTERS\n", "section6: REGISTERS\nreuse:\n" + row
            )

    def catalog(
        self,
        page,
        name,
        path,
        line,
        text="an entry copied from the sibling that owns it",
        bare=False,
    ):
        """Append one COVERAGE entry, traced or bare (page-model.md [catalog]),
        to a page of the clone."""
        where = self.path(page)
        body = Path(where).read_text(encoding="utf-8")
        start = body.index("\n## COVERAGE\n") + len("\n## COVERAGE\n")
        end = body.find("\n## ", start)
        body = (
            body[:end]
            + "\n"
            + (BARE_ENTRY if bare else ENTRY).format(
                name=name, path=path, line=line, text=text
            )
            + body[end:]
        )
        Path(where).write_text(body, encoding="utf-8")

    def pages_on_disk(self):
        return sum(
            len([f for f in files if f.endswith(".md") and f != "README.md"])
            for _r, _d, files in os.walk(os.path.join(self.skill, "docs", DIR))
        )

    def close(self):
        shutil.rmtree(self.root)


class Reader(unittest.TestCase):

    def test_the_campaign_reads_and_every_page_has_one_scope(self):
        spec = campaign.load(SPEC)
        self.assertIn(CLUSTER, spec.cluster_names())
        self.assertIn(CLUSTER, spec.boundaries)
        self.assertIn(PAGE, spec.notes_page)
        self.assertGreater(len(spec.pages), 50)
        self.assertTrue(
            all(len(spec.scopes.get(p, [])) == 1 for p in spec.pages)
        )
        self.assertTrue(
            any("yaml kg:campaign" in r for r in campaign.regions(spec))
        )
        symbols = spec.scope_symbols(PAGE)
        for name in (STRUCT, FUNC, CALLED, UNASSIGNED):
            self.assertIn(name, symbols)
        spec.scopes[PAGE][0].lines.append(
            "[errata 2026-10-01: `in_scope` renamed]"
        )
        self.assertIn("in_scope", spec.scope_symbols(PAGE))

    def test_a_quoted_fence_is_not_read(self):
        # the scope fence of PAGE as the plan writes it, from the line that
        # opens it to the line that closes it; e.g. "```md kg:scope
        # page=rc/portdrv/error-recovery\nthe recovery state machine: ...\n```"
        fence = re.search(
            rf"```md kg:scope page={PAGE}\n.*?\n```",
            Path(SPEC).read_text(encoding="utf-8"),
            re.S,
        ).group(0)
        path = tempfile.NamedTemporaryFile(
            "w", suffix=".md", delete=False, encoding="utf-8"
        )
        path.write("# doc\n\n````markdown\n" + fence + "\n````\n")
        path.close()
        try:
            spec = campaign.load(path.name)
            self.assertEqual(spec.fences, [])
            self.assertEqual(spec.pages, {})
        finally:
            os.unlink(path.name)


class Validation(unittest.TestCase):

    def variant(self, edit):
        text = edit(Path(SPEC).read_text(encoding="utf-8"))
        f = tempfile.NamedTemporaryFile(
            "w", suffix=".md", delete=False, encoding="utf-8"
        )
        f.write(text)
        f.close()
        self.addCleanup(os.unlink, f.name)
        return campaign.validate(campaign.load(f.name))

    def test_the_campaign_validates_and_its_warnings_are_the_shorthands(self):
        spec = campaign.load(SPEC)
        errors, warnings = campaign.validate(spec)
        self.assertEqual(errors, [])
        fences = sum(
            1
            for p in spec.pages
            for f in spec.scopes[p]
            if campaign.shorthands(f.body)
        )
        self.assertEqual(
            len([w for w in warnings if "suffix shorthand" in w]), fences
        )

    def test_the_campaign_block_agrees_with_the_subsystem_map(self):
        """The Campaign block's dir and section6 are the subsystem entry's dir
        and section6_heading said again; a disagreement is an error, a dir with
        no entry a warning, and a checkout without the map checks nothing.
        """
        world = World()
        self.addCleanup(world.close)
        errors, warnings = campaign.validate(world.load())
        self.assertFalse(
            [e for e in errors if "subsystems.md" in e]
            + [w for w in warnings if "subsystems.md" in w]
        )
        world.edit("section6: REGISTERS\n", "section6: METHODS\n")
        errors, _warnings = campaign.validate(world.load())
        self.assertTrue(
            any(
                f"section6 `METHODS` disagrees with the {SUBSYSTEM} entry" in e
                for e in errors
            ),
            errors,
        )
        world.edit("section6: METHODS\n", "section6: REGISTERS\n")
        world.edit(f"dir: {DIR}\n", "dir: nowhere\n")
        errors, warnings = campaign.validate(world.load())
        self.assertFalse([e for e in errors if "subsystems.md" in e])
        self.assertTrue(
            any(
                "no entry of guidelines/subsystems.md has dir `nowhere`" in w
                for w in warnings
            ),
            warnings,
        )
        self.assertEqual(campaign.subsystem_map(tempfile.gettempdir()), None)

    def test_errors(self):
        cases = {
            "pin": lambda t: t.replace(f"commit: {PIN}\n", ""),
            "short sha": lambda t: t.replace(PIN, PIN[:7]),
            "second block": lambda t: t.replace(
                f"page: {SIBLING}\n", f"page: {PAGE}\n"
            ),
            "no scope": lambda t: t.replace(
                f"```md kg:scope page={SIBLING}", "```md"
            ),
            "unknown kind": lambda t: t.replace(
                "```md kg:cautions", "```md kg:caution"
            ),
            "twice": lambda t: t.replace(
                f"  {ASSIGNED}: {ASSIGNED_OWNER}\n",
                f"  {ASSIGNED}: {ASSIGNED_OWNER}\n  {ASSIGNED}: {PAGE}\n",
            ),
            "unknown page": lambda t: t.replace(
                f"```md kg:notes page={PAGE}\n",
                "```md kg:notes page=rc/nope\n",
            ),
            "duplicate key": lambda t: t.replace(
                "tag: curated\n", "tag: curated\ntag: requested\n", 1
            ),
            "old request tag": lambda t: t.replace(
                "tag: curated\n", "tag: prompt\n", 1
            ),
            "bad tag": lambda t: t.replace(
                "tag: curated\n", "tag: optional-ish\n", 1
            ),
            "bad section6": lambda t: t.replace(
                f"page: {PAGE}\n", f"page: {PAGE}\nsection6: TABLES\n", 1
            ),
            "no boundary name": lambda t: t.replace(
                f"```md kg:boundary cluster={CLUSTER}", "```md kg:boundary"
            ),
            "exclude not a list": lambda t: t.replace(
                "exclude: [appendix]", "exclude: appendix", 1
            ),
            "exclude escapes the directory": lambda t: t.replace(
                "exclude: [appendix]", "exclude: [../other]", 1
            ),
        }
        for name, edit in cases.items():
            errors, _warnings = self.variant(edit)
            self.assertTrue(errors, name)

    def test_a_suffix_shorthand_is_warned_once_per_fence(self):
        opener = f"```md kg:scope page={PAGE}\n"
        _errors, warnings = self.variant(
            lambda t: t.replace(opener, opener + "`_alloc_x`, `_remove_y`, ")
        )
        own = [
            w
            for w in warnings
            if f"md kg:scope {PAGE}" in w and "suffix shorthand" in w
        ]
        self.assertEqual(len(own), 1)
        self.assertIn("`_alloc_x`, `_remove_y`", own[0])
        _errors, warnings = self.variant(
            lambda t: t.replace(opener, opener + "`__pci_walk_x`, `_OSC`, ")
        )
        self.assertFalse(
            any("_OSC" in w or "__pci_walk_x" in w for w in warnings)
        )

    def test_an_errata_bracket_in_a_scope_is_warned(self):
        opener = f"```md kg:scope page={PAGE}\n"
        _errors, warnings = self.variant(
            lambda t: t.replace(
                opener, opener + "[errata 2026-10-01: `pcie_x` is `pcie_y`] "
            )
        )
        own = [
            w
            for w in warnings
            if f"md kg:scope {PAGE}" in w and "`[errata …]`" in w
        ]
        self.assertEqual(len(own), 1)
        self.assertIn("1 `[errata …]` bracket,", own[0])

    @unittest.skipUnless(TREE, "the pinned tree is not available")
    def test_anchors_are_asked_of_the_pinned_commit(self):
        """`--anchors` asks the pinned commit for every name a scope fence
        carries: a name found nowhere is a warning naming its page, a name
        found only outside the roots is listed with its file.
        """
        opener = f"```md kg:scope page={PAGE}\n"
        text = (
            Path(SPEC)
            .read_text(encoding="utf-8")
            .replace(
                opener,
                opener
                + f"`pcie_no_such_anchor_xyz`, `{OUTSIDE}` (named at the"
                " seam), ",
            )
        )
        f = tempfile.NamedTemporaryFile(
            "w", suffix=".md", delete=False, encoding="utf-8"
        )
        f.write(text)
        f.close()
        self.addCleanup(os.unlink, f.name)
        spec = campaign.load(f.name)
        checked, outside, missing = campaign.anchors(spec, TREE, pages=[PAGE])
        self.assertEqual(checked, len(spec.scope_symbols(PAGE)))
        self.assertEqual(missing, [(PAGE, "pcie_no_such_anchor_xyz")])
        self.assertEqual(outside, [(PAGE, OUTSIDE, OUTSIDE_FILE)])
        self.assertIn(FUNC, spec.scope_symbols(PAGE))

    @unittest.skipUnless(TREE, "the pinned tree is not available")
    def test_many_anchors_are_answered_in_one_pass_as_one_by_one(self):
        """Above BULK_ANCHORS names the roots are read once for all of them;
        the answer is the one a `git grep` per name gives: the same names
        missing, the same names outside the roots.
        """
        opener = f"```md kg:scope page={PAGE}\n"
        text = (
            Path(SPEC)
            .read_text(encoding="utf-8")
            .replace(
                opener,
                opener + f"`pcie_no_such_anchor_xyz`, `{OUTSIDE}`,"
                f" `{FUNC[:-1]}` (a prefix of a name is no word), ",
            )
        )
        f = tempfile.NamedTemporaryFile(
            "w", suffix=".md", delete=False, encoding="utf-8"
        )
        f.write(text)
        f.close()
        self.addCleanup(os.unlink, f.name)
        spec = campaign.load(f.name)
        one_by_one = campaign.anchors(spec, TREE, pages=[PAGE])
        limit = campaign.BULK_ANCHORS
        self.addCleanup(setattr, campaign, "BULK_ANCHORS", limit)
        campaign.BULK_ANCHORS = 0
        self.assertEqual(
            campaign.anchors(spec, TREE, pages=[PAGE]), one_by_one
        )
        self.assertIn((PAGE, FUNC[:-1]), one_by_one[2])
        roots = [str(r) for r in spec.campaign.data.get("roots")]
        held = campaign._held_by_roots(
            TREE,
            [FUNC, FUNC[:-1], OUTSIDE, "not an identifier"],
            roots,
        )
        self.assertEqual(held, {FUNC})

    def test_checklist_names_what_is_empty(self):
        rows = campaign.checklist(campaign.load(SPEC))
        page = next(r for r in rows if r.startswith(PAGE + ":"))
        self.assertIn("scope,", page)
        self.assertIn(f"cluster {CLUSTER}", page)
        self.assertIn("reuse EMPTY", page)
        self.assertIn("campaign bans: present", rows)


class Index(unittest.TestCase):

    def setUp(self):
        self.world = World()
        self.addCleanup(self.world.close)

    def test_a_bare_entry_is_indexed_by_its_url(self):
        name = "PCI_ERS_RESULT_NO_AER_DRIVER"
        self.world.catalog(SIBLING, name, STRUCT_FILE, 936, bare=True)
        by_symbol, by_page = campaign.index(self.world.skill, DIR)
        self.assertEqual(by_symbol[name], [(SIBLING, STRUCT_FILE)])
        self.assertIn((name, STRUCT_FILE), by_page[SIBLING])

    def test_a_member_entry_claims_no_owner(self):
        before = campaign.conflicts(
            self.world.load(), campaign.index(self.world.skill, DIR)[0]
        )
        for page in (PAGE, SIBLING):  # one member, cataloged on two pages
            self.world.catalog(page, MEMBER, STRUCT_FILE, 951, bare=True)
        by_symbol, by_page = campaign.index(self.world.skill, DIR)
        self.assertNotIn(MEMBER, by_symbol)
        self.assertNotIn(MEMBER.split(".")[1], by_symbol)
        self.assertNotIn(MEMBER, [n for n, _ in by_page[PAGE]])
        self.assertEqual(
            campaign.conflicts(self.world.load(), by_symbol), before
        )

    def test_who_catalogs_what_and_the_conflicts(self):
        by_symbol, by_page = campaign.index(self.world.skill, DIR)
        self.assertIn((PAGE, FILE), by_symbol[FUNC])
        # the `'\\<struct pci_error_handlers\\>'` entry, keyed by its bare name
        self.assertIn((PAGE, STRUCT_FILE), by_symbol[STRUCT])
        self.assertNotIn("struct " + STRUCT, by_symbol)
        # member entries `A.B` are not indexed: the `controller.x` entries of
        # the other cluster's pages
        for member in (
            "pending_events",
            "button_work",
            "ist_running",
        ):
            self.assertNotIn(member, by_symbol)
        self.assertTrue(
            campaign.member_key(MEMBER)
            and campaign.member_key("bool hotplug_active")
            and campaign.member_key("const struct pci_error_handlers *eh")
        )
        self.assertFalse(
            campaign.member_key("struct " + STRUCT)
            or campaign.member_key(FUNC)
            or campaign.member_key(FUNC + "()")
        )
        self.assertIn(FUNC, [n for n, _ in by_page[PAGE]])
        before = campaign.conflicts(self.world.load(), by_symbol)
        # the sibling takes a copy of the owner's entry: one symbol, one file,
        # two pages
        self.world.catalog(SIBLING, FUNC, FILE, 210)
        by_symbol, _ = campaign.index(self.world.skill, DIR)
        self.assertEqual(campaign.holders(by_symbol, FUNC), [SIBLING, PAGE])
        rows = campaign.conflicts(self.world.load(), by_symbol)
        self.assertIn(f"{FUNC} ({FILE}): cataloged by {SIBLING}, {PAGE}", rows)
        # Additional catalogers are context; the primary assignment remains
        # valid.
        self.assertTrue(
            any(
                r.startswith(
                    f"{FUNC}: primary page {PAGE}; cataloged on disk by"
                )
                for r in rows
            )
        )
        self.assertEqual(len(rows), len(before) + 2)
        # one name in two files is two symbols shown with their files
        here, there = "drivers/pci/pcie/aer.c", "drivers/pci/pcie/dpc.c"
        self.world.catalog(PAGE, "probe_x", here, 10)
        self.world.catalog(SIBLING, "probe_x", there, 10)
        by_symbol, _ = campaign.index(self.world.skill, DIR)
        holders = campaign.holders(by_symbol, "probe_x")
        self.assertIn(f"{PAGE} ({here})", holders)
        self.assertIn(f"{SIBLING} ({there})", holders)
        self.assertEqual(
            campaign.holders(by_symbol, "probe_x", where=there),
            [f"{SIBLING} ({there})"],
        )

    def test_an_excluded_subdirectory_is_nobodys_cataloger(self):
        """The Campaign block's `exclude` names subdirectories of docs/<dir>/
        whose pages the index skips (guidelines/campaign/spec.md [campaign],
        [index]): the campaign excludes its appendix, and an annex named
        beside it is on disk and catalogs nothing.
        """
        old = os.path.join(self.world.skill, "docs", DIR, "annex", "old.md")
        os.makedirs(os.path.dirname(old))
        # a copy of the owner's page, its catalog included
        shutil.copy(self.world.path(PAGE), old)
        self.assertEqual(self.world.load().exclude, ["appendix"])
        by_symbol, by_page = campaign.index(
            self.world.skill, DIR, self.world.load().exclude
        )
        self.assertIn("annex/old", by_page)
        self.assertIn(("annex/old", FILE), by_symbol[FUNC])
        self.world.edit("exclude: [appendix]", "exclude: [appendix, annex]")
        spec = self.world.load()
        self.assertEqual(spec.exclude, ["appendix", "annex"])
        self.assertEqual(campaign.validate(spec)[0], [])
        by_symbol, by_page = campaign.index(
            self.world.skill, DIR, spec.exclude
        )
        self.assertNotIn("annex/old", by_page)
        self.assertEqual(campaign.holders(by_symbol, FUNC), [PAGE])
        code, out, _ = run_main(
            [
                "--glossary-checkout",
                self.world.skill,
                "index",
                self.world.spec,
                "--symbol",
                FUNC,
            ]
        )
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), f"{FUNC}: {PAGE}")

    def test_an_absent_page_lists_its_scope_and_the_catalogers(self):
        self.world.remove(SIBLING)
        symbols = self.world.load().scope_symbols(SIBLING)
        code, out, _ = run_main(
            [
                "--glossary-checkout",
                self.world.skill,
                "index",
                self.world.spec,
                "--page",
                SIBLING,
            ]
        )
        self.assertEqual(code, 0)
        self.assertIn(
            f"{SIBLING}: not on disk under docs/{DIR}/; its scope names"
            f" {len(symbols)} symbols, cataloged today by:",
            out,
        )
        by_symbol, _ = campaign.index(self.world.skill, DIR)
        for name in symbols:
            self.assertIn(
                f"  {name}:"
                f' {", ".join(campaign.holders(by_symbol, name)) or "-"}',
                out,
            )
        self.assertIn("  dpc_handler: ", out)
        _code, out, _ = run_main(
            [
                "--glossary-checkout",
                self.world.skill,
                "index",
                self.world.spec,
                "--page",
                "rc/nowhere",
            ]
        )
        self.assertIn(
            f"rc/nowhere: not on disk under docs/{DIR}/, and the spec names"
            " no scope symbol for it",
            out,
        )
        self.world.edit(
            f"```md kg:scope page={SIBLING}\n",
            f"```md kg:scope page={SIBLING}\n`_probe_x`, ",
        )
        _code, out, _ = run_main(
            [
                "--glossary-checkout",
                self.world.skill,
                "index",
                self.world.spec,
                "--page",
                SIBLING,
            ]
        )
        self.assertIn(
            "  _probe_x: - (suffix shorthand; the floor cannot resolve it)",
            out,
        )


class Content(unittest.TestCase):
    """guidelines/campaign/spec.md [prompt]: the page's content, what the spec
    and the disk say about one page and nothing about how to write it, for a
    process that assembles its own writer prompt.
    """

    def setUp(self):
        self.world = World()
        self.addCleanup(self.world.close)

    def content(self, page=PAGE, **kw):
        spec = self.world.load()
        errors, _ = campaign.validate(spec)
        self.assertEqual(errors, [])
        return campaign.content(
            spec, page, self.world.skill, self.world.tree, **kw
        )

    def test_every_fence_reaches_the_content(self):
        self.world.write(
            self.world.text()
            + f"\n```md kg:prompt page={PAGE}\nFigures: the recovery steps,"
            " the votes and the reset as one sequence.\n```\n"
        )
        # the campaign's clusters carry no notes fence: one is made here, and
        # a research tool is named where the Campaign block names none
        shared = f"a cluster note: the services reach `{FUNC}` through a seam"
        campaign.note(self.world.load(), None, shared, cluster=CLUSTER)
        if "\ntooling:" not in self.world.text():
            self.world.edit(
                "section6: REGISTERS\n",
                "section6: REGISTERS\ntooling:\n  symbol_index: {tool:"
                " codebase-memory-mcp, project: the tree root's}\n",
            )
        text, gaps = self.content()
        self.assertEqual(gaps, [])
        for expected in (
            "MISSION.",
            "CAMPAIGN FACTS:",
            "SOURCES.",
            # the scope, verbatim
            f"the recovery state machine: `{FUNC}`, `{CALLED}`",
            "`pci_dev_set_io_state` has a fourth caller",  # a page note
            "error-recovery owns err.c",  # the cluster boundary
            shared,  # the cluster note
            "no vendor-specific PCIe mechanism or controller behavior",  # bans
            (  # mandatory features
                "every PCIe concept named in prose is paired with its kernel"
                " representation"
            ),
            "The x86 path is one of several",  # cautions
            "Rule 2, A floor, never a fence",  # rules
            "Figures: the recovery steps, the votes",  # the prompt fence
            # an assign row of the cluster
            f"  {ASSIGNED}: {ASSIGNED_OWNER}  [{CLUSTER}]",
            # the tooling mapping
            "Research tooling: symbol_index tool codebase-memory-mcp",
            f"version v7.2, commit {PIN}",
        ):
            self.assertIn(expected, text, expected)
        for absent in (
            "OPERATION:",
            "YOUR WORKSHEET",
            "YOUR EVIDENCE",
            "YOUR SCRATCH",
            "DIRECTIVES.",
            "MANDATORY READING",
            "WRITING RULES.",
            "<!-- page model -->",
            "<!-- rule: ",
            "<SKILL_DIR>",
            "<commit8>",
        ):
            self.assertNotIn(absent, text, absent)
        order = [
            text.index(m)
            for m in (
                "MISSION.",
                "Cluster: ",
                "CAMPAIGN FACTS:",
                "ADDITIONS,",
                "SOURCES.",
            )
        ]
        self.assertEqual(order, sorted(order), order)

    def test_assigned_elsewhere_still_allows_local_catalog_coverage(
        self,
    ):
        campaign.assign(self.world.load(), FUNC, SIBLING, force=True)
        self.world.catalog(SIBLING, FUNC, FILE, 210)
        before = self.world.text()
        text, gaps = self.content()
        self.assertEqual(gaps, [])
        self.assertIn(
            "symbol: primary page; another assignment does not prevent"
            " cataloging a symbol here when needed",
            text,
        )
        self.assertIn(f"  {FUNC}: {SIBLING}  [{CLUSTER}]", text)
        self.assertNotIn("not cataloged here", text)
        self.assertEqual(self.world.text(), before)
        self.assertEqual(
            dict((s, o) for s, o, _ in self.world.load().assignments())[FUNC],
            SIBLING,
        )

    def test_a_page_section_six_overrides_the_campaign(self):
        """A page block may carry its own section-six heading (subsystems.md's
        note line); without it the campaign's value stands alone, and with it
        the content carries it and names the campaign's value beside it.
        """
        text, _gaps = self.content()
        self.assertIn("Section-six heading: REGISTERS.", text)
        self.world.edit(
            f"page: {PAGE}\ntag: curated\n",
            f"page: {PAGE}\ntag: curated\nsection6: INTERFACES\n",
        )
        text, _gaps = self.content()
        self.assertIn(
            "Section-six heading: INTERFACES (this page's value; the"
            " campaign's is REGISTERS).",
            text,
        )

    def test_the_reuse_pointer_is_read_from_a_revision(self):
        source = f"{self.world.head}:docs/{DIR}/{PAGE}.md"
        self.world.reuse(source)
        text, gaps = self.content()
        self.assertEqual([g for g in gaps if "reuse" in g], [])
        self.assertIn(f"the recovery steps: source {source} (readable", text)
        self.world.edit(source, f"archive/missing:docs/{DIR}/{PAGE}.md")
        text, gaps = self.content()
        self.assertEqual(len([g for g in gaps if "reuse" in g]), 1)
        self.assertIn("not readable", next(g for g in gaps if "reuse" in g))
        self.assertIn(
            "reuse source archive/missing", text.rsplit("Gaps: ", 1)[1]
        )
        code, _out, err = run_main(
            [
                "--glossary-checkout",
                self.world.skill,
                "--tree",
                self.world.tree,
                "content",
                self.world.spec,
                PAGE,
            ]
        )
        self.assertEqual(code, 1)
        self.assertIn("gap:", err)
        code, out, _err = run_main(
            [
                "--glossary-checkout",
                self.world.skill,
                "--tree",
                self.world.tree,
                "content",
                self.world.spec,
                PAGE,
                "--allow-gaps",
            ]
        )
        self.assertEqual(code, 0)
        self.assertIn("SOURCES.", out)

    def test_notes_and_seams_of_other_pages_naming_this_page_are_carried(self):
        note = (
            f"error-recovery.md walks `{FUNC}` whole; this page shows the"
            " call at the stage"
        )
        campaign.note(self.world.load(), SIBLING, note)
        text, _ = self.content()
        self.assertIn(
            "Notes of other pages and clusters that name this page or a symbol"
            " of its scope",
            text,
        )
        self.assertIn(note, text)
        opener = f"```md kg:boundary cluster={OTHER_CLUSTER}\n"
        self.world.edit(
            opener,
            opener
            + f"Seams: `{FUNC}` (error-recovery owns; the slot page cites"
            " the call). ",
        )
        text, _ = self.content()
        self.assertIn(
            "Seams of other clusters that name this page or a symbol of its"
            " scope",
            text,
        )
        self.assertIn(
            f"Seams: `{FUNC}` (error-recovery owns; the slot page cites the"
            " call).",
            text,
        )

    def test_the_content_reads_no_page_on_disk(self):
        """guidelines/campaign/spec.md [prompt]: no page of docs/<dir>/ is
        read for a page's content, which names no cataloger and no sibling
        and is the same whatever else has been written."""
        before, _ = self.content()
        for gone in (
            "Catalogers on disk",
            "catalogs it",
            "Sibling pages",
            "absent from disk",
            "scanned for catalogers",
        ):
            self.assertNotIn(gone, before, gone)
        # a sibling catalogs a symbol of the scope, then leaves the disk
        self.world.catalog(SIBLING, FUNC, FILE, 210)
        cataloged, _ = self.content()
        self.assertEqual(cataloged, before)
        os.remove(self.world.path(SIBLING))
        removed, _ = self.content()
        self.assertEqual(removed, before)
        with unittest.mock.patch.object(
            campaign, "index", side_effect=AssertionError("docs/ was read")
        ):
            unread, _ = self.content()
        self.assertEqual(unread, before)

    def test_scope_names_follow_the_page_model(self):
        self.assertEqual(
            campaign.symbol_name("tb_port_enable(port)"), "tb_port_enable"
        )
        self.assertEqual(campaign.symbol_name("struct tb_switch"), "tb_switch")
        self.assertEqual(campaign.symbol_name("struct tb_nhi *nhi"), "nhi")
        self.assertEqual(campaign.symbol_name("tmu_rates[]"), "tmu_rates")
        gives = {
            "tb_switch": "tb_switch",
            "struct tb_switch": "tb_switch",
            "enum  tb_xdp_type": "tb_xdp_type",
            "tb_port_enable(port)": "tb_port_enable",
            "tb_port_at()": "tb_port_at",
            "WARN_ON(!adev)": "WARN_ON",
            'TB_SERVICE("stream", 1)': "TB_SERVICE",
            "tmu_rates[]": "tmu_rates",
            "groups[MAX_GROUPS + 1]": "groups",
            "_OSC": "_OSC",
            "__tb_approve_xdomain_paths": "__tb_approve_xdomain_paths",
        }
        for text, name in gives.items():
            self.assertEqual(campaign.scope_name(text), name, text)
        for text in (
            "XDOMAIN_*",
            "*_noirq",
            "CS_0/1/2",
            "tb_port_read/write(.., TB_CFG_HOPS, 2 * hop, 2)",
            "sizeof(struct tb_cm)",
            "hotplug_active = false",
            "RING_FLAG_FRAME | RING_FLAG_E2E",
            "2 * hopid",
            "xd->lock",
            ".driver.pm = &nhi_pm_ops",
            "foo(x)->bar",
            "struct tb_nhi *nhi",
            "-EINVAL",
            "pci=noaer",
            "Link:",
            "tb_port_enable(port",
        ):
            self.assertIsNone(campaign.scope_name(text), text)

    @unittest.skipUnless(
        TREE,
        "no kernel tree: set KG_TREE or run the tests inside the checkout",
    )
    def test_hints_come_from_the_pinned_tree(self):
        """guidelines/campaign/spec.md [prompt]: the research pack names every
        scope symbol and every `symbols` name with its definition and a
        tree-wide census, as hints."""
        self.world.edit(
            f"page: {PAGE}\n",
            f"page: {PAGE}\nsymbols:\n  - {{file: {FILE}, names:"
            f" [{FUNC}]}}\n",
        )
        text, _ = self.content(hints=True)
        self.assertIn("- RESEARCH PACK, computed on the pinned tree", text)
        # the pack's head line of FUNC, which opens with its definition in
        # FILE; e.g. `  pcie_do_recovery: definition
        # drivers/pci/pcie/err.c:210-294 (85 lines); ...`
        self.assertRegex(
            text,
            rf"\n  {FUNC}: (definition|definition-shaped) "
            + re.escape(FILE)
            + r":\d+",
        )
        # the head line ends with the tree-wide count; e.g. `pcie_do_recovery:
        # definition ...; mentions 11 tree-wide:`
        self.assertRegex(text, rf"{FUNC}: .*; mentions \d+ tree-wide:\n")
        # a census line of the defining file, wherever git grep orders it
        self.assertRegex(
            text, r"\n    " + re.escape(FILE) + rf":\d+:.*\b{FUNC}\b"
        )
        # a scope name of the fixture, packed beside the `symbols` name
        self.assertRegex(text, rf"\n  {STRUCT}: ")
        # each caller with its range: FUNC calls CALLED, a scope name, in FILE
        self.assertRegex(
            text,
            r"\n    callers by function: .*\w+ "
            + re.escape(FILE)
            + r":\d+-\d+ \(at :\d+",
        )

    @unittest.skipUnless(
        TREE,
        "no kernel tree: set KG_TREE or run the tests inside the checkout",
    )
    def test_pack_definitions_name_the_defined_identifier(self):
        """guidelines/campaign/spec.md [prompt]: a definition line is one on
        which the name is the defined identifier, the function's own line with
        its range or the struct's opening line; a parameter type or an
        EXPORT_SYMBOL that mentions the name is no definition."""
        self.world.edit(
            f"page: {PAGE}\n",
            f"page: {PAGE}\nsymbols:\n  - {{file: {EXPORTED_FILE}, names:"
            f" [{EXPORTED}]}}\n  - {{file: {STRUCT_FILE}, names:"
            f" [{STRUCT}]}}\n",
        )
        text, _ = self.content(hints=True)
        # past the assign rows, which name the same symbols
        text = text[text.index("- RESEARCH PACK") :]
        # the pack's head line of EXPORTED, group 1 what follows the name; e.g.
        # `  pcie_port_service_register: definition
        # drivers/pci/pcie/portdrv.c:586-595 (10 lines); prototype ...`
        head = re.search(rf"\n  {EXPORTED}: (.*)", text).group(1)
        # the head opens with the function's definition and its range; e.g.
        # `definition drivers/pci/pcie/portdrv.c:586-595 (10 lines)`
        self.assertRegex(
            head,
            r"^definition "
            + re.escape(EXPORTED_FILE)
            + r":\d+-\d+ \(\d+ lines\)",
        )
        self.assertNotIn("EXPORT_SYMBOL", head)
        # the pack's head line of STRUCT, group 1 what follows the name
        head = re.search(rf"\n  {STRUCT}: (.*)", text).group(1)
        # the head opens with the line that opens the struct; e.g. `struct
        # include/linux/pci.h:949: struct pci_error_handlers {`
        self.assertRegex(
            head,
            r"^struct "
            + re.escape(STRUCT_FILE)
            + rf":\d+: struct {STRUCT} \{{",
        )
        # an object of the struct's type is not its definition
        self.assertNotIn("pcie_portdrv_err_handler", head)

    @unittest.skipUnless(
        TREE,
        "no kernel tree: set KG_TREE or run the tests inside the checkout",
    )
    def test_pack_census_sets_other_trees_aside(self):
        """guidelines/campaign/spec.md [prompt]: the census prints the roots
        and the rest of the tree's code; what lies under another architecture,
        tools/, Documentation/, samples/ or scripts/ is counted in one line.
        """
        self.world.edit(
            f"page: {PAGE}\n",
            f"page: {PAGE}\nsymbols:\n  - {{file: {EXPORTED_FILE}, names:"
            f" [{EXPORTED}]}}\n",
        )
        text, _ = self.content(hints=True)
        text = text[text.index("- RESEARCH PACK") :]
        block = text[text.index(f"\n  {EXPORTED}: ") :]
        # the next name's head; census lines are indented deeper
        nxt = re.search(r"\n  \S", block[1:])
        block = block[: nxt.start() + 1] if nxt else block
        # a census line of the defining file, indented four spaces; e.g. `
        # drivers/pci/pcie/portdrv.c:586:int pcie_port_service_register(`
        self.assertRegex(
            block, r"\n    " + re.escape(EXPORTED_FILE) + r":\d+:"
        )
        # no census line under another architecture, Documentation/, tools/ or
        # samples/; e.g. a line that opens `
        # Documentation/PCI/pciebus-howto.rst:` is not printed
        self.assertNotRegex(
            block, r"\n    (arch/powerpc|Documentation|tools|samples)/"
        )
        # the one summary line that counts them; e.g. `    ... 8 under
        # Documentation/`
        self.assertRegex(
            block,
            r"\n    \.\.\. .*\d+ under (other"
            r" architectures|Documentation/|tools/)",
        )

    @unittest.skipUnless(
        TREE,
        "no kernel tree: set KG_TREE or run the tests inside the checkout",
    )
    def test_pack_counts_a_common_name_only(self):
        """guidelines/campaign/spec.md [prompt]: a name mentioned more than the
        common cap gets its count and no census or callers, since a list of
        forty of its thousands of mentions would be noise.
        """
        self.world.edit(
            f"page: {PAGE}\n",
            f"page: {PAGE}\nsymbols:\n  - {{file: {FILE}, names: [kfree]}}\n",
        )
        text, _ = self.content(hints=True)
        # the head line of a common name, its count and the sentence that it
        # gets no census: group 1 the count, group 2 the line after; e.g. `
        # kfree: definition mm/slub.c:6781-6803 (23 lines); ...; mentions 30000
        # tree-wide; a name this common gets no census and no callers here`
        found = re.search(
            r"\n  kfree: .*; mentions (\d+) tree-wide; a name this common gets"
            r" no census and no callers here.*\n(.*)",
            text,
        )
        self.assertIsNotNone(found)
        self.assertGreater(int(found.group(1)), campaign.PACK_COMMON_CAP)
        self.assertFalse(found.group(2).startswith("    "), found.group(2))

    @unittest.skipUnless(
        TREE,
        "no kernel tree: set KG_TREE or run the tests inside the checkout",
    )
    def test_pack_caps_the_definitions_of_a_name_defined_everywhere(self):
        """guidelines/campaign/spec.md [prompt]: a name defined thousands of
        times tree-wide (flags) keeps the definitions under the roots and a
        count of the rest, so one scope name cannot make a brief half a
        megabyte.
        """
        self.world.edit(
            f"page: {PAGE}\n",
            f"page: {PAGE}\nsymbols:\n  - {{file: {FILE}, names: [flags]}}\n",
        )
        text, _ = self.content(hints=True)
        # the pack's head line of flags, group 1 what follows the name
        head = re.search(r"\n  flags: (.*)\n", text).group(1)
        self.assertLess(len(head), 20000)
        self.assertLessEqual(
            len(head.split("; mentions ")[0].split("; ")),
            campaign.PACK_DEFS_CAP + 1,
        )

    def test_definition_of_knows_macro_defined_objects(self):
        """guidelines/campaign/spec.md [prompt]: an object a kernel macro
        defines is a definition of the name it names; a SYSCALL_DEFINE line
        defines no function named after its argument.
        """
        d = campaign._definition_of
        self.assertEqual(
            d(
                None,
                "mm/mm_init.c",
                1,
                "DEFINE_STATIC_KEY_MAYBE(CONFIG_DEBUG_VM,"
                " check_pages_enabled);",
                "check_pages_enabled",
            ),
            ("variable", None),
        )
        self.assertEqual(
            d(
                None,
                "mm/swap.c",
                1,
                "static DEFINE_PER_CPU(struct cpu_fbatches, cpu_fbatches) = {",
                "cpu_fbatches",
            ),
            ("variable", None),
        )
        self.assertEqual(
            d(None, "x.h", 1, "DECLARE_BITMAP(flags, 8);", "flags"),
            ("declaration", None),
        )
        self.assertEqual(
            d(
                None,
                "x.h",
                1,
                "DEFINE_EVENT(mm_lru, mm_lru_insertion, TP_PROTO(struct folio"
                " *folio), TP_ARGS(folio));",
                "mm_lru_insertion",
            ),
            ("tracepoint", None),
        )
        self.assertIsNone(
            d(
                None,
                "mm/mm_init.c",
                1,
                "DEFINE_STATIC_KEY_MAYBE(CONFIG_DEBUG_VM,"
                " check_pages_enabled);",
                "CONFIG_DEBUG_VM",
            )
        )
        self.assertIsNone(
            d(
                None,
                "mm/mempolicy.c",
                1,
                "SYSCALL_DEFINE4(migrate_pages, pid_t, pid, unsigned long,"
                " maxnode,",
                "migrate_pages",
            )
        )
        self.assertIsNone(
            d(
                None,
                "x.h",
                1,
                "DEFINE_EVENT(mm_lru, mm_lru_insertion, TP_PROTO(struct folio"
                " *folio), TP_ARGS(folio));",
                "mm_lru",
            )
        )
        # unclosed: the event continues on the next lines
        self.assertEqual(
            d(
                None,
                "x.h",
                1,
                "TRACE_EVENT(mm_migrate_pages,",
                "mm_migrate_pages",
            ),
            ("tracepoint", None),
        )
        self.assertEqual(
            d(
                None,
                "x.h",
                1,
                "DEFINE_EVENT(mm_lru, mm_lru_insertion,",
                "mm_lru_insertion",
            ),
            ("tracepoint", None),
        )
        # a trailing attribute
        self.assertEqual(
            d(
                None,
                "x.c",
                1,
                "DEFINE_PER_CPU(int, foo) __read_mostly;",
                "foo",
            ),
            ("variable", None),
        )
        self.assertIsNone(
            d(None, "x.c", 1, "DEFINE_PER_CPU(int, foo) __read_mostly;", "int")
        )
        # the type argument is no object
        self.assertIsNone(
            d(
                None,
                "x.c",
                1,
                "DEFINE_PER_CPU(pg_data_t, node_data) __read_mostly;",
                "pg_data_t",
            )
        )

    @unittest.skipUnless(
        TREE,
        "no kernel tree: set KG_TREE or run the tests inside the checkout",
    )
    def test_pack_names_syscalls_and_lists_call_sites_only(self):
        """guidelines/campaign/spec.md [prompt]: the function index names
        SYSCALL_DEFINEn(name, ...) sys_name, and the callers by function are
        call sites: the syscall definition that carries the name as an argument
        is not one.
        """
        names = [
            fn
            for fn, _s, _e in campaign._function_index(TREE, "mm/mempolicy.c")
        ]
        self.assertIn("sys_migrate_pages", names)
        self.assertNotIn("SYSCALL_DEFINE4", names)
        self.world.edit(
            f"page: {PAGE}\n",
            f"page: {PAGE}\nsymbols:\n  - {{file: {FILE}, names:"
            " [migrate_pages]}\n",
        )
        text, _ = self.content(hints=True)
        block = text[text.index("\n  migrate_pages: ") :]
        # the callers line of the name's block, group 1 the callers; e.g. `
        # callers by function: compact_zone mm/compaction.c:2561-2798 (at
        # :2698); ...`
        callers = re.search(r"\n    callers by function: (.*)", block)
        self.assertIsNotNone(callers)
        self.assertNotIn("SYSCALL_DEFINE", callers.group(1))
        self.assertNotIn("sys_migrate_pages", callers.group(1))

    @unittest.skipUnless(
        TREE,
        "no kernel tree: set KG_TREE or run the tests inside the checkout",
    )
    def test_pack_does_not_take_a_forward_declaration_for_a_stub(self):
        """A static function declared ahead of its definition shares its first
        line with the prototype; the pack reports the definition with its range
        and never a one-line stub at the prototype.
        """
        self.world.edit(
            f"page: {PAGE}\n",
            f"page: {PAGE}\nsymbols:\n  - {{file: {FILE}, names:"
            " [__rmap_walk_file]}\n",
        )
        text, _ = self.content(hints=True)
        # the pack's head line of __rmap_walk_file, group 1 what follows the
        # name
        head = re.search(r"\n  __rmap_walk_file: (.*)\n", text).group(1)
        self.assertNotIn("stub definition", head)
        # the function's definition with its range; e.g. `definition
        # mm/rmap.c:3084-3170 (87 lines)`
        self.assertRegex(head, r"definition mm/rmap\.c:\d+-\d+ \(\d+ lines\)")

    @unittest.skipUnless(
        TREE,
        "no kernel tree: set KG_TREE or run the tests inside the checkout",
    )
    def test_pack_greps_past_a_stub_the_tags_file_offers(self):
        """css_put's definition stands behind CGROUP_REF_FN_ATTRS on its own
        line, which ctags does not tag; the tags file offers the !CGROUPS stub
        and a prototype, and the pack used to stop there. It greps on when the
        tags file gives no definition with a body, and lists the real one
        beside the stub.
        """
        self.world.edit(
            f"page: {PAGE}\n",
            f"page: {PAGE}\nsymbols:\n  - {{file: {FILE}, names:"
            " [css_put]}\n",
        )
        text, _ = self.content(hints=True)
        # the pack's head line of css_put, group 1 what follows the name
        head = re.search(r"\n  css_put: (.*)\n", text).group(1)
        # the definition with a body, behind its attribute line; e.g.
        # `definition include/linux/cgroup_refcnt.h:76-80`
        self.assertRegex(
            head, r"definition include/linux/cgroup_refcnt\.h:\d+-\d+"
        )
        self.assertIn("stub definition include/linux/cgroup.h:", head)

    def test_function_index_skips_macro_invocations_without_a_body(self):
        """PAGEFLAG(Locked, locked, PF_NO_TAIL) ends with no `;`, and the index
        took it for a function whose body was the next brace to close,
        swallowing folio_test_swapcache and every function between; a macro
        invocation is a function only when its body opens at once, as
        SYSCALL_DEFINE1's does.
        """
        folder = tempfile.mkdtemp(prefix="kg-index-")
        try:
            with open(
                os.path.join(folder, "x.h"), "w", encoding="utf-8"
            ) as handle:
                handle.write(
                    "PAGEFLAG(Locked, locked, PF_NO_TAIL)\n"
                    "PAGEFLAG(Dirty, dirty, PF_HEAD)\n"
                    "\n"
                    "static __always_inline bool folio_test_swapcache(const"
                    " struct folio *folio)\n"
                    "{\n"
                    "\treturn 1;\n"
                    "}\n"
                    "FOLIO_SET_FLAG(swapcache, FOLIO_HEAD_PAGE)\n"
                    "SYSCALL_DEFINE1(probe, int, x)\n"
                    "{\n"
                    "\treturn 0;\n"
                    "}\n"
                )
            self.assertEqual(
                campaign._function_index(folder, "x.h"),
                [("folio_test_swapcache", 4, 7), ("sys_probe", 9, 12)],
            )
            self.assertEqual(
                campaign._definition_of(
                    folder,
                    "x.h",
                    4,
                    "static __always_inline bool folio_test_swapcache(const"
                    " struct folio *folio)",
                    "folio_test_swapcache",
                ),
                ("definition", 7),
            )
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_content_prints_its_page_warnings_and_counts_the_rest(
        self,
    ):
        opener = f"```md kg:scope page={PAGE}\n"
        self.world.edit(opener, opener + "`_probe_x`, ")
        _errors, warnings = campaign.validate(self.world.load())
        # a warning that names PAGE: the page id with no word character or
        # hyphen after it; e.g. a warning that opens `md kg:scope
        # rc/portdrv/error-recovery:`
        own = [
            w for w in warnings if re.search(re.escape(PAGE) + r"(?![\w-])", w)
        ]
        rest = len(warnings) - len(own)
        code, _out, err = run_main(
            [
                "--glossary-checkout",
                self.world.skill,
                "--tree",
                self.world.tree,
                "content",
                self.world.spec,
                PAGE,
                "--allow-gaps",
            ]
        )
        self.assertEqual(code, 0)
        self.assertIn("`_probe_x`", err)
        self.assertEqual(err.count("warning: "), len(own))
        if rest:
            self.assertIn(f"{rest} other warning", err)
        code, _out, err = run_main(
            [
                "--glossary-checkout",
                self.world.skill,
                "--tree",
                self.world.tree,
                "content",
                self.world.spec,
                SIBLING,
                "--allow-gaps",
            ]
        )
        self.assertEqual(code, 0)
        self.assertNotIn("_probe_x", err)


class Census(unittest.TestCase):
    """The research pack's census: one grep asks a tree for all the names of
    a page, and every name gets the lines `git grep -n -w <name>` prints for
    it alone, in the same order."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        git(self.root, "init", "-q")
        files = {
            "a.c": (
                "int foo;\nint foo_bar; /* foo */\n"
                "bar foo2 xfoo\nfoo(bar)\n"
            ),
            "dir/c.h": "foo bar\nfoo.bar\n#define BAR foo->bar\n",
            "empty.txt": "",
        }
        for name, text in files.items():
            path = Path(self.root, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        Path(self.root, "b.bin").write_bytes(b"\0\0foo\0bar_x\n\0 zed \0")
        git(self.root, "add", "-A")

    def alone(self, tree, name):
        run = subprocess.run(
            ["git", "-C", tree, "grep", "-n", "-w", name],
            capture_output=True,
            text=True,
        )
        return [line for line in run.stdout.split("\n") if line]

    def test_one_grep_answers_every_name_as_its_own_grep_would(self):
        names = ["foo", "bar", "foo_bar", "foo2", "zed", "BAR", "nowhere"]
        asked = []
        real = subprocess.run

        def run(cmd, *args, **kw):
            asked.append(cmd)
            return real(cmd, *args, **kw)

        with unittest.mock.patch.object(campaign.subprocess, "run", run):
            census = campaign._census(self.root, names + ["foo.bar"])
        for name in names + ["foo.bar"]:
            self.assertEqual(census[name], self.alone(self.root, name), name)
        self.assertEqual(census["nowhere"], [])
        # a binary file is reported without its line: each name is asked
        # of the binary files again, and only those it holds report it
        self.assertIn("Binary file b.bin matches", census["foo"])
        self.assertIn("Binary file b.bin matches", census["zed"])
        self.assertNotIn("Binary file b.bin matches", census["bar"])
        # the plain identifiers share one grep over the tree; a name that
        # is no plain identifier is a pattern of its own and is asked alone
        whole_tree = [
            cmd for cmd in asked if "grep" in cmd and "--" not in cmd
        ]
        self.assertEqual(len(whole_tree), 2, whole_tree)
        self.assertEqual(whole_tree[0][-1], "|".join(names))
        self.assertEqual(whole_tree[1][-1], "foo.bar")

    def test_more_names_than_one_grep_takes_are_asked_in_turns(self):
        names = ["foo", "bar", "foo_bar", "foo2", "zed"]
        with unittest.mock.patch.object(campaign, "PACK_BULK", 2):
            census = campaign._census(self.root, names)
        for name in names:
            self.assertEqual(census[name], self.alone(self.root, name), name)

    @unittest.skipUnless(
        TREE,
        "no kernel tree: set KG_TREE or run the tests inside the checkout",
    )
    def test_the_kernel_tree_answers_the_same_in_one_grep(self):
        names = [FUNC, CALLED, STRUCT, "kobject"]
        census = campaign._census(TREE, names)
        for name in names:
            self.assertEqual(census[name], self.alone(TREE, name), name)
            self.assertTrue(census[name], name)


class FunctionIndex(unittest.TestCase):
    """The research pack's function index and ranges: a body ends at the brace
    that closes it, so a one-line weak function, a header stub, a function
    returning a struct pointer and a function whose type stands on the line
    above are indexed with their own ranges, and a prototype or a macro
    invocation is no function.
    """

    SOURCE = [
        "/* a comment with a brace { and an apostrophe ' */",  # 1
        "#include <linux/pci.h>",  # 2
        "",  # 3
        "int early_prototype(int a,",  # 4
        "\t\t    int b);",  # 5
        "",  # 6
        "void __weak one_liner(struct pci_dev *pdev) { }",  # 7
        "",  # 8
        # 9
        "struct pci_dev *returns_a_struct(struct pci_bus *bus, int devfn)",
        "{",  # 10
        '\tchar *s = "}";\t/* a brace in a string and a comment } */',  # 11
        "\tif (bus) {",  # 12
        "\t\treturn NULL;",  # 13
        "\t}",  # 14
        "\treturn NULL;",  # 15
        "}",  # 16
        "",  # 17
        "static int",  # 18
        "name_on_its_own_line(struct pci_dev *dev) {",  # 19
        "\treturn 0;",  # 20
        "}",  # 21
        "",  # 22
        "static inline int stub(struct pci_dev *dev, int i)",  # 23
        "{ return -EBUSY; }",  # 24
        "",  # 25
        "DECLARE_PCI_FIXUP_HEADER(PCI_VENDOR_ID_INTEL, 0x1460,",  # 26
        "\t\t\t one_liner);",  # 27
        "",  # 28
        "static const struct dmi_system_id quirks[] __initconst = {",  # 29
        "\t{ .callback = one_liner, },",  # 30
        "\t{}",  # 31
        "};",  # 32
    ]

    def setUp(self):
        self.tree = tempfile.mkdtemp(prefix="kg-index-")
        os.makedirs(os.path.join(self.tree, "drivers/x"))
        with open(
            os.path.join(self.tree, "drivers/x/f.c"), "w", encoding="utf-8"
        ) as handle:
            handle.write("\n".join(self.SOURCE) + "\n")

    def tearDown(self):
        shutil.rmtree(self.tree, ignore_errors=True)

    def test_bodies_end_at_their_closing_brace(self):
        self.assertEqual(
            campaign._function_index(self.tree, "drivers/x/f.c"),
            [
                ("one_liner", 7, 7),
                ("returns_a_struct", 9, 16),
                ("name_on_its_own_line", 19, 21),
                ("stub", 23, 24),
            ],
        )
        self.assertEqual(
            campaign._enclosing(self.tree, "drivers/x/f.c", 11),
            ("returns_a_struct", 9, 16),
        )
        self.assertEqual(
            campaign._enclosing(self.tree, "drivers/x/f.c", 20),
            ("name_on_its_own_line", 19, 21),
        )
        self.assertIsNone(campaign._enclosing(self.tree, "drivers/x/f.c", 5))
        self.assertIsNone(campaign._enclosing(self.tree, "drivers/x/f.c", 30))
        lines = campaign._file_lines(self.tree, "drivers/x/f.c")
        self.assertIsNone(
            campaign._function_end(lines, 4), "a prototype has no body"
        )
        self.assertIsNone(
            campaign._function_end(lines, 26), "a macro invocation has no body"
        )
        self.assertEqual(campaign._function_end(lines, 24 - 1), 24)
        self.assertEqual(campaign._brace_end(self.tree, "drivers/x/f.c", 7), 7)

    def test_a_comment_mention_is_no_caller(self):
        self.assertTrue(
            campaign._comment_line(
                " * We pass NULL as parent to pci_create_root_bus(), so"
            )
        )
        self.assertTrue(
            campaign._comment_line(
                "\t/* Can not put in pci_device_add yet because resources"
            )
        )
        self.assertTrue(
            campaign._comment_line("\t\t// pci_device_add(dev, bus);")
        )
        self.assertFalse(campaign._comment_line("\tpci_device_add(dev, bus);"))
        self.assertFalse(
            campaign._comment_line(
                "\tbus = pci_create_root_bus(NULL, busnum, ops->pci_ops,"
            )
        )


class Editing(unittest.TestCase):

    def setUp(self):
        self.world = World()
        self.addCleanup(self.world.close)

    def clean(self):
        errors, _ = campaign.validate(self.world.load())
        self.assertEqual(errors, [])

    def test_note_appends_or_creates(self):
        where = campaign.note(self.world.load(), PAGE, "a second caller")
        self.assertIn("appended", where)
        self.assertIn("- a second caller\n```", self.world.text())
        # the notes fence of SIBLING with the blank line after it; e.g. "```md
        # kg:notes page=rc/portdrv/dpc\n- a note\n```\n\n"
        self.world.write(
            re.sub(
                rf"```md kg:notes page={SIBLING}\n.*?\n```\n\n",
                "",
                self.world.text(),
                count=1,
                flags=re.S,
            )
        )
        self.assertNotIn(SIBLING, self.world.load().notes_page)
        where = campaign.note(self.world.load(), SIBLING, "first")
        self.assertIn("new notes fence", where)
        spec = self.world.load()
        self.assertEqual(spec.notes_page[SIBLING][0].body, "- first")
        campaign.note(spec, None, "shared", cluster=CLUSTER)
        self.assertIn(
            "- shared", self.world.load().notes_cluster[CLUSTER][-1].body
        )
        had = bool(self.world.load().notes_campaign)
        where = campaign.note(
            self.world.load(), None, "a campaign-wide ruling", campaign=True
        )
        self.assertIn("appended" if had else "new notes fence", where)
        self.assertIn(
            "- a campaign-wide ruling",
            self.world.load().notes_campaign[0].body,
        )
        code, out, _ = run_main(
            [
                "--glossary-checkout",
                self.world.skill,
                "note",
                self.world.spec,
                "-",
                "a second ruling",
                "--campaign",
            ]
        )
        self.assertEqual(code, 0)
        self.assertIn("appended", out)
        self.clean()

    def test_assign_adds_refuses_and_moves(self):
        out = campaign.assign(self.world.load(), UNASSIGNED, SIBLING)
        self.assertIn(f"assigned to {SIBLING}", out)
        with self.assertRaises(campaign.CampaignError):
            campaign.assign(self.world.load(), ASSIGNED, PAGE)
        out = campaign.assign(self.world.load(), ASSIGNED, PAGE, force=True)
        self.assertIn(f"moved from {ASSIGNED_OWNER} to {PAGE}", out)
        owners = {s: o for s, o, _ in self.world.load().assignments()}
        self.assertEqual(owners[UNASSIGNED], SIBLING)
        self.assertEqual(owners[ASSIGNED], PAGE)
        self.clean()

    def test_assign_creates_the_table(self):
        # the cluster block of CLUSTER, from the line that opens it to the line
        # that closes it; e.g. "```yaml kg:cluster\nname: Port services
        # cluster\npages: [...]\nassign:\n  aer_probe: rc/portdrv/aer\n```"
        block = re.search(
            rf"```yaml kg:cluster\nname: {CLUSTER}\n.*?\n```",
            self.world.text(),
            re.S,
        ).group(0)
        # the assign table of the block, the `assign:` line and its indented
        # rows; e.g. "\nassign:\n  aer_probe: rc/portdrv/aer\n"
        without = re.sub(r"\nassign:\n(?:  .*\n)*", "\n", block)
        self.assertNotEqual(block, without)
        self.world.edit(block, without)
        self.assertEqual(
            [
                s
                for s, _o, c in self.world.load().assignments()
                if str(c.data.get("name")) == CLUSTER
            ],
            [],
        )
        out = campaign.assign(self.world.load(), ASSIGNED, ASSIGNED_OWNER)
        self.assertIn("assign table created", out)
        self.assertEqual(
            [
                s
                for s, _o, c in self.world.load().assignments()
                if str(c.data.get("name")) == CLUSTER
            ],
            [ASSIGNED],
        )
        self.clean()


class Routes(unittest.TestCase):

    def test_a_spec_without_fences_is_refused(self):
        f = tempfile.NamedTemporaryFile(
            "w", suffix=".md", delete=False, encoding="utf-8"
        )
        f.write("# A plan in prose\n\nNo fence carries `kg`.\n")
        f.close()
        self.addCleanup(os.unlink, f.name)
        code, out, _err = run_main(["validate", f.name])
        self.assertEqual(code, 1)
        self.assertIn("error:", out)
        self.assertIn("no `yaml kg:campaign` block", out)

    def test_validate_returncodes(self):
        code, out, _ = run_main(["validate", SPEC])
        self.assertEqual(code, 0)
        self.assertIn("0 errors", out)
        f = tempfile.NamedTemporaryFile(
            "w", suffix=".md", delete=False, encoding="utf-8"
        )
        f.write(
            Path(SPEC)
            .read_text(encoding="utf-8")
            .replace(f"page: {SIBLING}\n", f"page: {PAGE}\n")
        )
        f.close()
        self.addCleanup(os.unlink, f.name)
        code, out, _ = run_main(["validate", f.name])
        self.assertEqual(code, 1)
        self.assertIn("error:", out)

    def test_cli_from_another_directory_with_a_selected_skill(self):
        world = World()
        self.addCleanup(world.close)
        with tempfile.TemporaryDirectory() as cwd:
            result = subprocess.run(
                [
                    sys.executable,
                    os.path.join(TOOLS, "campaign", "run.py"),
                    "--glossary-checkout",
                    world.skill,
                    "--tree",
                    world.tree,
                    "content",
                    world.spec,
                    OTHER,
                    "--allow-gaps",
                ],
                cwd=cwd,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("MISSION.", result.stdout)
        self.assertIn("CAMPAIGN FACTS:", result.stdout)
        self.assertNotIn("<!-- page model -->", result.stdout)

    def test_the_boundary_with_the_engine(self):
        source = Path(os.path.join(TOOLS, "campaign", "run.py")).read_text(
            encoding="utf-8"
        )
        for forbidden in (
            "from checks",
            "import kg",
            "lint_record",
            "from inputs",
            "from report",
            "from tools.qa",
            "import tools.qa",
            "kg.py check",
        ):
            self.assertNotIn(forbidden, source, forbidden)
        imports = {
            line.split()[1]
            for line in source.split("\n")
            if line.lstrip().startswith(("import ", "from "))
        }
        self.assertEqual(
            imports
            - {
                "argparse",
                "datetime",
                "glob",
                "hashlib",
                "json",
                "os",
                "pathlib",
                "re",
                "subprocess",
                "sys",
                "yaml",
                "unittest",
                "tools.rules",
                "tools.checkout",
                "tools.tagsfile",
            },
            set(),
        )
        # dynamic: every command runs without loading any module from under
        # tools/qa/
        world = World()
        self.addCleanup(world.close)
        for argv in (
            ["validate", world.spec, "--regions", "--checklist"],
            ["index", world.spec, "--conflicts"],
            ["show", world.spec, PAGE],
            ["content", world.spec, PAGE, "--allow-gaps", "--out", os.devnull],
        ):
            run_main(
                [
                    "--glossary-checkout",
                    world.skill,
                    "--tree",
                    world.tree,
                    *argv,
                ]
            )
        # only the skill's own trees count: a virtual environment under the
        # checkout (CI's .venv) holds PyYAML
        own = tuple(os.path.join(SKILL, d) + os.sep for d in ("tools",))
        loaded = [
            m.__file__
            for m in list(sys.modules.values())
            if getattr(m, "__file__", None) and m.__file__.startswith(own)
        ]
        project = sorted(
            {
                f
                for f in loaded
                if not f.startswith(
                    os.path.join(TOOLS, "campaign", "tests") + os.sep
                )
            }
        )
        self.assertTrue(
            set(project)
            <= {
                os.path.join(TOOLS, "__init__.py"),
                os.path.join(TOOLS, "campaign", "__init__.py"),
                os.path.join(TOOLS, "campaign", "run.py"),
                os.path.join(TOOLS, "rules.py"),
                os.path.join(TOOLS, "checkout.py"),
                os.path.join(TOOLS, "tagsfile.py"),
            },
            project,
        )
        self.assertEqual(
            [f for f in loaded if os.sep + "qa" + os.sep in f], []
        )
        for root, _dirs, files in os.walk(os.path.join(SKILL, "tools", "qa")):
            for name in files:
                if name.endswith(".py"):
                    text = Path(os.path.join(root, name)).read_text(
                        encoding="utf-8"
                    )
                    self.assertNotIn("import campaign", text, name)
                    self.assertNotIn("tools/campaign", text, name)


class TreeLocation(unittest.TestCase):
    def test_tree_root_is_the_checkout_holding_the_claude_directory(
        self,
    ):
        """guidelines/campaign/spec.md [campaign]: TREE_ROOT is the kernel
        checkout whose .claude directory holds this repository; a path in the
        spec or --tree wins, and no such directory is an error, never a guess.
        """
        with (
            tempfile.TemporaryDirectory() as folder,
            unittest.mock.patch.dict("os.environ"),
        ):
            path = os.path.join(folder, "x.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(
                    "```yaml kg:campaign\n"
                    "campaign: x\n"
                    "tree: TREE_ROOT\n"
                    "version: v7.2\n"
                    "commit: " + "0" * 40 + "\n```\n"
                )
            spec = campaign.Spec(path)
            os.environ.pop("KG_TREE", None)
            checkout = os.path.join(folder, "x", ".claude", "skills", "kg")
            os.makedirs(checkout)
            self.assertEqual(
                campaign.tree_root(spec, checkout=checkout),
                os.path.join(folder, "x"),
            )
            self.assertEqual(
                campaign.tree_root(
                    spec, override="/explicit", checkout=checkout
                ),
                "/explicit",
            )
            with self.assertRaises(campaign.CampaignError):
                campaign.tree_root(spec, checkout=folder)


class Documents(unittest.TestCase):
    def test_the_readme_has_to_name_every_command_and_option(self):
        """The standard names no tool, so the tool's README is where its
        commands and options are learned: selftest fails on one it leaves
        out."""
        names, options = campaign.interface()
        self.assertEqual(names, list(campaign.SUBCOMMANDS))
        self.assertIn("--allow-gaps", options)
        self.assertIn("--glossary-checkout", options)
        self.assertNotIn("--help", options)
        with tempfile.TemporaryDirectory() as folder:
            readme = os.path.join(folder, "README.md")
            self.assertEqual(campaign.unnamed(readme), names + options)
            text = "".join(f"`{n} <spec>`\n" for n in names) + "\n".join(
                f"`{o}`" for o in options
            )
            with open(readme, "w", encoding="utf-8") as f:
                f.write(text)
            self.assertEqual(campaign.unnamed(readme), [])
            with open(readme, "w", encoding="utf-8") as f:
                f.write(
                    text.replace("`--force`", "`--forceful`").replace(
                        "`show <spec>`", "`--page` to show"
                    )
                )
            self.assertEqual(campaign.unnamed(readme), ["show", "--force"])
        self.assertEqual(
            campaign.unnamed(os.path.join(TOOLS, "campaign", "README.md")), []
        )


if __name__ == "__main__":
    unittest.main()
