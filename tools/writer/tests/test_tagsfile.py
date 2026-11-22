"""tools/tagsfile.py: tags-file entries settled to lines on disk."""

import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

if not __package__:
    # run as a script: make the repository's packages importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools import tagsfile
from tools.writer import anchors

ROOT = os.path.dirname(
    os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
)

SOURCE = """/* a fixture */
static int
helper(int x)
{
\treturn x;
}
struct s { int m; };
#ifdef X
int twin(void)
{
\treturn 1;
}
#else
int twin(void)
{
\treturn 2;
}
#endif
int very_long_function_name_cut_by_the_pattern_length_limit_of_ctags_\
xxxxxxxxxxxxxxxxxxxxxxxxx(void)
{
}
#define SLASH "a/b\\\\c"
int broken(int a,
\t   int b)
{
\treturn a + b;
}
static void paired(int a,
\t\t   int b);
static void paired(int a,
\t\t   int b)
{
}
struct table_batch {
\tunsigned int\t\tnr;
\tvoid\t\t\t*tables[];
};
struct gather_batch {
\tstruct gather_batch\t*next;
\tunsigned int\t\tnr;
\tstruct inner {
\tunsigned int\t\tdepth;
\t} in;
\tunsigned int\t\tdepth;
\tunion {
\tunsigned int\t\tflag;
\t};
};
struct other
{
\tunsigned int\t\tflag;
\tchar\t\t\t*brace;\t/* a "}" in a comment */
};
"""

TAGS = """!_TAG_FILE_FORMAT\t2\t/extended format/
!_TAG_FILE_SORTED\t0\t/0=unsorted/
helper\ta/b.c\t/^helper(int x)$/;"\tkind:f\ttyperef:typename:int
m\ta/b.c\t/^struct s { int m; };$/;"\tkind:m\tstruct:s
twin\ta/b.c\t/^int twin(void)$/;"\tkind:f
twin\ta/b.c\t/^int twin(void)$/;"\tkind:f
verylong\ta/b.c\t/^int very_long_function_name_cut_by_the_pattern_length_\
limit_of_ctags_xxxxxxxxxxxxxxx/;"\tkind:f
SLASH\ta/b.c\t/^#define SLASH "a\\/b\\\\\\\\c"$/;"\tkind:d
withline\ta/b.c\t/^garbage$/;"\tkind:v\tline:7
numeric\ta/b.c\t4;"\tkind:v
broken\ta/b.c\t/^int broken(int a,$/;"\tkind:f
gone\ta/b.c\t/^no such line$/;"\tkind:f
paired\ta/b.c\t/^static void paired(int a,$/;"\tkind:f
paired\ta/b.c\t/^static void paired(int a,$/;"\tkind:p
nr\ta/b.c\t/^\tunsigned int\t\tnr;$/;"\tkind:m\tstruct:gather_batch\
\ttyperef:typename:unsigned int
nr\ta/b.c\t/^\tunsigned int\t\tnr;$/;"\tkind:m\tstruct:table_batch\
\ttyperef:typename:unsigned int
depth\ta/b.c\t/^\tunsigned int\t\tdepth;$/;"\tkind:m\tstruct:gather_batch
depth\ta/b.c\t/^\tunsigned int\t\tdepth;$/;"\tkind:m\
\tstruct:gather_batch::inner
flag\ta/b.c\t/^\tunsigned int\t\tflag;$/;"\tkind:m\tstruct:other
flag\ta/b.c\t/^\tunsigned int\t\tflag;$/;"\tkind:m\
\tunion:gather_batch::__anon4b5e2ee9010a
"""


