---
qa: auto
---

# Weakly supported claims

A claim stands on the page as well supported as the page can make it, and the page says nowhere how it was checked.

Before a claim is listed here it is strengthened or made exact:

- a count, a classification or a negative gets its second check, or its sentence states the scope the one check covered (the files one build compiles, one directory, one architecture);
- a claim about code gets the code shown, or is reduced to what the shown lines establish;
- a model figure's simplification gets the exact rule in the prose beside the figure;
- a number measured on one build names that build beside it;
- a value taken from the documented configuration names the option.

What remains is a claim the page could not strengthen, and the section WEAKLY SUPPORTED CLAIMS, the last H2, lists it so that a reader checks it before relying on it. The section stands only when it has an entry: a page whose every claim is supported has no such section, and an empty one is a fault.

The section opens with the paragraph `The claims below rest on less than the rest of this page does, and this page could not strengthen them. Verify them before relying on them.` and holds nothing else but its list of at most 10 entries, each one line in the form `- <class>, in "<heading>": <what the page claims, what it rests on, and what was out of reach>`, where `<heading>` is a DETAILS H3 heading of this page, verbatim, or `SUMMARY` or `the lead` without quotes for a claim made there, and `<class>` is one of these:

`<classes>`: Not cross-checked, Code not shown, Simplified, Taken as given.

- Not cross-checked: a count, a classification or a negative confirmed one way because the second check could not reach it (a tool that indexes no members or macros, a build that compiles none of the files, a tree-wide pass the machine cannot afford); the entry names the scope the one check covered.
- Code not shown: a claim that rests on code this page cannot reproduce, a source that is no C file, a subject outside this page's, or a function another page reads whole and this page shows at its seam; the entry names the function and what the claim takes from it.
- Simplified: a model figure under the lead or in SUMMARY that draws a simpler rule than the code and cannot carry the exception; the entry names the exact rule and the heading under which the page states it.
- Taken as given: a value this environment could not resolve, a configuration option or a toolchain fact taken from the documented configuration without a local build; the entry names the value and what a reader with the toolchain would check.

An entry is written in the kernel's words and the reader's, the functions, files and options, this page, the figure, the text below the figure, never the words of the page's production, and it states rather than hedges: what was not measured, not what may differ. Every span in an entry is linked at its definition line.

A matter of form, a length, a count of sentences or lines, a paragraph's place or a figure's geometry, is no claim and does not belong here: a digit followed by lines, words or sentences in an entry is a candidate. More than 10 entries means the page owes verification, not disclosure, and fails.
