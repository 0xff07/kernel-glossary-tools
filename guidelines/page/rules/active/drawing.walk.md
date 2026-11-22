---
qa: auto
---

# Walk

In DETAILS, the paragraph after a figure with a legend walks its marks in order, one sentence per mark, each sentence naming its complete mark and the function as a link at its first mention in the paragraph, so the reader goes from the drawing to the code by that paragraph and can pair every mark with its sentence; the model figure under the lead or in SUMMARY carries its legend alone. Write marks as ordinary text in explanations, including @12 and @A, without backticks.

A complete mark is the whole token: @1 does not match @10 or an email address. A DETAILS figure with legend entries needs the immediately following prose paragraph, blank lines ignored. A heading, list, table, blockquote or another fence in that position is no walk paragraph. Every mark and linked function must appear in legend order; a link destination does not supply a mark.
