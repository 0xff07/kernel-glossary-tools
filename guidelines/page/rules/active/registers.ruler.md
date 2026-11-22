---
qa: auto
---

# Ruler

The ruler runs from the high bit down to 0, one bit per two-column slot, in two rows (tens, then ones) whenever an index reaches two digits; the full per-bit `┌─┬...─┐` border keeps every cell aligned.

- DWORD labels sit in a left gutter at column 5 with the box border at column 11, columns counted from one including the four-space indent;
- `├──┬──┼──┴──┤` divider rows transition between layouts;
- each multi-bit cell carries its name and `(hi:lo)`;
- a legend beneath maps each field to its macro and cached struct field as `NAME = MACRO (meaning)`;
- reserved bits get no trunk;
- each elbow lands on its own trunk, the rightmost callout nesting first.

A cell boundary sits on the bit grid the top border draws, and an interior divider carries a junction exactly where the rows above and below have a boundary, `┼` for both, `┬` for below alone, `┴` for above alone and `─` for neither.


This rule applies to a figure whose primary subject is a register, TRB, context, descriptor or packet-header bit layout, a flag word of several bit fields or flag bits, or a pointer or word whose low or high bits carry a tag. A bit strip inside a larger structural figure follows the host figure's style.

Choose DWORD-grid with names inside cells for a multiword structure or a register whose labels fit; choose one row with L-shaped callouts for a register made mostly of single-bit fields. A register is one value at one address, however wide; a structure has successive DWORD rows.
