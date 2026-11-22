# Plain identifiers

## DETAILS

### The sentences

The core calls tb_port_enable() before the mask is written.

[`tb_port_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L30) is linked, so tb_port_enable later on the line is covered.

A `clx_mask` span, the file tb_regs.h and "tb_port_enable" in quotes are left alone, as is a path such as /sys/bus/thunderbolt and the site tb.c:30.

The option CONFIG_USB4 gates the build.

The flag TB_CL0S is a macro.

The lanes came with commit af76f532c39d (thunderbolt: add the lanes of an adapter, tb_port_lanes() included).

<!-- kg:expect
only:
- links.definition-line
findings:
- - links.definition-line
  - review
  - 7
  - tb_port_enable()
- - links.definition-line
  - review
  - 13
  - CONFIG_USB4
- - links.definition-line
  - review
  - 15
  - TB_CL0S
incomplete: []
-->
