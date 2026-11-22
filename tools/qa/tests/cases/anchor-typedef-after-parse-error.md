# A typedef after a prototype the parser cannot read

## DETAILS

### The freelist word

[`freelist_full_t`](https://elixir.bootlin.com/linux/v7.2/source/mm/kg_slab.h#L19) is the word a freelist compare-and-exchange moves whole, and the kmalloc prototypes above it carry parameter and attribute macros that leave the parser no construct to tag.

<!-- kg:expect
only:
- links.definition-line
findings: []
incomplete: []
-->
