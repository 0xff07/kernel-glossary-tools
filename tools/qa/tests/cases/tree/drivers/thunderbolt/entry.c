// SPDX-License-Identifier: GPL-2.0
/*
 * An entry point the fixture defines through a macro invocation.
 */

#include "tb.h"

#define DEFINE_FIXTURE_ENTRY(name) int name(struct tb_port *port)

DEFINE_FIXTURE_ENTRY(fixture_entry)
{
	return port->clx;
}
