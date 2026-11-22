// SPDX-License-Identifier: GPL-2.0
/*
 * An old consumer of the port API, last touched in 2020.
 */
#include "../thunderbolt/tb.h"

static int old_probe(struct tb_port *port)
{
	return tb_port_enable(port);
}
