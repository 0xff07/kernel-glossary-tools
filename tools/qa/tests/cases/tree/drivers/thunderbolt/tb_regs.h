/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Register definitions of the fixture router.
 */

#ifndef _TB_REGS
#define _TB_REGS

#include <linux/types.h>

#define TB_CFG_PORT		1

/* The eight dwords at offset zero of an adapter's config space. */
struct tb_regs_port_header {
	/* DWORD 0 */
	u16 vendor_id;
	u16 device_id;
	/* DWORD 1 */
	u32 route_lo;
	u32 route_hi;
	/* DWORD 2 */
	u8 max_counters;
	u8 type;
	u16 reserved;
} __packed;

#define PORT_CS_18		0x12
#define PORT_CS_18_CPS		BIT(10)
#define PORT_CS_19		0x13
#define PORT_CS_19_PC		BIT(3)

#endif
