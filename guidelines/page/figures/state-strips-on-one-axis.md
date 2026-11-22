# Pattern: state strips on one axis

1. Use when every position of one index space ends in a state that the ranges covering it decide, and one or more passes write that state: the frames of a node after memmap initialization and after the hand-over to the buddy allocator, the blocks of a device after an allocation pass, the slots of a bitmap after each reservation.
2. Draw the axis once as a span bar `├───┤` with both ends labelled, and under it one row per input in its own notation: the covering ranges as boxes at their extents, a partition as one span bar that `┼` divides, the name of each part inside it. Then draw one strip per pass, a run of block shades `░ ▓ █` with one character for each column of the axis, `after <pass>` at its left and each run named beneath it. Close with a legend that gives every shade its state and a sentence saying what a position outside every range takes.
3. The shape asserts that the state is a function of the position: the reader drops a vertical from any column through the inputs to each strip, reads which range and which part cover it and what each pass leaves there, and compares two strips to see what the later pass changed. Keep every row on the same columns, so that edges which coincide in the code coincide in the drawing; the lengths are schematic.
4. Distinct from ranges on one address axis, whose rows are the ranges themselves and what an operation makes of them, where this draws the state of every position under them; from the sweep with artifacts, which draws a loop's cursor and what it leaves at the present members alone, where here a position no range covers gets a state too; and from the object lifecycle strip, whose axis is time and whose bars are one object's fields.

```
    One node's frames on one pfn axis, before and after the two boot passes
    ───────────────────────────────────────────────────────────────────────

                       ├────────────────────────────────────────────────────────────────────────────────────────────┤
                       pfn 0                                           end of the last range, rounded up to a section
                                 ┌────────────────────────┐          ┌────────────────────────────────────┐
    memblock.memory              │ memory range           │          │ memory range                       │
                                 └────────────────────────┘          └────────────────────────────────────┘

    zone spans         ├─────────────────── ZONE_DMA32 ────────────────────────────┼───────── ZONE_NORMAL ──────────┤

    after memmap_init  ░░░░░░░░░░▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░
                       hole      count 1                   hole      count 1                               tail

    after the          ░░░░░░░░░░░░░░░░████████████████████░░░░░░░░░░██████████████░░░░░░░░████████████████░░░░░░░░░░
    hand-over                    resvd   buddy                         buddy       resvd     buddy

    ▓ zone, node and count 1 written     ░ the same, with PG_reserved set     █ handed to the buddy allocator, count 0
    a hole takes the zone and node of the memory range above it; the tail takes the last zone that was initialized
```
