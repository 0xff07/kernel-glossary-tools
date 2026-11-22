---
qa: auto
---

# Marks

A marked figure takes one of the six figure families, and the family tells the reader which figure a mark belongs to: two marked figures that follow each other on the page use different families, and the marked figures of one subsection all differ from each other.

Within that, the choice is free; a page drafted in one pass takes the families in the order ① → ➊ → «1» → «A» → @1 → @A, starting at the first family that fits, and a figure added later takes the first family in that order that its distinct marks fit and that neither the figure before it, the figure after it nor another figure of its subsection uses, so that adding or removing a figure changes no other figure's marks.

One figure fence uses one family, counted from 1 or A without a gap. Use plain guillemets around a decimal number or one capital, with no hidden characters; the decimal forms have no leading zero. Count distinct marks, so repeated appearances of one mark take one place, and never use a family whose capacity the figure's distinct marks exceed. Unmarked figures and prose outlines take no family.

The ①–⑩ and ➊–➓ are reserved for figures, their legends and the sentences that refer to their marks; prose never numbers a series of its own with them. A family reused later on the page may need the figure's subject or title in the explanation to make the reference clear.

The six **figure families**, in the order a page drafted in one pass takes them, are:

1. the circled digits `①`–`⑩`,
2. the sans-serif negative circled digits `➊`–`➓`,
3. the guillemet digits `«1»`, `«2»`, …,
4. the guillemet capitals `«A»`–`«Z»`,
5. the at digits `@1`, `@2`, … and
6. the at capitals `@A`–`@Z`.

A mark's **index** is its decimal value, or A=1 through Z=26; a decimal mark has no leading zero. The two circled families hold ten marks each, the two capital families 26, and the two decimal families any number; a mark beyond a family's capacity is no mark of it.

The circled digits `①`–`⑩` and `➊`–`➓` are **reserved** for figures: outside a figure they appear only where a sentence refers to a figure's mark, never as the numbering of a prose series. The circled digits `⑪`–`⑳`, whose glyphs render at another width, are used nowhere on a page: on a drawing line they are unsupported marks, in an outline reserved marks, and in prose they number nothing.

The **recognized prose families** include:

- the negative circled digits `❶`–`❿` and `⓫`–`⓴`,
- the circled capitals `Ⓐ`–`Ⓩ`,
- the circled small letters `ⓐ`–`ⓩ`,
- the double-circled digits `⓵`–`⓾`,
- the negative squared capitals `🅰`–`🆉`,
- the parenthesized digits `⑴`–`⒇` and
- the parenthesized small letters `⒜`–`⒵`.

They are examples, not a whitelist; another family's numbering is read.

A single-glyph mark is a token by itself. A guillemet or at mark is matched whole, with no word character, `@` or guillemet on either side; an at mark further neither follows `.`, `+`, `%` or `/`, nor precedes `/`, nor precedes a dot followed by a word character. So `@1` is not part of `@10`, `@A1` or an e-mail address, while `──@1──` and a sentence ending `@1.` carry it. Such a token is a **complete mark**.

A **mark-like token** is a single glyph of any family named here, the figure families and the recognized prose families alike, or a guillemet token `«…»` or an at token `@…` of non-space characters within the boundaries above.

A mark-like token on a figure's drawing line that is no complete mark of a figure family, an unused `⑪`, a prose family's glyph or a malformed `«x»` or `@x`, is an **unsupported mark**; a token beginning with a box-drawing character (U+2500–U+257F) belongs to the drawing.

A figure's marks are read as its legend entries' marks followed by the drawn marks that have no entry, and two marks written back to back are not complete marks: write `«1» «2»`, never `«1»«2»`.
