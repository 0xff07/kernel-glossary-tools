---
qa: auto
---

# Verbatim

Whatever the page explains, the real code is on it, verbatim: never fabricated, paraphrased or approximated, located with the question-appropriate research tools and read on disk, tabs and comments kept. A symbol whose code cannot be located gets no block.

A unit maps onto its file when, from the line its provenance names, each reproduced line equals the file's line at that position byte for byte after UTF-8 decoding, tabs, trailing spaces and carriage returns included, the position advancing by one, and each counted elision drops exactly the file lines from the position to the line before the one it resumes at.

A unit that does not map is a violation named by its first differing line; content that matches elsewhere under a wrong line number is one too, and so is an elision whose count or resumption line is wrong.
