/* SPDX-License-Identifier: GPL-2.0 */
/*
 * A handle the kernel declares and never defines: pointers to it travel
 * through helpers that encode and decode them, and no body exists.
 */
struct kg_opaque;

static inline unsigned long kg_opaque_bits(struct kg_opaque *handle)
{
	return (unsigned long)handle & 3;
}
