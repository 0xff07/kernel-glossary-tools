"""The writer's mechanical aids against a small tree: a fence in the page's
form, anchors resolved and checked, and a template expanded into a page."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

if not __package__:
    # run as a script: make the repository's packages importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.writer import anchors, excerpt, expand

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)

SOURCE = """/* SPDX-License-Identifier: GPL-2.0 */
#include <linux/kernel.h>

#define TB_MAX_PORTS 64

/**
 * struct tb_port - a port of a router
 * @sw: the router
 */
struct tb_port {
\tstruct tb_switch *sw;
\tint port;
\tbool enabled;
};

static int tb_port_enable(struct tb_port *port)
{
\tif (!port)
\t\treturn -EINVAL;
\tport->enabled = true;
\treturn 0;
}

int tb_port_disable(struct tb_port *port)
{
\tport->enabled = false;
\treturn 0;
}
"""
KCONFIG = """config USB4
\ttristate "Unified support for USB4 and Thunderbolt"
\tdepends on PCI

menuconfig USB4_DEBUGFS
\tbool "debugfs"
"""


class World(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.tree = os.path.join(self.root, "tree")
        os.makedirs(os.path.join(self.tree, "drivers", "thunderbolt"))
        os.makedirs(os.path.join(self.tree, "arch", "x86", "pci"))
        with open(
            os.path.join(self.tree, "drivers", "thunderbolt", "tb.c"),
            "w",
            encoding="utf-8",
        ) as handle:
            handle.write(SOURCE)
        with open(
            os.path.join(self.tree, "arch", "x86", "pci", "tb.c"),
            "w",
            encoding="utf-8",
        ) as handle:
            handle.write("int other(void)\n{\n\treturn 1;\n}\n")
        with open(
            os.path.join(self.tree, "drivers", "thunderbolt", "Kconfig"),
            "w",
            encoding="utf-8",
        ) as handle:
            handle.write(KCONFIG)
        git = ["git", "-C", self.tree]
        subprocess.run(git + ["init", "-q"], check=True)
        subprocess.run(
            git + ["-c", "user.name=t", "-c", "user.email=t@t", "add", "."],
            check=True,
        )
        subprocess.run(
            git
            + [
                "-c",
                "user.name=t",
                "-c",
                "user.email=t@t",
                "commit",
                "-q",
                "-m",
                "tree",
            ],
            check=True,
        )
        self.head = subprocess.run(
            git + ["rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    def tearDown(self):
        subprocess.run(["rm", "-rf", self.root])


class Excerpt(World):
    def test_a_unit_carries_its_provenance_and_counted_elisions(self):
        out = excerpt.fence(
            self.tree, ["drivers/thunderbolt/tb.c:16-18,20-22"], note="piece ❶"
        )
        lines = out.split("\n")
        self.assertEqual(lines[0], "```c")
        self.assertEqual(lines[1], "/* drivers/thunderbolt/tb.c:16 piece ❶ */")
        self.assertEqual(
            lines[2], "static int tb_port_enable(struct tb_port *port)"
        )
        # indented like the line it resumes at
        self.assertEqual(lines[5], "\t... /* 1 line, to :20 */")
        self.assertEqual(lines[6], "\tport->enabled = true;")
        self.assertEqual(lines[-1], "```")
        # verbatim, tab included
        self.assertEqual(SOURCE.split("\n")[19], lines[6])

    def test_a_fence_rejects_zero_or_multiple_units(self):
        for units in (
            [],
            ["drivers/thunderbolt/tb.c:4", "drivers/thunderbolt/tb.c:24-28"],
            ["drivers/thunderbolt/tb.c:4", "arch/x86/pci/tb.c:1-4"],
        ):
            with self.subTest(units=units):
                with self.assertRaisesRegex(
                    excerpt.ExcerptError, "exactly one source unit"
                ):
                    excerpt.fence(self.tree, units)

    def test_one_unit_can_contain_consecutive_functions(self):
        out = excerpt.fence(self.tree, ["drivers/thunderbolt/tb.c:16-28"])
        self.assertEqual(out.count("/* drivers/thunderbolt/tb.c:"), 1)
        self.assertIn("static int tb_port_enable(", out)
        self.assertIn("int tb_port_disable(", out)

    def test_a_commit_is_read_through_git(self):
        out = excerpt.fence(
            self.tree, ["drivers/thunderbolt/tb.c:4"], commit=self.head
        )
        self.assertIn("#define TB_MAX_PORTS 64", out)

    def test_bad_ranges_are_errors(self):
        for spec in (
            "drivers/thunderbolt/tb.c",
            "drivers/thunderbolt/tb.c:5-3",
            "drivers/thunderbolt/tb.c:4-5,6-7",
            "drivers/thunderbolt/tb.c:400-500",
            "drivers/thunderbolt/none.c:1-2",
        ):
            with self.subTest(spec=spec):
                with self.assertRaises(excerpt.ExcerptError):
                    excerpt.fence(self.tree, [spec])

    def test_the_command_prints_the_fence(self):
        done = subprocess.run(
            [
                sys.executable,
                os.path.join(TOOLS, "excerpt.py"),
                "--tree",
                self.tree,
                "drivers/thunderbolt/tb.c:10-14",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue(
            done.stdout.startswith(
                "```c\n/* drivers/thunderbolt/tb.c:10 */\nstruct tb_port {\n"
            )
        )

    def test_the_command_rejects_multiple_units_without_printing_code(self):
        done = subprocess.run(
            [
                sys.executable,
                os.path.join(TOOLS, "excerpt.py"),
                "--tree",
                self.tree,
                "drivers/thunderbolt/tb.c:4",
                "drivers/thunderbolt/tb.c:24-28",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(done.returncode, 2)
        self.assertIn("unrecognized arguments", done.stderr)
        self.assertEqual(done.stdout, "")


class Anchors(World):
    def resolve(self, name):
        return sorted(anchors.resolve(self.tree, name, tags=None))

    def test_definitions_by_kind(self):
        self.assertEqual(
            self.resolve("tb_port_enable"),
            [("drivers/thunderbolt/tb.c", 16, "function")],
        )
        self.assertEqual(
            self.resolve("tb_port_disable()"),
            [("drivers/thunderbolt/tb.c", 24, "function")],
        )
        self.assertEqual(
            self.resolve("struct tb_port"),
            [("drivers/thunderbolt/tb.c", 10, "struct")],
        )
        self.assertEqual(
            self.resolve("tb_port.enabled"),
            [("drivers/thunderbolt/tb.c", 13, "member")],
        )
        self.assertEqual(
            self.resolve("TB_MAX_PORTS"),
            [("drivers/thunderbolt/tb.c", 4, "macro")],
        )
        self.assertEqual(
            self.resolve("CONFIG_USB4"),
            [("drivers/thunderbolt/Kconfig", 1, "config")],
        )
        self.assertEqual(
            self.resolve("CONFIG_USB4_DEBUGFS"),
            [("drivers/thunderbolt/Kconfig", 5, "config")],
        )

    def test_macro_defined_objects_as_any_argument(self):
        """An object a kernel macro defines resolves to the invocation line
        whatever argument position names it, with a storage class before the
        macro: DEFINE_STATIC_KEY_MAYBE(CONFIG_DEBUG_VM, name), static
        DEFINE_PER_CPU(type, name).
        """
        os.makedirs(os.path.join(self.tree, "mm"))
        with open(
            os.path.join(self.tree, "mm", "keys.c"), "w", encoding="utf-8"
        ) as handle:
            handle.write(
                "DEFINE_STATIC_KEY_MAYBE(CONFIG_DEBUG_VM,"
                " check_pages_enabled);\n"
                "static DEFINE_PER_CPU(struct cpu_fbatches, cpu_fbatches) ="
                " {\n"
                "};\n"
                "LIST_HEAD(shrinker_list);\n"
                "DEFINE_EVENT(mm_lru, mm_lru_insertion,\n"
                "\tTP_PROTO(struct folio *folio),\n"
                "\tTP_ARGS(folio)\n"
                ");\n"
                "void f(struct folio *folio)\n"
                "{\n"
                "\tVM_BUG_ON_FOLIO(folio_test_dirty(folio), folio);\n"
                "\tWRITE_ONCE(folio->flags, flags);\n"
                "}\n"
            )
        git = [
            "git",
            "-C",
            self.tree,
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
        ]
        subprocess.run(git + ["add", "."], check=True)
        subprocess.run(git + ["commit", "-q", "-m", "keys"], check=True)
        self.assertEqual(
            self.resolve("check_pages_enabled"),
            [("mm/keys.c", 1, "macro invocation")],
        )
        self.assertEqual(
            self.resolve("cpu_fbatches"),
            [("mm/keys.c", 2, "macro invocation")],
        )
        self.assertEqual(
            self.resolve("shrinker_list"),
            [("mm/keys.c", 4, "macro invocation")],
        )
        # a tracepoint, its invocation unclosed on the line
        self.assertEqual(
            self.resolve("mm_lru_insertion"),
            [("mm/keys.c", 5, "macro invocation")],
        )
        # an indented macro inside a body defines nothing
        self.assertEqual(self.resolve("folio"), [])

    def test_a_member_is_found_in_code_not_in_a_comment_that_names_it(self):
        """Without a tags file a member is looked up inside its holder's body.
        A comment on another member's line that names it, a block comment
        carried over a line break, a `//` tail and a brace inside a comment are
        no code: the member's own declaration is the answer, and the body does
        not end at the comment's brace.
        """
        os.makedirs(os.path.join(self.tree, "mm"))
        with open(
            os.path.join(self.tree, "mm", "region.h"), "w", encoding="utf-8"
        ) as handle:
            handle.write(
                "struct vm_region_like {\n"
                "\tunsigned long pgoff;\t/* Offset (within file) in pages,\n"
                "\t\t\t\t   as file; says */\n"
                "\tvoid *private;\t\t// was pte (shared mem); a } here\n"
                "\tstruct file *file;\t/* the file */\n"
                "\tstruct {\n"
                "\t\tint rb;\n"
                "\t} shared;\n"
                "};\n"
            )
        git = [
            "git",
            "-C",
            self.tree,
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
        ]
        subprocess.run(git + ["add", "."], check=True)
        subprocess.run(git + ["commit", "-q", "-m", "region"], check=True)
        # not :2 or :3
        self.assertEqual(
            self.resolve("vm_region_like.file"), [("mm/region.h", 5, "member")]
        )
        # not :4
        self.assertEqual(
            self.resolve("vm_region_like.shared"),
            [("mm/region.h", 8, "member")],
        )
        # the `}` of :4 ends nothing
        self.assertEqual(
            self.resolve("vm_region_like.rb"), [("mm/region.h", 7, "member")]
        )
        # code before a comment
        self.assertEqual(
            self.resolve("vm_region_like.pgoff"),
            [("mm/region.h", 2, "member")],
        )

    def test_code_part_drops_comments_and_keeps_literals(self):
        self.assertEqual(
            anchors.code_part("int a; /* b; */ int c;", False),
            ("int a;   int c;", False),
        )
        self.assertEqual(
            anchors.code_part("\tlong pgoff;\t/* Offset (within file)", False),
            ("\tlong pgoff;\t", True),
        )
        self.assertEqual(
            anchors.code_part("\t   units */ int d;", True),
            ("  int d;", False),
        )
        self.assertEqual(
            anchors.code_part(" * still a comment; }", True), ("", True)
        )
        self.assertEqual(
            anchors.code_part('char *s = "/* text */"; // tail }', False),
            ('char *s = "/* text */"; ', False),
        )

    def test_a_path_filter_and_a_missing_name(self):
        self.assertEqual(
            self.resolve("other@arch/x86"),
            [("arch/x86/pci/tb.c", 1, "function")],
        )
        self.assertEqual(self.resolve("tb_port_enable@arch/x86"), [])
        self.assertEqual(self.resolve("nothing_here"), [])
        with self.assertRaises(ValueError):
            anchors.parse_name("a b c")

    def test_the_posix_rewrite_keeps_bracket_expressions_well_formed(self):
        self.assertEqual(
            anchors.posix_pattern(r"^[A-Za-z_][\w \t*]*\bname[ \t]*\("),
            "^[A-Za-z_][A-Za-z0-9_ \t*]*(^|[^A-Za-z0-9_])name[ \t]*\\(",
        )
        self.assertEqual(anchors.posix_pattern(r"\w+\b"), "[A-Za-z0-9_]+")
        import subprocess as sp

        posix = anchors.posix_pattern(
            r"^[A-Za-z_][\w \t*]*\btb_port_enable[ \t]*\("
        )
        done = sp.run(
            [
                "git",
                "-C",
                self.tree,
                "grep",
                "-n",
                "-E",
                posix,
                "--",
                "drivers/thunderbolt/tb.c",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            done.stdout.strip(),
            "drivers/thunderbolt/tb.c:16:static int tb_port_enable(struct"
            " tb_port *port)",
        )

    def test_check_reports_a_moved_line(self):
        tsv = os.path.join(self.root, "anchors.tsv")
        with open(tsv, "w", encoding="utf-8") as handle:
            handle.write(
                "tb_port_enable\tdrivers/thunderbolt/tb.c:16\tfunction\n"
                "struct tb_port\tdrivers/thunderbolt/tb.c:11\tstruct\n"
                "CONFIG_USB4\tdrivers/thunderbolt/Kconfig:1\tconfig\n"
                "gone\tdrivers/thunderbolt/missing.c:1\tfunction\n"
            )
        problems = anchors.check(self.tree, tsv)
        self.assertEqual(len(problems), 2, problems)
        self.assertTrue(
            problems[0].startswith(
                "struct tb_port: drivers/thunderbolt/tb.c:11 does not spell"
                " tb_port"
            )
        )
        self.assertIn("names no file line", problems[1])


class Expand(World):
    def build(self, template, anchors_text=""):
        tsv = os.path.join(self.root, "anchors.tsv")
        with open(tsv, "w", encoding="utf-8") as handle:
            handle.write(anchors_text)
        figures = os.path.join(self.root, "figs")
        os.makedirs(figures, exist_ok=True)
        with open(
            os.path.join(figures, "model.txt"), "w", encoding="utf-8"
        ) as handle:
            handle.write("```\n    a ──▶ b\n```\n")
        expander = expand.Expander(
            self.tree, "v7.2", expand.load_anchors([tsv]), figures
        )
        return expander.expand(template), expander.errors

    def test_directives_and_shorthand(self):
        template = (
            "A [[struct tb_port]] holds [[tb_port.enabled]];"
            " [[tb_port_enable()]] sets it at [[@drivers/thunderbolt/tb.c:20]"
            "].\n"
            "The option [[cfg|CONFIG_USB4]] and commit [[commit:"
            + self.head[:12]
            + "]] and [[file:drivers/thunderbolt/Kconfig]].\n\n@@c"
            " drivers/thunderbolt/tb.c:16-18,20-22 | piece ❶\n"
            "\n"
            "@@fig model\n"
        )
        anchors_text = (
            "struct tb_port\tdrivers/thunderbolt/tb.c:10\tstruct\n"
            "tb_port.enabled\tdrivers/thunderbolt/tb.c:13\tmember\n"
            "tb_port_enable\tdrivers/thunderbolt/tb.c:16\tfunction\n"
            "CONFIG_USB4\tdrivers/thunderbolt/Kconfig:1\tconfig\n"
        )
        out, errors = self.build(template, anchors_text)
        self.assertEqual(errors, [])
        base = "https://elixir.bootlin.com/linux/v7.2/source/"
        self.assertIn(
            "[`struct tb_port`](" + base + "drivers/thunderbolt/tb.c#L10)", out
        )
        self.assertIn(
            "[`tb_port.enabled`](" + base + "drivers/thunderbolt/tb.c#L13)",
            out,
        )
        self.assertIn(
            "[`tb_port_enable()`](" + base + "drivers/thunderbolt/tb.c#L16)",
            out,
        )
        self.assertIn(
            "[`tb.c:20`](" + base + "drivers/thunderbolt/tb.c#L20)", out
        )
        self.assertIn(
            "[`cfg`](" + base + "drivers/thunderbolt/Kconfig#L1)", out
        )
        self.assertIn(
            "commit ["
            + self.head[:12]
            + "](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/"
            "linux.git/commit/?id=" + self.head + ")",
            out,
        )
        self.assertIn(
            "[`Kconfig`](" + base + "drivers/thunderbolt/Kconfig)", out
        )
        self.assertIn(
            "```c\n"
            "/* drivers/thunderbolt/tb.c:16 piece ❶ */\n"
            "static int tb_port_enable(struct tb_port *port)\n",
            out,
        )
        self.assertIn("... /* 1 line, to :20 */", out)
        self.assertIn("    a ──▶ b", out)
        self.assertNotIn("@@", out)
        self.assertNotIn("[[", out)

    def test_site_text_keeps_the_path_on_a_shared_base_name(self):
        template = (
            "See [[@drivers/thunderbolt/tb.c:20]] and"
            " [[@arch/x86/pci/tb.c:1-3]] and"
            " [[@drivers/thunderbolt/Kconfig:1]].\n"
        )
        out, errors = self.build(template)
        self.assertEqual(errors, [])
        self.assertIn("[`drivers/thunderbolt/tb.c:20`]", out)
        self.assertIn("[`arch/x86/pci/tb.c:1-3`]", out)
        self.assertIn("[`drivers/thunderbolt/Kconfig:1`]", out)

    def test_a_directive_rejects_multiple_units_and_preserves_the_input(self):
        for second in (
            "drivers/thunderbolt/tb.c:24-28",
            "arch/x86/pci/tb.c:1-4",
        ):
            template = (
                "@@c drivers/thunderbolt/tb.c:16-22; "
                + second
                + " | source sites\n"
            )
            with self.subTest(second=second):
                out, errors = self.build(template)
                self.assertEqual(len(errors), 1, errors)
                self.assertIn("exactly one source unit", errors[0])
                self.assertEqual(out, template)
                self.assertNotIn("```c", out)

    def test_separate_directives_keep_their_introductions_between_fences(self):
        bridge = "The disable path clears the same flag that enable sets."
        template = (
            "The enable path sets the flag.\n"
            "\n"
            "@@c drivers/thunderbolt/tb.c:16-22\n"
            "\n" + bridge + "\n\n@@c drivers/thunderbolt/tb.c:24-28\n"
        )
        out, errors = self.build(template)
        self.assertEqual(errors, [])
        self.assertEqual(out.count("```c\n"), 2)
        self.assertEqual(out.count("/* drivers/thunderbolt/tb.c:"), 2)
        self.assertIn("```\n\n" + bridge + "\n\n```c", out)

    def test_errors_name_the_place_and_the_page_is_still_written(self):
        template = (
            "[[unknown_symbol]] at [[@drivers/thunderbolt/tb.c:900]] and"
            " [[commit:abcdef123456]]\n"
            "\n"
            "@@c drivers/thunderbolt/tb.c:4-5,6-7\n"
        )
        out, errors = self.build(template)
        self.assertEqual(len(errors), 4, errors)
        self.assertIn("`unknown_symbol`", out)
        # left in place to fix
        self.assertIn("@@c drivers/thunderbolt/tb.c:4-5,6-7", out)
        self.assertTrue(
            any("no anchor for unknown_symbol" in e for e in errors)
        )
        self.assertTrue(any("has 28 lines" in e for e in errors))
        self.assertTrue(any("does not resolve" in e for e in errors))
        self.assertTrue(any("no line to elide" in e for e in errors))

    def test_fences_are_copied_untouched(self):
        template = (
            "```c\n"
            "/* x */\n"
            "[[not_a_link]] @@c nothing\n"
            "```\n"
            "after [[@drivers/thunderbolt/tb.c:1]]\n"
        )
        out, errors = self.build(template)
        self.assertEqual(errors, [])
        self.assertIn("[[not_a_link]] @@c nothing\n", out)
        self.assertIn("[`tb.c:1`]", out)

    def test_the_command_writes_the_page(self):
        template = os.path.join(self.root, "page.tpl")
        with open(template, "w", encoding="utf-8") as handle:
            handle.write("# Title\n\n@@c drivers/thunderbolt/tb.c:24-28\n")
        out = os.path.join(self.root, "page.md")
        done = subprocess.run(
            [
                sys.executable,
                os.path.join(TOOLS, "expand.py"),
                "--tree",
                self.tree,
                "--version",
                "v7.2",
                template,
                out,
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(
            "/* drivers/thunderbolt/tb.c:24 */\n"
            "int tb_port_disable(struct tb_port *port)\n",
            Path(out).read_text(encoding="utf-8"),
        )


class TreeLocation(unittest.TestCase):
    def test_tree_is_the_checkout_whose_claude_directory_holds_the_repository(
        self,
    ):
        from tools.checkout import tree_of, tree_or_exit

        with tempfile.TemporaryDirectory() as folder:
            checkout = os.path.join(
                folder, "x", ".claude", "skills", "kernel-glossary"
            )
            os.makedirs(checkout)
            self.assertEqual(tree_of(checkout), os.path.join(folder, "x"))
            self.assertIsNone(tree_of(folder))
        self.assertEqual(
            tree_or_exit("/a/checkout", "/an/explicit/tree"),
            "/an/explicit/tree",
        )


if __name__ == "__main__":
    unittest.main()
