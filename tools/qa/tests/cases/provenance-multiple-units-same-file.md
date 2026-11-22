# Separate locations in one file need separate fences

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
/* drivers/thunderbolt/tb.c:38 */
static int tb_port_clx_write(struct tb_port *port, unsigned int clx)
{
	port->config.type = clx;
	return 0;
}
/* drivers/thunderbolt/tb.c:30 */
int tb_port_enable(struct tb_port *port)
{
	if (!tb_port_has_remote(port))
		return -ENODEV;
	port->bonded = true;
	return 0;
}
```

<!-- kg:expect
only:
- provenance.form
- excerpts.verbatim
findings:
- - provenance.form
  - FAIL
  - 18
  - /* drivers/thunderbolt/tb.c:38 */
- - provenance.form
  - FAIL
  - 24
  - /* drivers/thunderbolt/tb.c:30 */
-->
