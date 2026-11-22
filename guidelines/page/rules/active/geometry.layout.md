---
qa: off
---

# Layout

Every figure carries a short title underlined with a `────` rule, a clause saying what the drawing shows, so that the titles read in page order give the page's outline and two figures of one subsection are told apart; where several sub-diagrams share one fence, each has its title.

On a page the whole figure is indented four spaces inside the fence; a reference figure in the catalogue keeps the indent it has and may go untitled, and a copy on a page is re-indented and titled. Each box keeps its own left and right border columns from top to bottom, with corners joining its sidewalls; independent boxes may differ in width and indent.

Give every intended connection matching directions at each join, and follow each connector through its bends and branches to its ends. Legends, per-bit meanings and comments live inside the same fence, under the drawing. A prose paragraph sits above the fence. Inspect the title rule, indent, box borders, connector ends and legend placement.

Count display cells including the four-space indent, titles and legends. Mn, Me and Cf characters have width zero; East Asian Width W/F characters have width two; others width one. Keep lines within 120 cells. A single register drawn as one row with L-connectors may be wider; inspect its width and readability in the intended monospace rendering.

For that wide single-register exception only, the ruler begins with `bit` and a digit; exactly one top and one lower bottom border enclose its cells, no interior divider opens with a divider junction, and a callout elbow lies below it. Read ambiguous-width glyphs in the intended monospace rendering. Review intentional joins, crossings, gaps, labels and open axes against their meaning.

Inspect every figure by this procedure, legend entries left out of the connection tests. An orthogonal box-drawing glyph has the directions its Unicode name states, whatever its weight, rounding or doubling; a diagonal has no orthogonal port; a cardinal arrowhead is a triangle or an up, down, left or right arrow, with a tip side and a shaft side. Each of the following is a candidate, one per figure row, naming the row, the display columns and the directions that should connect:

1. A join: two neighbouring line glyphs where one opens toward the other and the other lacks the reciprocal direction, naming the glyph that lacks it. A span's endcaps (`├───┤`) keep a vertical port only where the glyph above or below supplies the reciprocal port. A straight dashed line touching a transverse line may be a guide crossing and is read. A shaft only on the tip side of an arrowhead is a candidate; a head embedded in a continuous shaft and a tip facing a transverse boundary are allowed.
2. A shifted vertical: across adjacent rows, a downward port and an upward port with nothing at their expected columns, paired uniquely one or two cells apart, reporting the lower glyph's column and the expected one.
3. A frame: a simple frame opens with a down-right corner, a horizontal run and a down-left corner, and closes at the next up-right corner in the same left column with a horizontal bottom; a bottom corner away from the top's right column, or a side column without up and down ports on an interior row, is a candidate. Independent frames keep their own bounds, and annotations outside a frame do not extend it.
4. A floating run: a maximal vertical run of non-dashed glyphs with up and down ports alone whose two ends meet blank cells, with no letter or digit on any of its rows.

Not breakage, cleared and never fixed:

- an annotation running past a box's right border,
- independent boxes at different widths or indents,
- a `│` above `▼` or below `▲`,
- a C expression in annotation text,
- a dashed guide or barrier crossing a border without connecting, and
- a span bar with no box above it.

Repair a confirmed defect by its class:

- replace a loose extent marker with `├───┤` sized to the box, with the label beneath when it no longer fits;
- replace a wrong corner or junction with the glyph for its actual connections;
- re-anchor a trunk at the intended junction or move it to that column;
- delete a trunk hanging in blank space and redraw the relationship as a straight arrow between facing borders with its label in the gutter above;
- re-pad a box's rows to its own width, leaving annotations outside it alone.

Re-read the affected boxes and every connected path after a batch of repairs, because a moved column breaks the next junction.

A span bar is a `├`, a horizontal run and a `┤` on one row; its two endcaps are exempt from the join test, and so are the junctions between them when nothing else on the row carries a port. A bar closed on one side only (`─────┤`, a `├` with no `┤`) is no span bar, so the stray endcap's vertical ports are joins to test: close both ends, or give the glyph above or below the reciprocal port.

A bare vertical run with blank cells at both ends and no letter or digit on its rows is a floating run; a run that meets a glyph, a label or an axis at either end is not.
