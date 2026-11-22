# Pattern: sweep with artifacts

1. Use when a loop visits a sparse index space, skips the absent members and leaves an artifact behind at each present one: the memmaps that sparse initialisation gives the present sections, the slots a controller driver fills for its populated ports, the entries a scan creates for the devices it finds.
2. Draw the index space as one row of `┌─┬─┐` cells with the presence of each member shown inside the cell, a cursor row beneath it with an arrowhead under every visited cell and the word `skipped` under the absent ones, then a row of the artifacts as boxes under the visited cells only, and where the artifacts occupy a range, a final row of span bars with the unmapped gaps named.
3. The shape asserts which members the loop touches, that the artifacts align with the present members alone, and what the resulting range looks like; a reader checks the loop's guard against the presence row and the artifact row against the memory the page then accounts for.
4. Distinct from the sparse slot map, which shows backing without the loop that creates it; from the scan bar chart, which measures a scan rather than drawing its products; and from the object lifecycle strip, which follows one object's fields through time.

```
    sparse_init_nid over one node: the present bits, the cursor and the memmap each present section gets
    ──────────────────────────────────────────────────────────────────────────────────────────────────

    section           0     1     2     3     4     5     6     7
                    ┌─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┐
    present bit     │ ██  │ ██  │     │     │ ██  │ ██  │ ██  │     │
                    └──┬──┴──┬──┴─────┴─────┴──┬──┴──┬──┴──┬──┴─────┘

    cursor @A          ▼     ▼   skipped       ▼     ▼     ▼   skipped ──▶ pnum_end
                    ┌───┐ ┌───┐             ┌───┐ ┌───┐ ┌───┐
    memmap          │map│ │map│             │map│ │map│ │map│         @B PAGES_PER_SECTION descriptors each
                    └───┘ └───┘             └───┘ └───┘ └───┘

    vmemmap         ├───────────┤ unmapped  ├─────────────────┤ unmapped   the virtual range the maps occupy

    @A sparse_init_nid sparse.c:293  visits the present sections of the node
    @B __populate_section_memmap sparse-vmemmap.c:549  maps a section's descriptors into the vmemmap
```
