---
qa: auto
---

# Form

Every fenced C block contains exactly one source unit. Its first line is the unit's sole provenance comment, `/* path/from/tree/root.c:LINE */`, naming the first reproduced source line. A short annotation may follow the line number.

A second provenance comment fails even when it names the same file or the next source line. End the fence before another source unit and introduce the next excerpt in prose that connects it to the explanation. One unit may contain consecutive constructs and permitted counted elisions.

An elision, a run of source lines dropped between two reproduced runs, is a line of its own, `... /* N lines, to :LINE */`, indented like the line it resumes at: its leading tabs and spaces are those of the next reproduced line, so that the fence reads as code and the dots stand where the dropped lines stood.

An elision at column 0 above an indented line, or indented differently from the line after it, is a violation. A non-code fence carries no provenance; it is a figure or a quotation rather than a source excerpt.

The counted elision form is `... /* N lines, to :LINE */`, or `1 line` for one line, on a line of its own at the indentation of the line it resumes at. It identifies how many source lines are omitted and the next source line. A provenance path has a directory component except for root Kconfig or Makefile. Never put provenance in a figure or quotation fence.
