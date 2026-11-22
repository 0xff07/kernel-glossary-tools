---
qa: off
---

# Tool per question

Research asks four kinds of question and uses the tool fit for each:

| question | tool |
|---|---|
| where a construct is defined and who calls it | a whole-tree symbol index (the one the campaign block names, or the tree's `tags` file) |
| what a line is | a parse of its file |
| what a symbol's type is, which construct a same-named identifier denotes, what a macro expands to and what the tree compiles | the compile database the campaign block names |
| what the text says | `git grep` and `git log`, with semcode `dig` for the mailing-list thread behind a commit and for nothing else |

Every line number a tool reports is re-read on disk before it reaches the page, and a machine without a tool does that class by hand and says so in the worksheet.

The compile database establishes existence, types and expansions, never a gate: whether the documented build compiles a file or a branch is read from the subsystem Makefile's `obj-$(CONFIG_...)` lines, the `#if` conditions around the code and the documented config's resolved values. The research-tools note the workflow documents says what each tool answers and where it errs.
