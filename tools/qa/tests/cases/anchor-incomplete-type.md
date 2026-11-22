# An opaque type the kernel never defines

## DETAILS

### The handle

[`struct kg_opaque`](https://elixir.bootlin.com/linux/v7.2/source/mm/kg_opaque.h#L6) is declared and never defined, so a pointer to it passes only through [`kg_opaque_bits()`](https://elixir.bootlin.com/linux/v7.2/source/mm/kg_opaque.h#L8) and its kin.

<!-- kg:expect
only:
- links.definition-line
findings: []
incomplete: []
-->
