/* SPDX-License-Identifier: GPL-2.0 */
/*
 * The lanes of a fixture adapter.
 */

#ifndef _LINUX_THUNDERBOLT_H_
#define _LINUX_THUNDERBOLT_H_

#include <linux/bitmap.h>
#include <linux/types.h>

struct tb_lanes;
int tb_lanes_read(struct tb_lanes *lanes);

/**
 * struct tb_lanes - the lanes of an adapter
 * @raw: the lane register as read
 * @width: the negotiated width, the low byte of @raw
 * @up: the lanes that are up
 * @rate: the rate the lanes run at
 */
struct tb_lanes {
	union {
		u32 raw;
		u8 width;
	};
	DECLARE_BITMAP(up, 4);
	struct tb_lane_rate {
		u32 gbps;
	} rate;
};

#endif
