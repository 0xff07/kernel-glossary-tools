# A symbol link anchored at a comment line

## DETAILS

### The kerneldoc line is no declaration

[`tb_port_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L25) marks a port bonded; the link lands on the kerneldoc line that names the function, which declares nothing and is no macro invocation.

<!-- kg:expect
only:
- links.definition-line
findings:
- - links.definition-line
  - FAIL
  - 7
  - tb_port_enable()
incomplete: []
-->
