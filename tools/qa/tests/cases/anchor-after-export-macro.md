# A function after an ACPICA-style export line

## DETAILS

### The second export

[`tb_export_first`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/export.c#L10) returns the port's mask, and [`tb_export_second`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/export.c#L17), defined after the export line of the first, returns it plus one.

<!-- kg:expect
only:
- links.definition-line
findings: []
incomplete: []
-->
