# Separate files need separate fences

## DETAILS

### The excerpt identifies its source

The code below shows the source sites discussed here.

```c
/* drivers/thunderbolt/tb.h:12 */
#define TB_CL0S			BIT(0)
#define TB_CL1			BIT(1)
#define TB_CL2			BIT(2)
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
  - 14
  - /* drivers/thunderbolt/tb.c:30 */
-->