class TagsFileTest(unittest.TestCase):
    def setUp(self):
        self.tree = tempfile.mkdtemp(prefix="kg-tags-")
        os.makedirs(os.path.join(self.tree, "a"))
        with open(
            os.path.join(self.tree, "a", "b.c"), "w", encoding="utf-8"
        ) as handle:
            handle.write(SOURCE)
        self.tags = os.path.join(self.tree, "tags")
        with open(self.tags, "w", encoding="utf-8") as handle:
            handle.write(TAGS)

    def tearDown(self):
        shutil.rmtree(self.tree, ignore_errors=True)

    def lookup(self, name):
        if not tagsfile.have_readtags():
            self.skipTest("no readtags on this machine")
        return [
            (p, n, k)
            for p, n, k, _f in tagsfile.entries(self.tree, self.tags, name)
        ]

    def held(self, name):
        """(line, the struct, union or enum the entry's scope names) per entry,
        in the tags file's order."""
        if not tagsfile.have_readtags():
            self.skipTest("no readtags on this machine")
        return [
            (n, tagsfile.scope_holder(f))
            for _p, n, _k, f in tagsfile.entries(self.tree, self.tags, name)
        ]

    def test_parse_pattern_and_fields(self):
        parsed = tagsfile.parse(
            "vma_link\tmm/vma.c\t/^static int vma_link(struct mm_struct"
            ' *mm)$/;"\tkind:f\tfile:\ttyperef:typename:int'
        )
        self.assertEqual(
            parsed[:5],
            (
                "vma_link",
                "mm/vma.c",
                None,
                "static int vma_link(struct mm_struct *mm)",
                True,
            ),
        )
        self.assertEqual(parsed[5]["kind"], "f")
        self.assertEqual(parsed[5]["typeref"], "typename:int")

    def test_parse_pattern_with_tab_and_escapes(self):
        parsed = tagsfile.parse(
            "vm_file\tx.h\t/^\tstruct file *vm_file;\t\\/* the file"
            ' *\\/$/;"\tkind:m\tstruct:vm_region'
        )
        self.assertEqual(parsed[3], "\tstruct file *vm_file;\t/* the file */")
        self.assertEqual(parsed[5]["struct"], "vm_region")

    def test_parse_numeric_and_truncated(self):
        self.assertEqual(tagsfile.parse('x\ta.c\t12;"\tkind:v')[2], 12)
        name, path, number, body, full, _fields = tagsfile.parse(
            'x\ta.c\t/^int very_long(void/;"\tkind:f'
        )
        self.assertEqual(
            (number, body, full), (None, "int very_long(void", False)
        )

    def test_head_of_split_signature(self):
        lines = SOURCE.split("\n")
        # `static int` above `helper(int x)`
        self.assertEqual(tagsfile.head_of(lines, 3), 2)
        # `int twin(void)` after `#ifdef X`
        self.assertEqual(tagsfile.head_of(lines, 9), 9)
        # `int broken(int a,` after a `#define`
        self.assertEqual(tagsfile.head_of(lines, 24), 24)

    def test_split_signature_moves_to_the_head_line(self):
        self.assertEqual(self.lookup("helper"), [("a/b.c", 2, "f")])

    def test_member_pattern(self):
        self.assertEqual(self.lookup("m"), [("a/b.c", 7, "m")])

    def test_twins_take_successive_lines(self):
        self.assertEqual(
            self.lookup("twin"), [("a/b.c", 9, "f"), ("a/b.c", 14, "f")]
        )

    def test_prototype_and_definition_sharing_a_first_line_settle_by_kind(
        self,
    ):
        """A prototype that repeats the definition's first line gets the same
        pattern as the definition: the function entry settles to the line a
        body follows, the prototype entry to the line a `;` ends.
        """
        self.assertEqual(
            self.lookup("paired"), [("a/b.c", 30, "f"), ("a/b.c", 28, "p")]
        )

    def test_same_text_members_settle_inside_their_holder(self):
        """Two structs of one file declare `nr` with the same text, and the
        tags file lists the entries by holder name, here the second struct
        first: each entry takes the line inside its own holder's body, not the
        k-th matching line of the file."""
        self.assertEqual(
            self.held("nr"), [(40, "gather_batch"), (35, "table_batch")]
        )

    def test_member_of_a_nested_struct_and_of_its_parent(self):
        self.assertEqual(
            self.held("depth"), [(44, "gather_batch"), (42, "inner")]
        )

    def test_anonymous_union_member_is_held_by_the_struct_around_it(
        self,
    ):
        """`struct other` opens its brace on the next line and holds a `}` in a
        comment."""
        self.assertEqual(
            self.held("flag"), [(51, "other"), (46, "gather_batch")]
        )

    def test_body_end_and_holders(self):
        lines = SOURCE.split("\n")
        self.assertEqual(tagsfile.body_end(lines, 34), 37)
        # the `}` in the comment does not close it
        self.assertEqual(tagsfile.body_end(lines, 49), 53)
        # a prototype: a `;` before any body
        self.assertIsNone(tagsfile.body_end(lines, 28))
        spans = tagsfile.holders(self.tree, "a/b.c")
        self.assertEqual(
            spans,
            [
                (7, 7, "s"),
                (34, 37, "table_batch"),
                (38, 48, "gather_batch"),
                (41, 43, "inner"),
                (49, 53, "other"),
            ],
        )
        self.assertEqual(tagsfile.holder_at(spans, 42), "inner")
        self.assertEqual(tagsfile.holder_at(spans, 46), "gather_batch")
        self.assertIsNone(tagsfile.holder_at(spans, 30))

    def test_scope_holder(self):
        self.assertEqual(tagsfile.scope_holder({"struct": "page"}), "page")
        self.assertEqual(
            tagsfile.scope_holder({"union": "page::__anon4b5e2ee9010a"}),
            "page",
        )
        self.assertEqual(
            tagsfile.scope_holder({"struct": "outer::inner"}), "inner"
        )
        self.assertIsNone(
            tagsfile.scope_holder({"struct": "__anon4b5e2ee90108"})
        )
        self.assertIsNone(tagsfile.scope_holder({"kind": "f"}))

    def test_resolver_keeps_anonymous_union_member_under_its_struct(
        self,
    ):
        """anchors.py asks the tags file for `holder.member`: an entry scoped
        `union:gather_batch::__anon...` is a member of gather_batch, a nested
        struct's member is not its parent's, and same-text members of two
        structs each answer for their own holder."""
        if not tagsfile.have_readtags():
            self.skipTest("no readtags on this machine")

        def ask(holder, member):
            return anchors.resolve_with_tags(
                self.tree, self.tags, holder, None, member, None
            )

        self.assertEqual(
            ask("gather_batch", "flag"), [("a/b.c", 46, "member")]
        )
        self.assertEqual(ask("other", "flag"), [("a/b.c", 51, "member")])
        self.assertEqual(ask("inner", "depth"), [("a/b.c", 42, "member")])
        self.assertEqual(
            ask("gather_batch", "depth"), [("a/b.c", 44, "member")]
        )
        self.assertEqual(ask("table_batch", "nr"), [("a/b.c", 35, "member")])
        self.assertEqual(ask("gather_batch", "nr"), [("a/b.c", 40, "member")])
        self.assertEqual(ask("s", "m"), [("a/b.c", 7, "member")])
        self.assertEqual(ask("table_batch", "flag"), [])

    def test_truncated_pattern_matches_as_a_prefix(self):
        self.assertEqual(self.lookup("verylong"), [("a/b.c", 19, "f")])

    def test_escaped_slashes_and_backslashes(self):
        self.assertEqual(self.lookup("SLASH"), [("a/b.c", 22, "d")])

    def test_line_field_and_numeric_entry_stand(self):
        self.assertEqual(self.lookup("withline"), [("a/b.c", 7, "v")])
        self.assertEqual(self.lookup("numeric"), [("a/b.c", 4, "v")])

    def test_continued_parameter_list_keeps_its_first_line(self):
        self.assertEqual(self.lookup("broken"), [("a/b.c", 23, "f")])

    def test_pattern_the_file_no_longer_spells_yields_nothing(self):
        self.assertEqual(self.lookup("gone"), [])
        self.assertEqual(self.lookup("absent"), [])


if __name__ == "__main__":
    unittest.main()
