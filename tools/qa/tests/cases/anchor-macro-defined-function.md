# A function a macro invocation defines

## DETAILS

### The entry point

[`fixture_entry`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/entry.c#L10) returns the port's mask, and the same line defines it as [`DEFINE_FIXTURE_ENTRY(fixture_entry)`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/entry.c#L10); a link to the macro's own line, [`DEFINE_FIXTURE_ENTRY`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/entry.c#L8), is the macro.

<!-- kg:expect
only:
- links.definition-line
findings: []
incomplete: []
-->
