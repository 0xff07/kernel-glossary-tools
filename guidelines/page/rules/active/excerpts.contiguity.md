---
qa: auto
---

# Contiguity

An excerpt reads as code. A counted elision inside a function resumes inside the same function. Every reproduced run after any elision, including an elided long definition, contains at least three contiguous source lines or just the closing line. A cataloged function is walked whole in consecutive stage pieces without elision.

Only a definition longer than the 40-line source target may omit one contiguous run of members the page never mentions; name that run in prose. Mark it with `... /* N lines, to :LINE */`, or `1 line`, on a line of its own indented like the line it resumes at, giving the exact number omitted and the next reproduced source line.

A unit of a function the page does not catalog may end after the last line of its stage, with nothing after it; an elision line at the end of a unit or into another function is a truncation and fails.
