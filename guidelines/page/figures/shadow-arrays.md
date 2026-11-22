# Pattern: shadow arrays

1. Use when two arrays share one index and differ in their cell size alone, and the point is that a conversion between them is an index change: the memmap beside the physical memory it describes, a bitmap beside the slots it tracks, a per-entry side table beside its main table.
2. Draw the two arrays side by side as `┌─┬─┐` cells with the same index labels in the same order, the narrow cells on the left and the wide cells on the right, each array named above and its cell size stated below; an arrow from the shared index into each array carries the mark of the conversion that produces that address, and an upward arrow from the narrow array carries the inverse.
3. The shape asserts that the two arrays are the same sequence at two scales and that the index is the only state a conversion needs; the reader compares the cell sizes to see the memory ratio and follows the arrows to see which operation lands where.
4. Distinct from lockstep rulers, which show several coordinate systems as rulers with holes and a worked object; from the two-view memory strip, which is one buffer under two rulers; and from the N-to-M mapping, whose arrows connect unequal sets.

```
    The frame number is the shared index of two arrays that differ only in their cell size
    ──────────────────────────────────────────────────────────────────────────────────────

                  index n                                                   index n
                          │ @1 vmemmap + n                                          │ @3 n << PAGE_SHIFT
                          │                                                         │
                 vmemmap  ▼                                physical memory          ▼
                 ┌───┬───┬───┬───┬───┬───┬───┬───┐         ┌──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┐
                 │ 0 │ 1 │ 2 │ 3 │ n │   │   │   │         │  0   │  1   │  2   │  3   │  n   │      │      │      │
                 └───┴───┴───┴───┴───┴───┴───┴───┘         └──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┘
                 64 bytes a cell, one descriptor           4 KiB a cell, one frame
                          ▲ @2 page − vmemmap

    @1 __pfn_to_page memory_model.h:46  adds the frame number to vmemmap
    @2 __page_to_pfn :47  subtracts vmemmap from the descriptor's address
    @3 page_to_phys :85  shifts the frame number into a physical address
```
