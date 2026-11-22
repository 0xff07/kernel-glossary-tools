# Pattern: subdivision tree

1. Use when an operation halves one object toward a target until a size is reached, leaving pieces of descending sizes in place, and when a later walk steps over the pieces by their own sizes: the non-uniform split of a large folio, a buddy block split down to an order, a range carved toward an alignment.
2. Draw the halvings as rows of span bars `├───┤├───┤` under one page ruler, each row splitting the half that holds the target and keeping the other half as it is, then the pieces as `┌─┬─┐` cells in physical order with their sizes named, and the walk as a row of `●───▶` steps whose lengths are the pieces' sizes; mark the halving loop, the piece preparation and the walk's step.
   - A page that shows the walk alone draws the pieces row and the walk row and leaves the halvings to a page that shows the split.
3. The shape asserts the order of the pieces, their sizes and the fact that the walk's step length is the piece's own size, so a reader can count the pieces, check that they sum to the original and see why a fixed stride would miss boundaries.
4. Distinct from the before-and-after transformation, which shows one structure on two sides of an operation without the intermediate halvings; from parent and children fan-out, whose children are not ordered pieces of the parent; and from lengths against one ruler, which tests whether parts fit a budget.

```
    One order-4 folio split toward its last page, halved until the piece holding that page is order 0
    ─────────────────────────────────────────────────────────────────────────────────────────────────

    page            0                               8               12      14  15
                    ├───────────────────────────────────────────────────────────────┤ order 4, before the split
                    ├───────────────────────────────┤├──────────────────────────────┤ «1» the first halving
                                                    ├───────────────┤├──────────────┤ the second, same half
                                                                    ├───────┤├──────┤ the third
                                                                            ├───┤├──┤ the fourth, new order 0

                    ┌───────────────────────────────┬───────────────┬───────┬───┬───┐
    pieces          │ order 3                       │ order 2       │ ord 1 │ 0 │ 0 │ «2» the leaves, in physical order
                    └───────────────────────────────┴───────────────┴───────┴───┴───┘
    walk            ●──────────────────────────────▶●──────────────▶●──────▶●──▶●──▶  «3» steps by each piece's own size

    «1» __split_unmapped_folio huge_memory.c:3857  halves one order at a time down to the new order
    «2» __split_folio_to_order huge_memory.c:3685  makes each piece a folio of its order
    «3» remap_page huge_memory.c:3644  steps to the next piece with folio_next
```
