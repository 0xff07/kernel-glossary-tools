# Weakly supported claims, faults of form

## COVERAGE

### The port
- [`'\<tb_port_enable\>':'drivers/thunderbolt/tb.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L30): enables a port

## DETAILS

### The port is enabled by its peer

[`tb_port_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L30) tests the peer and sets the port bonded when the peer answers.

## WEAKLY SUPPORTED CLAIMS

The claims below rest on less than the rest of this page does, and this page could not strengthen them. Verify them before relying on them.

- Counted one way, in "The port is enabled by its peer": the count of callers comes from one search of the tree.
- Not cross-checked, in "A heading the page lacks": the count of callers comes from one search of the tree.
- Code not shown, in "The port is enabled by its peer": `tb_port_reset` is read at its seam only.
- Simplified, in SUMMARY: about 50 sentences of the model stay long.
A stray paragraph after the list.

## OTHER SOURCES

### Added by kg

- [thunderbolt: add the fixture router (commit 5e8f80d3de8d)](https://lore.kernel.org/r/fixture-router@example.invalid)

<!-- kg:expect
only:
- sections.weakly-supported-claims
findings:
- - sections.weakly-supported-claims
  - FAIL
  - 14
  - "WEAKLY SUPPORTED CLAIMS"
- - sections.weakly-supported-claims
  - FAIL
  - 18
  - 'Counted one way, in "The port is enabled by its peer"'
- - sections.weakly-supported-claims
  - FAIL
  - 19
  - "A heading the page lacks"
- - sections.weakly-supported-claims
  - FAIL
  - 20
  - "tb_port_reset"
- - sections.weakly-supported-claims
  - review
  - 21
  - "50 sentences"
- - sections.weakly-supported-claims
  - FAIL
  - 22
  - "A stray paragraph after the list."
incomplete: []
-->
