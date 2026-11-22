# Weakly supported claims, well formed

## SUMMARY

The model is one port enabled by its peer.

## SPECIFICATIONS

No specification applies to the fixture router.

## COVERAGE

### The port
- [`'\<tb_port_enable\>':'drivers/thunderbolt/tb.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L30): enables a port

## DOCUMENTATION

- [`Documentation/driver-api/thunderbolt.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/driver-api/thunderbolt.rst): the fixture's documentation

## OTHER SOURCES

### Added by kg

- [thunderbolt: add the fixture router (commit 5e8f80d3de8d)](https://lore.kernel.org/r/fixture-router@example.invalid)

## DETAILS

### The port is enabled by its peer

[`tb_port_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L30) tests the peer and sets the port bonded when the peer answers.

## WEAKLY SUPPORTED CLAIMS

The claims below rest on less than the rest of this page does, and this page could not strengthen them. Verify them before relying on them.

- Not cross-checked, in "The port is enabled by its peer": the three callers of [`tb_port_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L30) were found by one search of the tree; the files of other architectures were not compiled.
- Simplified, in SUMMARY: the model draws one peer per port; the exact rule, a peer per lane, stands under "The port is enabled by its peer".
- Taken as given, in the lead: [`CONFIG_USB4`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/Kconfig#L2) is taken from the documented configuration, which this environment could not resolve.

<!-- kg:expect
only:
- sections.weakly-supported-claims
- sections.order
findings: []
incomplete: []
-->
