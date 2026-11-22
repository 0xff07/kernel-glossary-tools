---
qa: off
---

# One line paragraphs

Every paragraph is one unwrapped line, and a blank line separates it from the next. Fences, figures, list items, table rows and blockquotes retain their own line structure. Cited code retains its tabs.

A raw prose line is a nonblank line outside fences that is not a heading beginning `#`, a blockquote beginning `>`, a table row beginning `|`, an optionally indented list item beginning `- `, `* ` or digits plus `. `, or material beginning four spaces or a tab. Two adjacent raw prose lines fail this rule; inspect them before a renderer joins lines into a paragraph.
