# One source unit can contain consecutive functions

## DETAILS

### The excerpt identifies its source

The code below shows the source sites discussed here.

```c
/* drivers/thunderbolt/tb.c:30 */
int tb_port_enable(struct tb_port *port)
{
	if (!tb_port_has_remote(port))
		return -ENODEV;
	port->bonded = true;
	return 0;
}

static int tb_port_clx_write(struct tb_port *port, unsigned int clx)
{
	port->config.type = clx;
	return 0;
}
```

<!-- kg:expect
only:
- provenance.form
- excerpts.verbatim
findings: []
-->
