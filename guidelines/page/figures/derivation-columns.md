# Pattern: derivation columns

1. Use when a chain of constants is derived step by step from one starting value and the page compares the chain under two or more configurations: the section constants of an architecture under two paging depths, the timing constants of a controller under two clock rates, the sizes of a table under two page sizes.
2. Draw one column per configuration, each a vertical chain of boxes joined by a trunk, every box naming the constant and its value under that configuration and the trunk segment between two boxes naming the operation that derives the lower from the upper; put the configuration's name above its column, the selector that picks the configuration between the columns, and a shared operand's definition under the figure.
3. The shape asserts that the derivation is one computation run under different inputs: the operations match row by row, the values differ, and the reader can follow either column down and compare any row across. Keep the rows aligned across columns, since a row that slips breaks the comparison.
4. Distinct from the data-dependency figure, whose inputs feed one transform in a graph; from the side-by-side struct comparison, which compares layouts rather than computations; and from values on one scale, which places results on an axis without their derivation.

```
    The section constants of x86-64 under the two paging depths, one derivation run twice
    ────────────────────────────────────────────────────────────────────────────────────

        4-level paging                                            5-level paging
        ┌──────────────────────────┐                              ┌──────────────────────────┐
        │ MAX_PHYSMEM_BITS 46      │    pgtable_l5_enabled()      │ MAX_PHYSMEM_BITS 52      │
        └─────────────┬────────────┘    picks the column          └─────────────┬────────────┘
                        − SECTION_SIZE_BITS 27                                    − SECTION_SIZE_BITS 27
        ┌─────────────┴────────────┐                              ┌─────────────┴────────────┐
        │ SECTIONS_SHIFT 19  «A»   │                              │ SECTIONS_SHIFT 25  «A»   │
        └─────────────┬────────────┘                              └─────────────┬────────────┘
                        1 << SECTIONS_SHIFT                                       1 << SECTIONS_SHIFT
        ┌─────────────┴────────────┐                              ┌─────────────┴────────────┐
        │ NR_MEM_SECTIONS  «B»     │                              │ NR_MEM_SECTIONS  «B»     │
        │ 2^19 = 524,288           │                              │ 2^25 = 33,554,432        │
        └─────────────┬────────────┘                              └─────────────┬────────────┘
                        ÷ SECTIONS_PER_ROOT 256                                   ÷ SECTIONS_PER_ROOT 256
        ┌─────────────┴────────────┐                              ┌─────────────┴────────────┐
        │ NR_SECTION_ROOTS  «C»    │                              │ NR_SECTION_ROOTS  «C»    │
        │ 2,048 roots, 16 KiB      │                              │ 131,072 roots, 1 MiB     │
        └──────────────────────────┘                              └──────────────────────────┘

    SECTIONS_PER_ROOT = PAGE_SIZE / sizeof(struct mem_section) = 4096 / 16

    «A» SECTIONS_SHIFT page-flags-layout.h:31  subtracts the section size from the address width
    «B» NR_MEM_SECTIONS mmzone.h:1957  raises two to the section-number width
    «C» NR_SECTION_ROOTS mmzone.h:2045  divides the sections among page-sized roots
```
