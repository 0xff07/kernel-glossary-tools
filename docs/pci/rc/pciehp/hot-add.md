# Native PCIe hot-add

> CAUTION: AI-GENERATED CONTENT
>
> STRICTLY DO NOT SUBMIT THIS UPSTREAM UNLESS YOU ARE AN EXPERT INTIMATELY FAMILIAR WITH THIS SUBSYSTEM.

A PCIe slot that supports hot-plug lets a card be added while the system runs, and the kernel then has to power the slot, wait until the card can answer configuration requests, and enumerate and bind it as boot would have. On x86 the pciehp driver does this for a Downstream Port whose Slot Capabilities advertise hot-plug, running as a portdrv service of the port and keeping one [`struct controller`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L91) per port. Its event handling hands an insertion to an enable path that ends in the PCI core's scan, resource assignment and driver binding. This page follows that path from the event that finds a card to the bound driver: the power-on, the waits that guard the first configuration request, the enumeration under two locks, and the trace and log lines the path leaves.

```text
    A hot-add, from the slot event to a bound driver
    ────────────────────────────────────────────────
    time ↓

    slot, link and card         ╎ pciehp IRQ thread           ╎ PCI core                  ╎ driver core
    ────────────────────────────┼─────────────────────────────┼───────────────────────────┼────────────────────────────
    a card arrives: PDC or      ╎                             ╎                           ╎
    DLLSC latched ──────────▶   ╎ state OFF ─▶ POWERON,       ╎                           ╎
                                ╎ reset_lock held (read)      ╎                           ╎
    slot powered ◀────────────  ╎ Power Controller: on        ╎                           ╎
    indicator blinks ◀────────  ╎ Power Indicator: blink      ╎                           ╎
    link trains, DLLLA 1 ─────▶ ╎ link active, then 100 ms    ╎                           ╎
    PDS 1, if needed ─────────▶ ╎ presence seen               ╎                           ╎
    Vendor ID valid ──────────▶ ╎ a function at devfn 0       ╎                           ╎
                                ╎ rescan lock held ──────────▶╎ functions listed,         ╎
                                ╎                             ╎ bridges numbered,         ╎
                                ╎                             ╎ BARs inside windows       ╎
                                ╎ reset_lock released ─────── ╎ ──────────────────────────▶ drivers bound
                                ╎ reset_lock held again       ╎                           ╎
                                ╎ rescan lock released        ╎                           ╎
    indicator on ◀────────────  ╎ Power Indicator: on         ╎                           ╎
                                ╎ state ON                    ╎                           ╎
```

## SUMMARY

The specification speaks of slots, ports and cards, and pciehp reaches the matching kernel objects through one chain of pointers. The table settles the names the rest of the page uses.

| Specification term | Kernel object | How the hot-add reaches it |
|---|---|---|
| Hot-Plug slot and the Downstream Port that owns it | one [`struct controller`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L91); no separate slot object exists | the argument of the IRQ thread |
| the port as a portdrv service | [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59), portdrv's service instance | [`pcie`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L92) of the controller |
| Downstream Port | the port's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) | [`port`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L61) of that service |
| secondary bus behind the slot | a [`struct pci_bus`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L702) | [`subordinate`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L355) of the port |
| the card's functions | one [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) each, Function 0 at devfn 0 | the [`devices`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L706) list of that bus |
| the slot in sysfs | a [`struct hotplug_slot`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L57) embedded in the controller | [`hotplug_slot`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L113) |

A hot-add runs on the port's IRQ thread with [`reset_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114) held for reading, and [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109) moves from [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) to [`POWERON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L136) before any hardware is touched. [`board_added()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L62) powers the slot and lets [`pciehp_configure_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_pci.c#L32) enumerate only after the link is active, a settle delay has passed and Function 0 answers its Vendor ID read. Within the hot-add, driver binding is the only stage that runs with reset_lock released, and state becomes [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) when the whole path returns 0.

## SPECIFICATIONS

The tree cites the PCI Express Base Specification by revision and section in comments on this path, and one commit message cites the section behind the settle delay. The model of objects above is a kernel synthesis read from drivers/pci/hotplug/pciehp*.[ch] and drivers/pci/, which no specification defines.

- PCIe r4.0, sec 6.6.1, cited without a title by the comment in [`pcie_wait_for_link_delay()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4629) at [`pci.c:4643-4651`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4643) for the 20 ms Detect entry and the minimum 100 ms wait before configuration requests to a device below the port.
- PCIe r4.0, sec 6.7.3.3, cited without a title by the message of commit [6c35a1ac3da6](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=6c35a1ac3da63a7fe5b18b435a5a9d6b9fd3990a) ("PCI: pciehp: Tolerate initially unstable link") for the 100 ms wait at slot enablement.
- PCIe r5.0, appendix I implementation note, cited by the kerneldoc of [`struct controller`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L91) at [`pciehp.h:53-55`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L53) for In-Band Presence Detect Disable.
- PCIe r6.2 sec 7.9.3, cited by the same kerneldoc at [`pciehp.h:49-51`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L49) for the Device Serial Number cached at hot-add.

## COVERAGE

### The enable path (drivers/pci/hotplug/pciehp_ctrl.c, pciehp_pci.c, pciehp.h)

- [`'\<board_added\>':'drivers/pci/hotplug/pciehp_ctrl.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L62): powers the slot, gates on the link and the card, enumerates, and sets the indicators or turns the slot off.
- [`'\<__pciehp_enable_slot\>':'drivers/pci/hotplug/pciehp_ctrl.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L317): refuses an open latch, skips a slot already powered, and calls the bring-up.
- [`'pciehp_enable_slot'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L342): holds a runtime PM reference on the port around the enable and records ON_STATE or OFF_STATE.
- [`'\<set_slot_off\>':'drivers/pci/hotplug/pciehp_ctrl.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L34): the failure exit, which removes power, waits one second and lights the Attention Indicator.
- [`'\<pciehp_configure_device\>':'drivers/pci/hotplug/pciehp_pci.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_pci.c#L32): scans, assigns and binds the devices below the port under the rescan lock.
- [`'\<struct controller\>':'drivers/pci/hotplug/pciehp.h'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L91): the one object pciehp keeps per hotplug port and slot.
- [`'controller.reset_lock'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114): the semaphore a slot reset takes for writing, released by the hot-add around driver binding.
- [`'OFF_STATE'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133): the state of a slot that is powered off with nothing enumerated.
- [`'BLINKINGON_STATE'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L134): the state of a slot waiting out the five seconds after an Attention Button press.
- [`'POWERON_STATE'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L136): the state while the enable path runs.
- [`'ON_STATE'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138): the state of a slot that is powered and enumerated.
- [`'ATTN_BUTTN'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L156), [`'POWER_CTRL'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L157) and [`'MRL_SENS'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L158): tests of the cached Slot Capabilities for an Attention Button, a power controller and an MRL sensor.
- [`'ATTN_LED'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L159) and [`'PWR_LED'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L160): tests of the cached Slot Capabilities for the two indicators.
- [`'INDICATOR_NOOP'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L181): the argument that leaves one indicator as it is.
- [`'\<slot_name\>':'drivers/pci/hotplug/pciehp.h'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L202): the slot's name in messages and trace records.
- [`'ctrl_dbg'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L35), [`'ctrl_info'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L39) and [`'ctrl_err'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L37): the message macros of pciehp, which print through the port's device.

### Slot power and the link gate (drivers/pci/hotplug/pciehp_hpc.c, drivers/pci/pci.c, drivers/pci/pci.h, drivers/pci/probe.c)

- [`'\<pcie_write_cmd\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L213): a Slot Control write that waits for the command to complete.
- [`'\<pcie_write_cmd_nowait\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L219): a Slot Control write that does not wait.
- [`'\<pciehp_power_on_slot\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L534): clears a stale power fault, writes Power Controller Control to on and enables the link.
- [`'\<__pciehp_link_set\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L335): clears or sets Link Disable in the port's Link Control.
- [`'\<pciehp_link_enable\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L346): clears Link Disable so that the link may train.
- [`'\<pciehp_query_power_fault\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L474): reads Power Fault Detected from Slot Status.
- [`'\<pciehp_set_indicators\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L513): writes the Power and Attention Indicator Control fields the slot implements.
- [`'\<pciehp_set_raw_indicator_status\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L483): writes both indicator fields from a user's value, the attention setter of a port whose indicators belong to user space.
- [`'\<pciehp_check_link_status\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L291): the link gate, from the link wait to the training check.
- [`'\<pcie_wait_for_presence\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L277): polls Presence Detect State for up to 1250 ms.
- [`'\<pci_bus_check_dev\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L251): polls the Vendor ID at a devfn for up to 1000 ms.
- [`'\<pcie_wait_for_link\>':'drivers/pci/pci.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4678): waits for the link with a 100 ms settle delay.
- [`'\<pcie_wait_for_link_delay\>':'drivers/pci/pci.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4629): the link wait with a caller's settle delay and the fallback for a port that cannot report DLLLA.
- [`'\<pcie_wait_for_link_status\>':'drivers/pci/pci.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4535): polls one Link Status bit every millisecond up to the retrain timeout.
- [`'PCIE_LINK_RETRAIN_TIMEOUT_MS'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L22): the 1000 ms limit of the link wait.
- [`'\<__pcie_update_link_speed\>':'drivers/pci/pci.h'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L637): records the new link's speed and Flit mode on the bus and fires the link trace event.
- [`'\<pci_bus_generic_read_dev_vendor_id\>':'drivers/pci/probe.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2569): reads the Vendor ID dword and rejects the values that mean no function answered.
- [`'\<pci_bus_rrs_vendor_id\>':'drivers/pci/pci.h'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L289): tests a Vendor ID read for the value of a Configuration RRS completion.
- [`'\<pci_bus_read_dev_vendor_id\>':'drivers/pci/probe.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2586): the exported entry of that read.

### Enumeration and binding (drivers/pci/probe.c, setup-bus.c, bus.c, search.c, pci.c)

- [`'\<pci_lock_rescan_remove\>':'drivers/pci/probe.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L3512): takes the mutex that serializes rescans and removals.
- [`'\<pci_unlock_rescan_remove\>':'drivers/pci/probe.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L3518): releases it.
- [`'\<pci_get_slot\>':'drivers/pci/search.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/search.c#L196): finds the device at a devfn on a bus and takes a reference.
- [`'\<pci_scan_slot\>':'drivers/pci/probe.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2866): scans the functions of one device number and counts the new ones.
- [`'\<pci_hp_add_bridge\>':'drivers/pci/probe.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L3547): gives a hot-added bridge bus numbers and scans behind it.
- [`'\<pci_assign_unassigned_bridge_resources\>':'drivers/pci/setup-bus.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/setup-bus.c#L2261): sizes and assigns the windows and BARs below a bridge in up to two rounds.
- [`'\<pci_hotplug_io_size\>':'drivers/pci/pci.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L110), [`'\<pci_hotplug_mmio_size\>':'drivers/pci/pci.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L116) and [`'\<pci_hotplug_mmio_pref_size\>':'drivers/pci/pci.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L117): the headroom added to a hotplug bridge's windows when they are sized.
- [`'\<pcie_bus_configure_settings\>':'drivers/pci/probe.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L3031): applies the payload policy to a bus and everything below it.
- [`'\<pcie_bus_configure_set\>':'drivers/pci/probe.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L3002): writes one device's Max Payload Size and Max Read Request Size under the policy.
- [`'\<pcie_find_smpss\>':'drivers/pci/probe.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2901): lowers the common payload size to a device's supported maximum.
- [`'\<pcie_bus_config\>':'drivers/pci/pci.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L124): the payload policy, PCIE_BUS_DEFAULT unless a boot parameter sets another.
- [`'\<pci_bus_add_device\>':'drivers/pci/bus.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/bus.c#L345): makes one new device visible and offers it to drivers.
- [`'\<pci_bus_add_devices\>':'drivers/pci/bus.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/bus.c#L385): adds the new devices of a bus and of the buses below it.
- [`'\<pci_get_dsn\>':'drivers/pci/pci.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L555): reads the Device Serial Number capability into one u64.

### Hotplug trace values (include/uapi/linux/pci.h, include/trace/events/pci.h)

- [`'PCI_HOTPLUG_LINK_UP'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci.h#L43): the event value recorded when the link of an empty slot is found up.
- [`'PCI_HOTPLUG_CARD_PRESENT'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci.h#L45): the event value recorded when a card is found present.
- [`'PCI_HOTPLUG_EVENT'`](https://elixir.bootlin.com/linux/v7.2/source/include/trace/events/pci.h#L11): the list that exports the event values to tracing tools and maps them to the strings a trace record prints.

## DOCUMENTATION

- [`Documentation/trace/events-pci.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/trace/events-pci.rst): the pci_hp_event and pcie_link_event tracepoints, their formats and an example of the CARD_PRESENT and LINK_UP records a hot-add produces.
- [`Documentation/admin-guide/kernel-parameters.txt`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/admin-guide/kernel-parameters.txt): the pci= parameters hpiosize, hpmmiosize, hpmmioprefsize, hpmemsize and hpbussize that size the headroom a hotplug bridge gets at boot, and pcie_bus_tune_off, pcie_bus_safe, pcie_bus_perf and pcie_bus_peer2peer that select the payload policy.

## OTHER SOURCES

- [PCI-SIG specifications](https://pcisig.com/specifications): the PCI Express Base and PCI-to-PCI Bridge Architecture specifications referenced above.
- [PCI hotplug bridge resource reservation (LWN)](https://lwn.net/Articles/767885/): background on why hotplug bridge windows are padded at boot so later insertions have room.

### Added by Claude Opus 5.5

- [PCI: pciehp: Fix AB-BA deadlock between reset_lock and device_lock (commit f5eff5591b8f)](https://lore.kernel.org/r/fef2b2e9edf245c049a8c5b94743c0f74ff5008a.1681191902.git.lukas@wunner.de)
- [PCI: pciehp: Wait for PDS if in-band presence is disabled (commit f496648b99f8)](https://lore.kernel.org/r/20191025190047.38130-3-stuart.w.hayes@gmail.com)
- [PCI: pciehp: Fix race condition handling surprise link down (commit 499022396a38)](https://patchwork.kernel.org/patch/9469023)
- [PCI: pciehp: Detect device replacement during system sleep (commit 9d573d19547b)](https://lore.kernel.org/r/a1afaa12f341d146ecbea27c1743661c71683833.1716992815.git.lukas@wunner.de)
- [PCI/PM: Add pcie_wait_for_link_delay() (commit 4827d63891b6)](https://lore.kernel.org/r/20191112091617.70282-2-mika.westerberg@linux.intel.com)
- [PCI: trace: Add generic RAS tracepoint for hotplug event (commit 9e541b3cee70)](https://patch.msgid.link/20251210132907.58799-2-xueshuai@linux.alibaba.com)
- [PCI: trace: Add RAS tracepoint to monitor link speed changes (commit d4318c1a79ac)](https://patch.msgid.link/20251210132907.58799-3-xueshuai@linux.alibaba.com)

## REGISTERS

The hot-add path reads the port's Slot Capabilities through a copy taken at probe, writes two fields and one bit of Slot Control, reads four bits of Slot Status, and reads Link Status to decide that the link is usable. All of them lie in the port's PCI Express capability, which the drawing shows by dword offset from the capability.

```text
    The Slot registers of the port's PCI Express capability on the hot-add path
    ───────────────────────────────────────────────────────────────────────────

    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    cap+14│       PSN (31:19)       │N│    other (17:7)     │H│·│P│A│M│C│B│
          ├─────────────┬─┬─┬─┬───┬─┼─┼─┬─┬─┬─┬─────┬─┬───┬─┴─┼─┴─┴─┴─┴─┴─┤
    cap+18│  reserved   │L│·│D│ · │c│·│f│·│·│I│ oth │W│PIC│AIC│  enables  │
          └─────────────┴─┴─┴─┴───┴─┴─┴─┴─┴─┴─┴─────┴─┴───┴───┴───────────┘

    cap+14, Slot Capabilities = PCI_EXP_SLTCAP (0x14), cached in controller.slot_cap:
      B = PCI_EXP_SLTCAP_ABP (Attention Button Present, ATTN_BUTTN)
      C = PCI_EXP_SLTCAP_PCP (Power Controller Present, POWER_CTRL)
      M = PCI_EXP_SLTCAP_MRLSP (MRL Sensor Present, MRL_SENS)
      A = PCI_EXP_SLTCAP_AIP (Attention Indicator Present, ATTN_LED; masked by hotplug_user_indicators)
      P = PCI_EXP_SLTCAP_PIP (Power Indicator Present, PWR_LED; masked by hotplug_user_indicators)
      H = PCI_EXP_SLTCAP_HPC (Hot-Plug Capable)
      N = PCI_EXP_SLTCAP_NCCS (No Command Completed Support)
      PSN = PCI_EXP_SLTCAP_PSN (Physical Slot Number, the slot name through PSN)
    cap+18, Slot Control = PCI_EXP_SLTCTL (0x18, bits 15:0 of the dword):
      AIC = PCI_EXP_SLTCTL_AIC (Attention Indicator Control: 01 on, 10 blink, 11 off)
      PIC = PCI_EXP_SLTCTL_PIC (Power Indicator Control: 01 on, 10 blink, 11 off)
      W = PCI_EXP_SLTCTL_PCC (Power Controller Control: PCI_EXP_SLTCTL_PWR_ON 0, PCI_EXP_SLTCTL_PWR_OFF 1)
      I = PCI_EXP_SLTCTL_IBPD_DISABLE (In-band PD disable, written at probe)
      enables = the event enables, ABPE to HPIE, which the interrupt setup writes and this path leaves alone
    cap+1a, Slot Status = PCI_EXP_SLTSTA (0x1a, bits 31:16 of the dword; a status bit k sits at dword bit 16 + k):
      f = PCI_EXP_SLTSTA_PFD (Power Fault Detected, bit 1)
      c = PCI_EXP_SLTSTA_PDC (Presence Detect Changed, bit 3)
      D = PCI_EXP_SLTSTA_PDS (Presence Detect State, bit 6)
      L = PCI_EXP_SLTSTA_DLLSC (Data Link Layer State Changed, bit 8)
    · marks a bit the hot-add path neither reads nor writes
```

The capability bits decide which steps exist on a given port. With [`PCI_EXP_SLTCAP_PCP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L599) clear, [`POWER_CTRL`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L157) is false and the hot-add neither powers the slot nor checks whether power is already on. [`PCI_EXP_SLTCAP_AIP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L601) and [`PCI_EXP_SLTCAP_PIP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L602) decide whether [`pciehp_set_indicators()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L513) writes AIC and PIC at all, and [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) clears both in its copy when the port's [`hotplug_user_indicators`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L425) is set. [`PCI_EXP_SLTCAP_MRLSP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L600) lets the enable path refuse a slot whose latch is open. In Slot Control, PCC ([`PCI_EXP_SLTCTL_PCC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L626)) is the power switch, PIC ([`PCI_EXP_SLTCTL_PIC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L622)) blinks while the bring-up runs and turns on at the end, and AIC ([`PCI_EXP_SLTCTL_AIC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L617)) turns off on success and on after a failure. In Slot Status, PDC ([`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637)) and DLLSC ([`PCI_EXP_SLTSTA_DLLSC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L642)) are the events that start the hot-add, PDS ([`PCI_EXP_SLTSTA_PDS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L640)) is the presence the link gate can wait for, and PFD ([`PCI_EXP_SLTSTA_PFD`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L635)) is the fault [`pciehp_power_on_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L534) clears and [`board_added()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L62) checks.

The link gate reads Link Status of the same port, and power-on clears one bit of Link Control.

```text
    The Link registers of the port's PCI Express capability on the hot-add path
    ───────────────────────────────────────────────────────────────────────────

    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    cap+10│B│b│A│·│T│·│    NLW    │  CLS  │    other (15:5)     │D│ other │
          ├─┴─┴─┴─┴─┼─┼───────────┴───────┼─────────────────────┴─┴───────┤
    cap+30│    ·    │F│   other (25:16)   │     Link Control 2 (15:0)     │
          └─────────┴─┴───────────────────┴───────────────────────────────┘

    cap+10, Link Control = PCI_EXP_LNKCTL (0x10, bits 15:0 of the dword):
      D = PCI_EXP_LNKCTL_LD (Link Disable, cleared at power-on)
    cap+12, Link Status = PCI_EXP_LNKSTA (0x12, bits 31:16 of the dword; a status bit k sits at dword bit 16 + k):
      CLS = PCI_EXP_LNKSTA_CLS (Current Link Speed, 3:0, cached in cur_bus_speed of the bus)
      NLW = PCI_EXP_LNKSTA_NLW (Negotiated Link Width, 9:4; zero fails the gate)
      T = PCI_EXP_LNKSTA_LT (Link Training, bit 11; set fails the gate)
      A = PCI_EXP_LNKSTA_DLLLA (Data Link Layer Link Active, bit 13; the link wait polls it)
      b = PCI_EXP_LNKSTA_LBMS, B = PCI_EXP_LNKSTA_LABS (bits 14 and 15, carried into the link trace)
    cap+32, Link Status 2 = PCI_EXP_LNKSTA2 (0x32, bits 31:16 of the dword):
      F = PCI_EXP_LNKSTA2_FLIT (Flit Mode Status, bit 10, cached in flit_mode of the bus)
    · marks a bit the hot-add path neither reads nor writes
```

DLLLA ([`PCI_EXP_LNKSTA_DLLLA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L593)) decides when the link wait ends. LT ([`PCI_EXP_LNKSTA_LT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L591)) set or an NLW ([`PCI_EXP_LNKSTA_NLW`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L585)) of zero after the waits fails the gate with the message that the link cannot train. CLS ([`PCI_EXP_LNKSTA_CLS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L578)) and the Flit Mode Status bit of Link Status 2 ([`PCI_EXP_LNKSTA2_FLIT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L714)) are copied into the bus behind the port by [`__pcie_update_link_speed()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L637), and Link Disable ([`PCI_EXP_LNKCTL_LD`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L569)) is the bit [`pciehp_power_on_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L534) clears so that the link may train.

The card itself is first touched by a read of the dword at offset 0 of Function 0, its Vendor ID ([`PCI_VENDOR_ID`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L38)) and Device ID, and its Device Serial Number capability ([`PCI_EXT_CAP_ID_DSN`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L728)) is read once the card is enumerated.

```text
    The first dword of the new function's configuration header, and the DSN capability
    ──────────────────────────────────────────────────────────────────────────────────

    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    DW0   │       Device ID (31:16)       │       Vendor ID (15:0)        │
          ├───────────────────────┬───────┼───────────────────────────────┤
    dsn+0 │     Next (31:20)      │  Ver  │     Capability ID (15:0)      │
          ├───────────────────────┴───────┴───────────────────────────────┤
    dsn+4 │                Serial Number, low dword (31:0)                │
          ├───────────────────────────────────────────────────────────────┤
    dsn+8 │               Serial Number, high dword (63:32)               │
          └───────────────────────────────────────────────────────────────┘

    Vendor ID = PCI_VENDOR_ID (0x00), read as one dword with Device ID = PCI_DEVICE_ID (0x02)
      all ones, 0, 0x0000ffff and 0xffff0000 mean no function answered
      the reserved Vendor ID PCI_VENDOR_ID_PCI_SIG in 15:0 marks a Configuration RRS completion
    dsn = the offset of the Device Serial Number extended capability, Capability ID PCI_EXT_CAP_ID_DSN
      Capability ID = PCI_EXT_CAP_ID(header), Ver = PCI_EXT_CAP_VER(header), Next = PCI_EXT_CAP_NEXT(header)
      dsn+4 and dsn+8 are read as two dwords and combined into the u64 cached in controller.dsn
```

A valid Vendor ID opens the gate. The read returns all ones, zero or a half-filled value when no function answers, and the reserved RRS value when the function asks to be retried. The serial number is the identity [`pciehp_configure_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_pci.c#L32) caches in [`dsn`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L93), against which a later read decides whether the card in the slot was replaced.

## DETAILS

DETAILS first introduces the controller pciehp keeps for a slot and the state probe leaves it in, then follows the IRQ thread from the event that finds a card to POWERON_STATE and the trace values it records. The bring-up comes next: the checks before power-on, the power and indicator writes, and the link gate with its settle delay, presence wait and Vendor ID probe. Enumeration follows under the rescan lock, with the slot scan, resource assignment inside the port's windows and the payload policy. The last subsections bind drivers with reset_lock released, record ON_STATE or turn the slot off, and list the messages, tracepoints, threads and files that make the path visible.

### Kconfig assumptions

The page documents x86-64 with ACPI, built from the x86-64 default configuration resolved at v7.2 with the PCIe port services, native hotplug and dynamic debug turned on. The table lists the options the prose below relies on, with the value it assumes.

| option | assumed value | what it decides on this page's paths |
|---|---|---|
| [`CONFIG_HOTPLUG_PCI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/Kconfig#L6) | y | builds the hotplug core that registers the slot in sysfs |
| [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5) | y | builds portdrv, which binds pciehp to the port as a service |
| [`CONFIG_HOTPLUG_PCI_PCIE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L16) | y | builds pciehp into the kernel, so its parameters are boot parameters |
| [`CONFIG_PCI_QUIRKS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L62) | y | builds the erratum retrain the link wait tries after a timeout |
| [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) | y | makes the debug messages of the path dynamic-debug sites |
| [`CONFIG_PCI_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L70) | unset | would turn the same debug messages on at build time |

The table indexes the prose and decides nothing by itself: each option is named again, with its effect, where the path depends on it.

### One controller holds the slot's state and locks

A hot-add has to remember what the slot can do, which state it is in, which events are pending, and which locks keep a slot reset away from a bring-up. pciehp keeps all of it in one [`struct controller`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L91) per hotplug port, and its kerneldoc at [`pciehp.h:46-90`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L46) explains why one object serves both, since a PCIe hotplug port and its slot are in a one-to-one relationship. Read the kerneldoc for what each member holds, [`reset_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114) and [`depth`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L115) above all.

```c
/* drivers/pci/hotplug/pciehp.h:46 */
/**
 * struct controller - PCIe hotplug controller
 * @pcie: pointer to the controller's PCIe port service device
 * @dsn: cached copy of Device Serial Number of Function 0 in the hotplug slot
 *	(PCIe r6.2 sec 7.9.3); used to determine whether a hotplugged device
 *	was replaced with a different one during system sleep
 * @slot_cap: cached copy of the Slot Capabilities register
 * @inband_presence_disabled: In-Band Presence Detect Disable supported by
 *	controller and disabled per spec recommendation (PCIe r5.0, appendix I
 *	implementation note)
 * @slot_ctrl: cached copy of the Slot Control register
 * @ctrl_lock: serializes writes to the Slot Control register
 * @cmd_started: jiffies when the Slot Control register was last written;
 *	the next write is allowed 1 second later, absent a Command Completed
 *	interrupt (PCIe r4.0, sec 6.7.3.2)
 * @cmd_busy: flag set on Slot Control register write, cleared by IRQ handler
 *	on reception of a Command Completed event
 * @queue: wait queue to wake up on reception of a Command Completed event,
 *	used for synchronous writes to the Slot Control register
 * @pending_events: used by the IRQ handler to save events retrieved from the
 *	Slot Status register for later consumption by the IRQ thread
 * @notification_enabled: whether the IRQ was requested successfully
 * @power_fault_detected: whether a power fault was detected by the hardware
 *	that has not yet been cleared by the user
 * @poll_thread: thread to poll for slot events if no IRQ is available,
 *	enabled with pciehp_poll_mode module parameter
 * @state: current state machine position
 * @state_lock: protects reads and writes of @state;
 *	protects scheduling, execution and cancellation of @button_work
 * @button_work: work item to turn the slot on or off after 5 seconds
 *	in response to an Attention Button press
 * @hotplug_slot: structure registered with the PCI hotplug core
 * @reset_lock: prevents access to the Data Link Layer Link Active bit in the
 *	Link Status register and to the Presence Detect State bit in the Slot
 *	Status register during a slot reset which may cause them to flap
 * @depth: Number of additional hotplug ports in the path to the root bus,
 *	used as lock subclass for @reset_lock
 * @ist_running: flag to keep user request waiting while IRQ thread is running
 * @request_result: result of last user request submitted to the IRQ thread
 * @requester: wait queue to wake up on completion of user request,
 *	used for synchronous slot enable/disable request via sysfs
 *
 * PCIe hotplug has a 1:1 relationship between controller and slot, hence
 * unlike other drivers, the two aren't represented by separate structures.
 */
```

According to the comment, reset_lock keeps a slot reset from running while code reads DLLLA in Link Status or Presence Detect State in Slot Status, both of which a reset can make flap. It is a reader-writer semaphore, so the readers of those bits run together and a reset waits for all of them. depth counts the hotplug ports between this one and the root bus and serves as the lockdep subclass when nested ports take their reset_lock. The definition below lists the members in the groups its own comments name; read it for the types, since the hot-add path takes reset_lock with the rw-semaphore calls and changes [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104) with atomic operations.

```c
/* drivers/pci/hotplug/pciehp.h:91 */
struct controller {
	struct pcie_device *pcie;
	u64 dsn;

	u32 slot_cap;				/* capabilities and quirks */
	unsigned int inband_presence_disabled:1;

	u16 slot_ctrl;				/* control register access */
	struct mutex ctrl_lock;
	unsigned long cmd_started;
	unsigned int cmd_busy:1;
	wait_queue_head_t queue;

	atomic_t pending_events;		/* event handling */
	unsigned int notification_enabled:1;
	unsigned int power_fault_detected;
	struct task_struct *poll_thread;

	u8 state;				/* state machine */
	struct mutex state_lock;
	struct delayed_work button_work;

	struct hotplug_slot hotplug_slot;	/* hotplug core interface */
	struct rw_semaphore reset_lock;
	unsigned int depth;
	unsigned int ist_running;
	int request_result;
	wait_queue_head_t requester;
};
```

[`pcie`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L92) points at the port's [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59), portdrv's service instance, and through it at the port's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352). The capabilities group, [`dsn`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L93), [`slot_cap`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L95) and [`inband_presence_disabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L96), holds values cached at probe. The control register group, from [`slot_ctrl`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L98) to [`queue`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L102), serializes Slot Control writes and their completion. The event group holds what the interrupt handler latched in pending_events, the fault flag [`power_fault_detected`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L106), and the [`poll_thread`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L107) used when the port has no interrupt.

The state machine group is [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109), the [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110) that guards it, and the [`button_work`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L111) that runs five seconds after an Attention Button press. [`hotplug_slot`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L113) is the slot the hotplug core registers in sysfs. The last group carries reset_lock and depth, and [`ist_running`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L116), [`request_result`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L117) and [`requester`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L118), with which a sysfs request waits for the IRQ thread to finish the work it asked for.

The figure places the controller among the objects a hot-add starts from. The port's portdrv service leads to the port's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352), whose [`subordinate`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L355) bus is where the card's functions will appear.

```text
    One controller per hotplug port, and the bus its slot feeds
    ───────────────────────────────────────────────────────────

    ┌────────────────────────────────────┐
    │ struct controller, one per port    │    ┌──────────────────────────────────────────┐
    │ pcie ──────────────────────────────┼───▶│ struct pcie_device, portdrv's service    │
    │ slot_cap        cached Slot Cap.   │    │ port ──────────────────────────────────┐ │
    │ state           OFF_STATE          │    │ irq   the interrupt the thread serves  │ │
    │ pending_events  latched events     │    └────────────────────────────────────────┼─┘
    │ reset_lock      rw_semaphore       │                                             │
    │ depth           lock subclass      │                                             │
    │ hotplug_slot    the sysfs slot     │                                             ▼
    └────────────────────────────────────┘    ┌──────────────────────────────────────────┐
                                              │ struct pci_dev, the Downstream Port      │
                                              │ hotplug_user_indicators                  │
                                              │ subordinate ───────────────────────────┐ │
                                              └────────────────────────────────────────┼─┘
                                                                                       │
                                                                                       ▼
                                              ┌──────────────────────────────────────────┐
                                              │ struct pci_bus, the bus behind the slot  │
                                              │ devices  empty while the slot is empty   │
                                              └──────────────────────────────────────────┘
```

The expression [`ctrl->pcie->port->subordinate`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L355) is therefore the bus behind the slot, and the functions this page follows start from it. The controller is created by [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) when the portdrv service probes the port; read the lines below for the zeroed allocation, the cached Slot Capabilities with the indicator bits masked for a port whose [`hotplug_user_indicators`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L425) is set, the lock setup, the initial state and the in-band presence decision.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:1006 */
struct controller *pcie_init(struct pcie_device *dev)
{
	struct controller *ctrl;
	u32 slot_cap, slot_cap2;
	u8 poweron;
	struct pci_dev *pdev = dev->port;
	struct pci_bus *subordinate = pdev->subordinate;

	ctrl = kzalloc_obj(*ctrl);
	if (!ctrl)
		return NULL;

	ctrl->pcie = dev;
	ctrl->depth = pcie_hotplug_depth(dev->port);
	pcie_capability_read_dword(pdev, PCI_EXP_SLTCAP, &slot_cap);

	if (pdev->hotplug_user_indicators)
		slot_cap &= ~(PCI_EXP_SLTCAP_AIP | PCI_EXP_SLTCAP_PIP);
	... /* 11 lines, to :1035 */
	init_rwsem(&ctrl->reset_lock);
	init_waitqueue_head(&ctrl->requester);
	init_waitqueue_head(&ctrl->queue);
	INIT_DELAYED_WORK(&ctrl->button_work, pciehp_queue_pushbutton_work);
	dbg_ctrl(ctrl);

	down_read(&pci_bus_sem);
	ctrl->state = list_empty(&subordinate->devices) ? OFF_STATE : ON_STATE;
	up_read(&pci_bus_sem);

	pcie_capability_read_dword(pdev, PCI_EXP_SLTCAP2, &slot_cap2);
	if (slot_cap2 & PCI_EXP_SLTCAP2_IBPD) {
		pcie_write_cmd_nowait(ctrl, PCI_EXP_SLTCTL_IBPD_DISABLE,
				      PCI_EXP_SLTCTL_IBPD_DISABLE);
		ctrl->inband_presence_disabled = 1;
	}

	if (dmi_first_match(inband_presence_disabled_dmi_table))
		ctrl->inband_presence_disabled = 1;
```

pcie_init() starts the controller zeroed, so the members it does not assign begin at 0, pending_events and power_fault_detected among them. state starts as [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) when the [`devices`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L706) list of the bus behind the slot is empty, which is the slot a hot-add finds. A port that sets [`PCI_EXP_SLTCAP2_IBPD`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L717) in Slot Capabilities 2 gets [`PCI_EXP_SLTCTL_IBPD_DISABLE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L632) written to Slot Control, and inband_presence_disabled, set then or by a DMI table match, tells the link gate to wait for Presence Detect State later.

Several functions of the hot-add path write the controller's state, power_fault_detected and the event bits of pending_events, each at its own moment. The strip follows one controller from probe to an enabled slot, with the interval between ③ and ⑥ the one in which a link or presence flap can set the event bits again.

```text
    One controller from probe to an enabled slot, and the fields a hot-add writes
    ─────────────────────────────────────────────────────────────────────────────
    fields: state, power_fault_detected, and the PDC and DLLSC bits of pending_events

    time ────────────────────────────────────────────────────────────────────────────────────────────────────────▶

    event                  probe          IRQ thread     POWERON        power on       link gate      enabled
                           ▼              ▼              ▼              ▼              ▼              ▼
                           ┌─────────────────────────────┬────────────────────────────────────────────┬───────────┐
    state                  │ OFF                         │ POWERON                                    │ ON or OFF │
                           └─────────────────────────────┴────────────────────────────────────────────┴───────────┘
                           ┌────────────────────────────────────────────┬─────────────────────────────────────────┐
    power_fault_detected   │ 0; the ISR sets 1 on a fault               │ 0                                       │
                           └────────────────────────────────────────────┴─────────────────────────────────────────┘
                           ┌──────────────┬────────────────────────────────────────────┬──────────────────────────┐
    PDC, DLLSC pending     │ 0, then set  │ 0; a flap may set them again               │ 0                        │
                           └──────────────┴────────────────────────────────────────────┴──────────────────────────┘

                           ① ②            ③              ④              ⑤              ⑥              ⑦

    ① pcie_init                              pciehp_hpc.c:1014  allocates the controller zeroed through kzalloc_obj
    ② pcie_init                              :1042              sets state to OFF_STATE for an empty bus
    ③ pciehp_ist                             :747               takes the latched events and zeroes the word
    ④ pciehp_handle_presence_or_link_change  pciehp_ctrl.c:294  moves state to POWERON_STATE
    ⑤ pciehp_power_on_slot                   pciehp_hpc.c:545   clears power_fault_detected before power-on
    ⑥ pciehp_check_link_status               :310               clears the PDC and DLLSC bits raised so far
    ⑦ pciehp_enable_slot                     pciehp_ctrl.c:355  sets ON_STATE, or OFF_STATE after a failure
```

① [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) allocates the controller zeroed through `kzalloc_obj()`. ② pcie_init() sets state to OFF_STATE because the bus behind the slot is empty. ③ [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728) takes the events the interrupt handler latched and leaves pending_events zero. ④ [`pciehp_handle_presence_or_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L232) moves state to [`POWERON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L136). ⑤ [`pciehp_power_on_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L534) clears power_fault_detected before it issues the power-on command. ⑥ [`pciehp_check_link_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L291) clears the PDC and DLLSC bits the bring-up raised once a device answers. ⑦ [`pciehp_enable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L342) sets [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138), or OFF_STATE when the enable failed.

The strip draws the writes of a hot-add that a card starts in an empty slot. The writers in the table run on other paths of pciehp, and the strip leaves them out for the reason each row gives.

| writer | field and value | why the strip leaves it out |
|---|---|---|
| [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623), [`pciehp_hpc.c:677`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L677) and [`pciehp_hpc.c:724`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L724) | power_fault_detected to true, event bits set with `atomic_or()` | the hard-interrupt handler, whose body this page does not show; the strip draws its effect as the bits that are set when ③ runs |
| [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728), [`pciehp_hpc.c:739`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L739) | clears [`RERUN_ISR`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L154) in pending_events | touches no PDC or DLLSC bit |
| [`pciehp_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L141), [`pciehp_ctrl.c:143`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L143) | event or [`DISABLE_SLOT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L153) bits for sysfs and button requests | a request path, not a card event |
| [`pciehp_ignore_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L596), [`pciehp_hpc.c:606`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L606) | clears ignored link events | runs only for a slot in ON_STATE |
| [`pciehp_handle_presence_or_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L232), [`pciehp_ctrl.c:246`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L246) and [`pciehp_ctrl.c:275`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L275) | POWEROFF_STATE for an occupied slot, OFF_STATE for a vanished card | the removal branch and the empty-slot exit |
| the button and disable paths of pciehp_ctrl.c, [`pciehp_ctrl.c:174`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L174) to [`pciehp_ctrl.c:226`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L226) and [`pciehp_ctrl.c:387`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L387) | the BLINKING, POWEROFF and OFF states | Attention Button and removal paths |
| [`pciehp_release_ctrl()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1096), [`pciehp_hpc.c:1099`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1099) | frees the controller | runs when the port's service is removed |

The controller of an empty slot therefore starts a hot-add in OFF_STATE with no event pending, and the next subsection follows the event that moves it.

### The IRQ thread moves an empty slot to POWERON

A card arriving in a slot sets Presence Detect Changed, Data Link Layer State Changed or both in the port's Slot Status, [`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637) and [`PCI_EXP_SLTSTA_DLLSC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L642). The interrupt handler latches those bits in pending_events and wakes a thread, so that the slow work of a hot-add runs in process context. [`pciehp_request_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L58) installs that thread, or starts a polling thread when the pciehp_poll_mode parameter asks for one; read the lines below for the two ways [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728) comes to run.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:58 */
static inline int pciehp_request_irq(struct controller *ctrl)
{
	int retval, irq = ctrl->pcie->irq;

	if (pciehp_poll_mode) {
		ctrl->poll_thread = kthread_run(&pciehp_poll, ctrl,
						"pciehp_poll-%s",
						slot_name(ctrl));
		return PTR_ERR_OR_ZERO(ctrl->poll_thread);
	}

	/* Installs the interrupt handler */
	retval = request_threaded_irq(irq, pciehp_isr, pciehp_ist,
				      IRQF_SHARED, "pciehp", ctrl);
	if (retval)
```

With interrupts, pciehp_ist() is the thread half of a threaded handler whose hard half is [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623); in poll mode, [`pciehp_poll()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L800) calls both from the kthread named after the slot. In both cases the thread is where the rest of this page runs. pciehp_ist() takes the latched events and dispatches them; read the lines below for the exchange that empties pending_events and for the read hold on reset_lock around the handlers.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:728 */
static irqreturn_t pciehp_ist(int irq, void *dev_id)
{
	struct controller *ctrl = (struct controller *)dev_id;
	struct pci_dev *pdev = ctrl_dev(ctrl);
	irqreturn_t ret;
	u32 events;

	ctrl->ist_running = true;
	pci_config_pm_runtime_get(pdev);

	/* rerun pciehp_isr() if the port was inaccessible on interrupt */
	if (atomic_fetch_and(~RERUN_ISR, &ctrl->pending_events) & RERUN_ISR) {
		ret = pciehp_isr(irq, dev_id);
		enable_irq(irq);
		if (ret != IRQ_WAKE_THREAD)
			goto out;
	}

	synchronize_hardirq(irq);
	events = atomic_xchg(&ctrl->pending_events, 0);
	if (!events) {
		ret = IRQ_NONE;
		goto out;
	}
	... /* 29 lines, to :781 */
	/*
	 * Disable requests have higher priority than Presence Detect Changed
	 * or Data Link Layer State Changed events.
	 */
	down_read_nested(&ctrl->reset_lock, ctrl->depth);
	if (events & DISABLE_SLOT)
		pciehp_handle_disable_request(ctrl);
	else if (events & (PCI_EXP_SLTSTA_PDC | PCI_EXP_SLTSTA_DLLSC))
		pciehp_handle_presence_or_link_change(ctrl, events);
	up_read(&ctrl->reset_lock);
```

The thread first reruns the interrupt handler if the port was inaccessible when the interrupt came, then takes every latched event with `atomic_xchg()`, leaving zero behind. A presence or link event reaches [`pciehp_handle_presence_or_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L232) with reset_lock held for reading, and a [`DISABLE_SLOT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L153) request takes precedence over it. Everything the hot-add does below that call, until the binding stage releases the lock for a while, therefore runs as a reader of reset_lock.

The handler compares the hardware with the slot's state, which takes one of the values the defines below name; read their DOC comment for the meaning of each.

```c
/* drivers/pci/hotplug/pciehp.h:121 */
/**
 * DOC: Slot state
 *
 * @OFF_STATE: slot is powered off, no subordinate devices are enumerated
 * @BLINKINGON_STATE: slot will be powered on after the 5 second delay,
 *	Power Indicator is blinking
 * @BLINKINGOFF_STATE: slot will be powered off after the 5 second delay,
 *	Power Indicator is blinking
 * @POWERON_STATE: slot is currently powering on
 * @POWEROFF_STATE: slot is currently powering off
 * @ON_STATE: slot is powered on, subordinate devices have been enumerated
 */
#define OFF_STATE			0
#define BLINKINGON_STATE		1
#define BLINKINGOFF_STATE		2
#define POWERON_STATE			3
#define POWEROFF_STATE			4
#define ON_STATE			5
```

A hot-add starts from OFF_STATE, or from [`BLINKINGON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L134) when an Attention Button press is waiting out its five seconds. The handler's first half, which brings down an ON_STATE slot whose card changed, does not apply to an empty slot. Its second half reads presence and link state under [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110) and returns when neither shows a card.

```c
/* drivers/pci/hotplug/pciehp_ctrl.c:232 */
void pciehp_handle_presence_or_link_change(struct controller *ctrl, u32 events)
{
	int present, link_active;
	... /* 34 lines, to :269 */
	/* Turn the slot on if it's occupied or link is up */
	mutex_lock(&ctrl->state_lock);
	present = pciehp_card_present(ctrl);
	link_active = pciehp_check_link_active(ctrl);
	if (present <= 0 && link_active <= 0) {
		if (ctrl->state == BLINKINGON_STATE) {
			ctrl->state = OFF_STATE;
			cancel_delayed_work(&ctrl->button_work);
			pciehp_set_indicators(ctrl, PCI_EXP_SLTCTL_PWR_IND_OFF,
					      INDICATOR_NOOP);
			ctrl_info(ctrl, "Slot(%s): Card not present\n",
				  slot_name(ctrl));
			trace_pci_hp_event(pci_name(ctrl->pcie->port),
					   slot_name(ctrl),
					   PCI_HOTPLUG_CARD_NOT_PRESENT);
		}
		mutex_unlock(&ctrl->state_lock);
		return;
	}
```

`present` and `link_active` are locals of pciehp_handle_presence_or_link_change() that hold the two readings, and the test treats a value of zero or below as no card. With neither showing a card, a slot in BLINKINGON_STATE falls back to OFF_STATE with its button work cancelled, and an OFF_STATE slot stays as it is. When either reading shows a card, the same function moves an OFF_STATE or BLINKINGON_STATE slot to POWERON_STATE and starts the enable path, recording a trace value for each reading that is set.

```c
/* drivers/pci/hotplug/pciehp_ctrl.c:232 */
void pciehp_handle_presence_or_link_change(struct controller *ctrl, u32 events)
{
	int present, link_active;
	... /* 54 lines, to :289 */
	switch (ctrl->state) {
	case BLINKINGON_STATE:
		cancel_delayed_work(&ctrl->button_work);
		fallthrough;
	case OFF_STATE:
		ctrl->state = POWERON_STATE;
		mutex_unlock(&ctrl->state_lock);
		if (present) {
			ctrl_info(ctrl, "Slot(%s): Card present\n",
				  slot_name(ctrl));
			trace_pci_hp_event(pci_name(ctrl->pcie->port),
					   slot_name(ctrl),
					   PCI_HOTPLUG_CARD_PRESENT);
		}
		if (link_active) {
			ctrl_info(ctrl, "Slot(%s): Link Up\n", slot_name(ctrl));
			trace_pci_hp_event(pci_name(ctrl->pcie->port),
					   slot_name(ctrl),
					   PCI_HOTPLUG_LINK_UP);
		}
		ctrl->request_result = pciehp_enable_slot(ctrl);
		break;
	default:
		mutex_unlock(&ctrl->state_lock);
		break;
	}
}
```

The state lock is released before the enable starts, so a sysfs reader sees POWERON_STATE for the whole bring-up, and [`request_result`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L117) keeps what [`pciehp_enable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L342) returns for a sysfs request that waits on it. A slot in any other state, POWERON_STATE included, is left alone, which keeps a second event from starting a second enable. The figure gathers the states a hot-add passes through and the conditions that move it between them.

```text
    The slot states a hot-add passes through
    ────────────────────────────────────────

    ┌──────────────────┐  card present or link up,
    │ BLINKINGON_STATE ├───────────────────────────────────┐
    └────────┬─────────┘  button work cancelled            │
             │ nothing present                             │
             │                                             │
             ▼                                             ▼
    ┌──────────────────┐ card present or link up  ┌──────────────────┐ enable returned 0      ┌──────────────────┐
    │ OFF_STATE        ├─────────────────────────▶│ POWERON_STATE    ├───────────────────────▶│ ON_STATE         │
    └──────────────────┘                          └────────┬─────────┘                        └──────────────────┘
             ▲                                             │
             └──────── enable returned an error ───────────┘
```

The slot leaves POWERON_STATE only when the enable path returns, for ON_STATE on success and OFF_STATE on any error. Before power is applied, the handler has recorded which of the two readings found the card, and the next subsection reads those records.

### Two trace values record the card and the link

A hot-add that fails leaves little behind once the slot is off again, so pciehp records the moment it saw the card in the trace buffer. The values it records are the members of [`enum pci_hotplug_event`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci.h#L42), defined in the UAPI header so that tracing tools can decode them; read the definition for the two values a hot-add uses and their removal counterparts.

```c
/* include/uapi/linux/pci.h:41 */

enum pci_hotplug_event {
	PCI_HOTPLUG_LINK_UP,
	PCI_HOTPLUG_LINK_DOWN,
	PCI_HOTPLUG_CARD_PRESENT,
	PCI_HOTPLUG_CARD_NOT_PRESENT,
```

| value | string in the trace record | recorded on a hot-add when |
|---|---|---|
| [`PCI_HOTPLUG_LINK_UP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci.h#L43) | LINK_UP | `link_active` is set as the slot leaves OFF_STATE or BLINKINGON_STATE |
| [`PCI_HOTPLUG_LINK_DOWN`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci.h#L44) | LINK_DOWN | never on a hot-add; a DLLSC event on an ON_STATE or BLINKINGOFF_STATE slot records it |
| [`PCI_HOTPLUG_CARD_PRESENT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci.h#L45) | CARD_PRESENT | `present` is set as the slot leaves OFF_STATE or BLINKINGON_STATE |
| [`PCI_HOTPLUG_CARD_NOT_PRESENT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci.h#L46) | CARD_NOT_PRESENT | never on a hot-add; the removal branch and the empty-slot exit record it |

The trace header lists the same values once more in [`PCI_HOTPLUG_EVENT`](https://elixir.bootlin.com/linux/v7.2/source/include/trace/events/pci.h#L11), a list of `EM()` and `EMe()` entries that the header expands twice. Read the lines below for the first expansion, which exports each value to user space.

```c
/* include/trace/events/pci.h:11 */
#define PCI_HOTPLUG_EVENT						\
	EM(PCI_HOTPLUG_LINK_UP,			"LINK_UP")		\
	EM(PCI_HOTPLUG_LINK_DOWN,		"LINK_DOWN")		\
	EM(PCI_HOTPLUG_CARD_PRESENT,		"CARD_PRESENT")		\
	EMe(PCI_HOTPLUG_CARD_NOT_PRESENT,	"CARD_NOT_PRESENT")

/* Enums require being exported to userspace, for user tool parsing */
#undef EM
#undef EMe
#define EM(a, b)	TRACE_DEFINE_ENUM(a);
#define EMe(a, b)	TRACE_DEFINE_ENUM(a);

PCI_HOTPLUG_EVENT
```

The first expansion turns every entry into `TRACE_DEFINE_ENUM()`, so a tool that reads the event's format finds the numeric values of the enumerators. The second expansion redefines the entries as `{value, "string"}` pairs, and the event [`pci_hp_event`](https://elixir.bootlin.com/linux/v7.2/source/include/trace/events/pci.h#L43) uses that list to print each value by name; read its definition for the three fields a record carries.

```c
/* include/trace/events/pci.h:43 */
TRACE_EVENT(pci_hp_event,

	TP_PROTO(const char *port_name,
		 const char *slot,
		 const int event),

	TP_ARGS(port_name, slot, event),

	TP_STRUCT__entry(
		__string(	port_name,	port_name	)
		__string(	slot,		slot		)
		__field(	int,		event	)
	),

	TP_fast_assign(
		__assign_str(port_name);
		__assign_str(slot);
		__entry->event = event;
	),

	TP_printk("%s slot:%s, event:%s\n",
		__get_str(port_name),
		__get_str(slot),
		__print_symbolic(__entry->event, PCI_HOTPLUG_EVENT)
	)
);
```

A record carries the port's name from `pci_name()`, the slot's name from [`slot_name()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L202) and the event value, and its output prints them as port, slot and event string. The CARD_PRESENT and LINK_UP records of a hot-add therefore name the slot by its sysfs name and the port by its PCI address. Both fire before the slot is powered, so a trace holds them even when the enable path then fails.

### board_added runs the bring-up after two checks

The enable path has to bring an unpowered slot to a configured one, or leave it off with a reason, and it does so in three layers. [`pciehp_enable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L342) holds the port awake around the work and records the result in the slot's state; read it for the runtime PM reference and the state it writes.

```c
/* drivers/pci/hotplug/pciehp_ctrl.c:342 */
static int pciehp_enable_slot(struct controller *ctrl)
{
	int ret;

	pm_runtime_get_sync(&ctrl->pcie->port->dev);
	ret = __pciehp_enable_slot(ctrl);
	if (ret && ATTN_BUTTN(ctrl))
		/* may be blinking */
		pciehp_set_indicators(ctrl, PCI_EXP_SLTCTL_PWR_IND_OFF,
				      INDICATOR_NOOP);
	pm_runtime_put(&ctrl->pcie->port->dev);

	mutex_lock(&ctrl->state_lock);
	ctrl->state = ret ? OFF_STATE : ON_STATE;
	mutex_unlock(&ctrl->state_lock);

	return ret;
}
```

The port stays resumed from `pm_runtime_get_sync()` to `pm_runtime_put()`, so its configuration space answers throughout the bring-up. A failure turns the Power Indicator off on a slot with an Attention Button, whose indicator may still blink from the button press. The state written at the end is ⑦ of the strip, shown here ahead of ⑤ and ⑥ because this wrapper is the caller of everything between them. [`__pciehp_enable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L317) makes the two checks that can stop an enable before power is applied; read it for which capability bits allow each check.

```c
/* drivers/pci/hotplug/pciehp_ctrl.c:317 */
static int __pciehp_enable_slot(struct controller *ctrl)
{
	u8 getstatus = 0;

	if (MRL_SENS(ctrl)) {
		pciehp_get_latch_status(ctrl, &getstatus);
		if (getstatus) {
			ctrl_info(ctrl, "Slot(%s): Latch open\n",
				  slot_name(ctrl));
			return -ENODEV;
		}
	}

	if (POWER_CTRL(ctrl)) {
		pciehp_get_power_status(ctrl, &getstatus);
		if (getstatus) {
			ctrl_info(ctrl, "Slot(%s): Already enabled\n",
				  slot_name(ctrl));
			return 0;
		}
	}

	return board_added(ctrl);
}
```

Each check exists only where the slot implements the hardware it reads, which the capability tests below decide from the cached Slot Capabilities.

```c
/* drivers/pci/hotplug/pciehp.h:156 */
#define ATTN_BUTTN(ctrl)	((ctrl)->slot_cap & PCI_EXP_SLTCAP_ABP)
#define POWER_CTRL(ctrl)	((ctrl)->slot_cap & PCI_EXP_SLTCAP_PCP)
#define MRL_SENS(ctrl)		((ctrl)->slot_cap & PCI_EXP_SLTCAP_MRLSP)
#define ATTN_LED(ctrl)		((ctrl)->slot_cap & PCI_EXP_SLTCAP_AIP)
#define PWR_LED(ctrl)		((ctrl)->slot_cap & PCI_EXP_SLTCAP_PIP)
#define NO_CMD_CMPL(ctrl)	((ctrl)->slot_cap & PCI_EXP_SLTCAP_NCCS)
#define PSN(ctrl)		(((ctrl)->slot_cap & PCI_EXP_SLTCAP_PSN) >> 19)
```

[`MRL_SENS()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L158) is true for a slot with an MRL sensor, and an open latch ends the enable with -ENODEV before anything is written. [`POWER_CTRL()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L157) is true for a slot with a power controller, and power that is already on ends it with 0 and the message that the slot is already enabled. Every other slot reaches [`board_added()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L62), the bring-up itself; read it for the order of its steps and for where each failure leaves.

```c
/* drivers/pci/hotplug/pciehp_ctrl.c:56 */
 * board_added - Called after a board has been added to the system.
 * @ctrl: PCIe hotplug controller where board is added
 *
 * Turns power on for the board.
 * Configures board.
 */
static int board_added(struct controller *ctrl)
{
	int retval = 0;
	struct pci_bus *parent = ctrl->pcie->port->subordinate;

	if (POWER_CTRL(ctrl)) {
		/* Power on slot */
		retval = pciehp_power_on_slot(ctrl);
		if (retval)
			return retval;
	}

	pciehp_set_indicators(ctrl, PCI_EXP_SLTCTL_PWR_IND_BLINK,
			      INDICATOR_NOOP);

	/* Check link training status */
	retval = pciehp_check_link_status(ctrl);
	if (retval)
		goto err_exit;

	/* Check for a power fault */
	if (ctrl->power_fault_detected || pciehp_query_power_fault(ctrl)) {
		ctrl_err(ctrl, "Slot(%s): Power fault\n", slot_name(ctrl));
		retval = -EIO;
		goto err_exit;
	}

	retval = pciehp_configure_device(ctrl);
	if (retval) {
		if (retval != -EEXIST) {
			ctrl_err(ctrl, "Cannot add device at %04x:%02x:00\n",
				 pci_domain_nr(parent), parent->number);
			goto err_exit;
		}
	}

	pciehp_set_indicators(ctrl, PCI_EXP_SLTCTL_PWR_IND_ON,
			      PCI_EXP_SLTCTL_ATTN_IND_OFF);
	return 0;

err_exit:
	set_slot_off(ctrl);
	return retval;
}
```

`parent` is a local of board_added() that holds the bus behind the slot, used only to name the bus in the failure message. Power-on and the blinking Power Indicator come first, and an error from power-on returns at once, without the slot-off exit. The link gate [`pciehp_check_link_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L291) follows, then a power fault test that reads [`power_fault_detected`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L106) as the interrupt handler left it and asks the hardware through [`pciehp_query_power_fault()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L474). Enumeration by [`pciehp_configure_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_pci.c#L32) comes last, and an -EEXIST from it counts as success, because it means the functions were already enumerated.

Every failure after power-on leaves through `err_exit` to [`set_slot_off()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L34), which undoes the power and lights the Attention Indicator; read it for the one-second wait after power-off.

```c
/* drivers/pci/hotplug/pciehp_ctrl.c:34 */
static void set_slot_off(struct controller *ctrl)
{
	/*
	 * Turn off slot, turn on attention indicator, turn off power
	 * indicator
	 */
	if (POWER_CTRL(ctrl)) {
		pciehp_power_off_slot(ctrl);

		/*
		 * After turning power off, we must wait for at least 1 second
		 * before taking any action that relies on power having been
		 * removed from the slot/adapter.
		 */
		msleep(1000);
	}

	pciehp_set_indicators(ctrl, PCI_EXP_SLTCTL_PWR_IND_OFF,
			      PCI_EXP_SLTCTL_ATTN_IND_ON);
}
```

The wait is the one the comment gives, at least one second before anything may rely on the slot's power being gone. On success board_added() instead turns the Power Indicator on and the Attention Indicator off. The figure lays out the decisions of the three layers between POWERON_STATE and a configured slot.

```text
    The decisions between POWERON_STATE and a configured slot
    ─────────────────────────────────────────────────────────

    ┌──────────────────────────────────────┐ yes
    │ MRL sensor present and latch open?   ├──────▶ -ENODEV, the slot is left untouched
    └──────────────────┬───────────────────┘
                       │ no
                       │
    ┌──────────────────▼───────────────────┐ yes
    │ power controller present and slot    ├──────▶ 0, "Already enabled", nothing written
    │ power already on?                    │
    └──────────────────┬───────────────────┘
                       │ no
                       │
    ┌──────────────────▼───────────────────┐ error
    │ power on where a controller exists,  ├──────▶ the error, returned at once
    │ Power Indicator set to blink         │
    └──────────────────┬───────────────────┘
                       │
                       │
    ┌──────────────────▼───────────────────┐ no
    │ link active and settled, and a       ├──────────────────────┐
    │ Vendor ID at devfn 0?                │                      │
    └──────────────────┬───────────────────┘                      │
                       │ yes                                      │
                       │                                          │
    ┌──────────────────▼───────────────────┐ yes                  │
    │ power fault latched or reported?     ├──────────────────────┤
    └──────────────────┬───────────────────┘                      │
                       │ no                                       │
                       │                                          │
    ┌──────────────────▼───────────────────┐ yes                  │
    │ enumeration failed with an error     ├──────────────────────┤
    │ other than -EEXIST?                  │                      │
    └──────────────────┬───────────────────┘                      │
                       │ no                                       ▼
                       │                      ┌────────────────────────────────────────┐
    ┌──────────────────▼───────────────────┐  │ slot off: power off where a            │
    │ Power Indicator on, Attention        │  │ controller exists and wait 1 s,        │
    │ Indicator off, return 0              │  │ Power Indicator off, Attention         │
    └──────────────────────────────────────┘  │ Indicator on, return the error         │
                                              └────────────────────────────────────────┘
```

Only two outcomes leave power on: success and an -EEXIST from enumeration. The bring-up starts with the power and indicator writes, which the next subsection follows into Slot Control.

### Power-on writes Slot Control while the indicator blinks

Slot Control is one register whose fields pciehp changes one group at a time, and a write must not undo a field another write just set. Two wrappers carry every write; read them for the one difference between them.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:213 */
static void pcie_write_cmd(struct controller *ctrl, u16 cmd, u16 mask)
{
	pcie_do_write_cmd(ctrl, cmd, mask, true);
}

/* Same as above without waiting for the hardware to latch */
static void pcie_write_cmd_nowait(struct controller *ctrl, u16 cmd, u16 mask)
{
	pcie_do_write_cmd(ctrl, cmd, mask, false);
}
```

Both pass a command value and a mask of the fields it changes to the common Slot Control write, and [`pcie_write_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L213) waits for the hardware to latch the command while [`pcie_write_cmd_nowait()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L219) does not. [`pciehp_power_on_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L534) uses the waiting form, because the link it enables next needs the power that command switches on; read it for the order of the fault clear, the power command and the link enable.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:534 */
int pciehp_power_on_slot(struct controller *ctrl)
{
	struct pci_dev *pdev = ctrl_dev(ctrl);
	u16 slot_status;
	int retval;

	/* Clear power-fault bit from previous power failures */
	pcie_capability_read_word(pdev, PCI_EXP_SLTSTA, &slot_status);
	if (slot_status & PCI_EXP_SLTSTA_PFD)
		pcie_capability_write_word(pdev, PCI_EXP_SLTSTA,
					   PCI_EXP_SLTSTA_PFD);
	ctrl->power_fault_detected = 0;

	pcie_write_cmd(ctrl, PCI_EXP_SLTCTL_PWR_ON, PCI_EXP_SLTCTL_PCC);
	ctrl_dbg(ctrl, "%s: SLOTCTRL %x write cmd %x\n", __func__,
		 pci_pcie_cap(ctrl->pcie->port) + PCI_EXP_SLTCTL,
		 PCI_EXP_SLTCTL_PWR_ON);

	retval = pciehp_link_enable(ctrl);
	if (retval)
		ctrl_err(ctrl, "%s: Can not enable the link!\n", __func__);

	return retval;
}
```

`slot_status` and `retval` are locals of pciehp_power_on_slot(). A [`PCI_EXP_SLTSTA_PFD`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L635) latched by an earlier failure is written back to clear it, and ⑤ of the strip zeroes the software copy. The command writes [`PCI_EXP_SLTCTL_PWR_ON`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L627) under the mask [`PCI_EXP_SLTCTL_PCC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L626), which clears the one Power Controller Control bit. The link enable that follows is [`pciehp_link_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L346), a wrapper of [`__pciehp_link_set()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L335); read the helper for the bit it changes and the value it returns.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:335 */
static int __pciehp_link_set(struct controller *ctrl, bool enable)
{
	struct pci_dev *pdev = ctrl_dev(ctrl);

	pcie_capability_clear_and_set_word(pdev, PCI_EXP_LNKCTL,
					   PCI_EXP_LNKCTL_LD,
					   enable ? 0 : PCI_EXP_LNKCTL_LD);

	return 0;
}
```

The wrapper asks for the enabled link.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:346 */
static int pciehp_link_enable(struct controller *ctrl)
{
	return __pciehp_link_set(ctrl, true);
}
```

Link Disable, [`PCI_EXP_LNKCTL_LD`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L569), is cleared and the helper returns 0, so the error tests of pciehp_power_on_slot() and of board_added() see 0 from this step. The fault test that board_added() makes after the link gate reads the same Slot Status bit again through [`pciehp_query_power_fault()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L474).

```c
/* drivers/pci/hotplug/pciehp_hpc.c:474 */
int pciehp_query_power_fault(struct controller *ctrl)
{
	struct pci_dev *pdev = ctrl_dev(ctrl);
	u16 slot_status;

	pcie_capability_read_word(pdev, PCI_EXP_SLTSTA, &slot_status);
	return !!(slot_status & PCI_EXP_SLTSTA_PFD);
}
```

A fault the hardware latches while the link comes up therefore stops the bring-up, whether the interrupt handler saw it first or the read finds it. The indicators are written by [`pciehp_set_indicators()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L513), with the encodings and the [`INDICATOR_NOOP`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L181) argument its kerneldoc lists; read it for the capability tests that decide which field is written.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:498 */
/**
 * pciehp_set_indicators() - set attention indicator, power indicator, or both
 * @ctrl: PCIe hotplug controller
 * @pwr: one of:
 *	PCI_EXP_SLTCTL_PWR_IND_ON
 *	PCI_EXP_SLTCTL_PWR_IND_BLINK
 *	PCI_EXP_SLTCTL_PWR_IND_OFF
 * @attn: one of:
 *	PCI_EXP_SLTCTL_ATTN_IND_ON
 *	PCI_EXP_SLTCTL_ATTN_IND_BLINK
 *	PCI_EXP_SLTCTL_ATTN_IND_OFF
 *
 * Either @pwr or @attn can also be INDICATOR_NOOP to leave that indicator
 * unchanged.
 */
void pciehp_set_indicators(struct controller *ctrl, int pwr, int attn)
{
	u16 cmd = 0, mask = 0;

	if (PWR_LED(ctrl) && pwr != INDICATOR_NOOP) {
		cmd |= (pwr & PCI_EXP_SLTCTL_PIC);
		mask |= PCI_EXP_SLTCTL_PIC;
	}

	if (ATTN_LED(ctrl) && attn != INDICATOR_NOOP) {
		cmd |= (attn & PCI_EXP_SLTCTL_AIC);
		mask |= PCI_EXP_SLTCTL_AIC;
	}

	if (cmd) {
		pcie_write_cmd_nowait(ctrl, cmd, mask);
		ctrl_dbg(ctrl, "%s: SLOTCTRL %x write cmd %x\n", __func__,
			 pci_pcie_cap(ctrl->pcie->port) + PCI_EXP_SLTCTL, cmd);
	}
}
```

The indicator definition sits beside the prototype in pciehp.h.

```c
/* drivers/pci/hotplug/pciehp.h:181 */
#define INDICATOR_NOOP -1	/* Leave indicator unchanged */
void pciehp_set_indicators(struct controller *ctrl, int pwr, int attn);
```

[`PWR_LED()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L160) and [`ATTN_LED()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L159) test the cached Slot Capabilities bits [`PCI_EXP_SLTCAP_PIP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L602) and [`PCI_EXP_SLTCAP_AIP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L601), and a field whose indicator is absent or whose argument is INDICATOR_NOOP stays out of both command and mask. The write uses the non-waiting form, and board_added() goes on without waiting for the indicator command to complete. [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) cleared both capability bits in its copy for a port whose [`hotplug_user_indicators`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L425) is set, which turns every indicator write of the hot-add into a no-op on that port. The x86 code sets the bit in [`set_dev_domain_options()`](https://elixir.bootlin.com/linux/v7.2/source/arch/x86/pci/common.c#L637) for a device on a bus that the test below matches.

```c
/* arch/x86/pci/common.c:637 */
static void set_dev_domain_options(struct pci_dev *pdev)
{
	if (is_vmd(pdev->bus))
		pdev->hotplug_user_indicators = 1;
}
```

The setter's caller is [`pcibios_device_add()`](https://elixir.bootlin.com/linux/v7.2/source/arch/x86/pci/common.c#L643) in the same file.

```c
/* arch/x86/pci/common.c:643 */
int pcibios_device_add(struct pci_dev *dev)
{
	struct pci_setup_rom *rom;
	struct irq_domain *msidom;
	struct setup_data *data;
	u64 pa_data;

		... /* 20 lines, to :670 */
		pa_data = data->next;
		memunmap(data);
	}
	set_dev_domain_options(dev);
```

On such a port the indicators belong to user space. [`init_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L51) gives the slot's attention accessors raw versions in place of the usual ones when the port has the bit and no Attention Indicator in its masked capabilities.

```c
/* drivers/pci/hotplug/pciehp_core.c:51 */
static int init_slot(struct controller *ctrl)
{
	struct hotplug_slot_ops *ops;
	char name[SLOT_NAME_SIZE];
	int retval;
	... /* 13 lines, to :69 */
	if (ATTN_LED(ctrl)) {
		ops->get_attention_status = pciehp_get_attention_status;
		ops->set_attention_status = set_attention_status;
	} else if (ctrl->pcie->port->hotplug_user_indicators) {
		ops->get_attention_status = pciehp_get_raw_indicator_status;
		ops->set_attention_status = pciehp_set_raw_indicator_status;
	}
```

The setter installed there, [`pciehp_set_raw_indicator_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L483), writes both indicator fields at once from the value user space gives.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:483 */
int pciehp_set_raw_indicator_status(struct hotplug_slot *hotplug_slot,
				    u8 status)
{
	struct controller *ctrl = to_ctrl(hotplug_slot);
	struct pci_dev *pdev = ctrl_dev(ctrl);

	pci_config_pm_runtime_get(pdev);

	/* Attention and Power Indicator Control bits are supported */
	pcie_write_cmd_nowait(ctrl, FIELD_PREP(PCI_EXP_SLTCTL_AIC | PCI_EXP_SLTCTL_PIC, status),
			      PCI_EXP_SLTCTL_AIC | PCI_EXP_SLTCTL_PIC);
	pci_config_pm_runtime_put(pdev);
	return 0;
}
```

`status` is the parameter that carries the user's value, placed into AIC and PIC by `FIELD_PREP()` under one mask. The figure follows the three Slot Control fields through the steps of board_added() on a port without that bit.

```text
    The Slot Control fields board_added writes, step by step
    ────────────────────────────────────────────────────────
    (▼ marks a write; a cell holds its value until the next write)

    step              before         power on       blink          link gate      configured
                                     ▼              ▼                             ▼
                      ┌──────────────┬───────────────────────────────────────────────────────────┐
    PCC, bit 10       │ 1, off       │ 0, on                                                     │
                      └──────────────┴───────────────────────────────────────────────────────────┘
                      ┌─────────────────────────────┬─────────────────────────────┬──────────────┐
    PIC, bits 9:8     │ as left                     │ 10, blink                   │ 01, on       │
                      └─────────────────────────────┴─────────────────────────────┴──────────────┘
                      ┌───────────────────────────────────────────────────────────┬──────────────┐
    AIC, bits 7:6     │ as left by earlier events                                 │ 11, off      │
                      └───────────────────────────────────────────────────────────┴──────────────┘

    failure exit: PCC 1 (off) and a 1 s wait, PIC 11 (off), AIC 01 (on)
    hotplug_user_indicators set: PIC and AIC receive no write from these steps
```

So far, the slot has left OFF_STATE for POWERON_STATE on the IRQ thread with reset_lock held for reading, the trace holds CARD_PRESENT or LINK_UP, and Slot Control has the slot powered with its Power Indicator blinking. Nothing has yet been sent to the card; that waits for the link gate.

### pciehp_check_link_status admits a trained link with a device

A configuration request sent to a card whose link is still training, or whose function is not ready, fails or stalls, and the enumeration that follows would record an empty slot. [`pciehp_check_link_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L291) is the gate between power-on and that first request, and it opens only when the link is active, the card is present and Function 0 answers. Read it for the order of the three waits and the two checks after them.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:291 */
int pciehp_check_link_status(struct controller *ctrl)
{
	struct pci_dev *pdev = ctrl_dev(ctrl);
	bool found;
	u16 lnk_status, linksta2;

	if (!pcie_wait_for_link(pdev, true)) {
		ctrl_info(ctrl, "Slot(%s): No link\n", slot_name(ctrl));
		return -1;
	}

	if (ctrl->inband_presence_disabled)
		pcie_wait_for_presence(pdev);

	found = pci_bus_check_dev(ctrl->pcie->port->subordinate,
					PCI_DEVFN(0, 0));

	/* ignore link or presence changes up to this point */
	if (found)
		atomic_and(~(PCI_EXP_SLTSTA_DLLSC | PCI_EXP_SLTSTA_PDC),
			   &ctrl->pending_events);

	pcie_capability_read_word(pdev, PCI_EXP_LNKSTA, &lnk_status);
	ctrl_dbg(ctrl, "%s: lnk_status = %x\n", __func__, lnk_status);
	if ((lnk_status & PCI_EXP_LNKSTA_LT) ||
	    !(lnk_status & PCI_EXP_LNKSTA_NLW)) {
		ctrl_info(ctrl, "Slot(%s): Cannot train link: status %#06x\n",
			  slot_name(ctrl), lnk_status);
		return -1;
	}

	pcie_capability_read_word(pdev, PCI_EXP_LNKSTA2, &linksta2);
	__pcie_update_link_speed(ctrl->pcie->port->subordinate, PCIE_HOTPLUG,
				 lnk_status, linksta2);

	if (!found) {
		ctrl_info(ctrl, "Slot(%s): No device found\n",
			  slot_name(ctrl));
		return -1;
	}

	return 0;
}
```

`pdev` is the port's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352), `found` records whether the Vendor ID read succeeded, and `lnk_status` and `linksta2` hold the port's Link Status and Link Status 2. The link wait of [`pcie_wait_for_link()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4678) comes first and includes the settle delay; [`pcie_wait_for_presence()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L277) runs only for a port whose [`inband_presence_disabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L96) is set; and [`pci_bus_check_dev()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L251) probes devfn 0 of the bus behind the slot. Once a device answers, the PDC and DLLSC bits that the link coming up raised in [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104) are dropped, so they do not start a second event after the enable. commit [6c35a1ac3da6](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=6c35a1ac3da63a7fe5b18b435a5a9d6b9fd3990a) ("PCI: pciehp: Tolerate initially unstable link") gives the reason, a Presence Detect and a Link Up event that arrive a few milliseconds apart and may flap for up to 100 ms.

The training check then fails the gate when [`PCI_EXP_LNKSTA_LT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L591) is set or [`PCI_EXP_LNKSTA_NLW`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L585) is zero, and only after it does the absence of a device fail it. The link's speed is recorded on the bus behind the port in between, by the helper below and the reasons it is called with; read it for the two fields it writes and the trace event it fires.

```c
/* drivers/pci/pci.h:629 */
enum pcie_link_change_reason {
	PCIE_LINK_RETRAIN,
	PCIE_ADD_BUS,
	PCIE_BWCTRL_ENABLE,
	PCIE_BWCTRL_IRQ,
	PCIE_HOTPLUG,
};

static inline void __pcie_update_link_speed(struct pci_bus *bus,
					    enum pcie_link_change_reason reason,
					    u16 linksta, u16 linksta2)
{
	bus->cur_bus_speed = pcie_link_speed[linksta & PCI_EXP_LNKSTA_CLS];
	bus->flit_mode = (linksta2 & PCI_EXP_LNKSTA2_FLIT) ? 1 : 0;

	trace_pcie_link_event(bus,
			     reason,
			     FIELD_GET(PCI_EXP_LNKSTA_NLW, linksta),
			     linksta & PCI_EXP_LNKSTA_LINK_STATUS_MASK);
}
```

[`__pcie_update_link_speed()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L637) stores the Current Link Speed in [`cur_bus_speed`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L721) and the Flit Mode Status in [`flit_mode`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L734) of the bus, and fires the pcie_link_event tracepoint with reason [`PCIE_HOTPLUG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L634), the negotiated width and the status bits. A gate that passes the training check therefore leaves one pcie_link_event record with that reason, whether or not a device was found. The figure lays the gate out in time, with the register bits the waits watch above the waits themselves.

```text
    What the link gate waits for before the first configuration request
    ───────────────────────────────────────────────────────────────────
    (traces are register bits of the port and the card; bars are the waits)

    time ────────────────────────────────────────────────────────────────────────────────────────────────────▶

                                        ┌──────────────────────────────────────────────────────────────────────
    DLLLA, Link Status      ────────────┘

                                                                      ┌────────────────────────────────────────
    PDS, Slot Status        ──────────────────────────────────────────┘

                                                                                        ┌──────────────────────
    Vendor ID valid         ────────────────────────────────────────────────────────────┘

    ➊ link wait             ├───────────┼───────────────────┤
                             poll         settle, 100 ms

    ➋ presence wait                                         ├─────────┤
                                                             only without in-band presence

    ➌ Vendor ID polls                                                 ├─────────────────┤
                                                                       devfn 0 on the bus behind the port

    ➍ events dropped                                                                     ●
    ➎ training checked                                                                     ●

    ➊ pciehp_check_link_status pciehp_hpc.c:297 waits for DLLLA and the settle delay after it
    ➋ pciehp_check_link_status :303 waits for Presence Detect State when in-band presence is off
    ➌ pciehp_check_link_status :305 polls the Vendor ID of the function at devfn 0
    ➍ pciehp_check_link_status :310 drops the PDC and DLLSC events the bring-up raised
    ➎ pciehp_check_link_status :315 refuses a link still training or of zero width
```

➊ [`pciehp_check_link_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L291) waits for DLLLA and then for the settle delay. ➋ pciehp_check_link_status() waits for Presence Detect State when in-band presence detection is off. ➌ pciehp_check_link_status() polls the Vendor ID of the function at devfn 0. ➍ pciehp_check_link_status() drops the PDC and DLLSC events the bring-up raised. ➎ pciehp_check_link_status() refuses a link that is still training or has a width of zero.

The gate therefore fails for three reasons, each with its own message: no link, a link that cannot train, and no device. The next two subsections read the waits it is built from.

### The link wait ends with a 100 ms settle delay

A link reports itself active before the device behind it is necessarily ready for configuration requests, and the PCIe Base Specification requires software to wait after the link comes up. The settle delay is that wait, and pciehp gets it from the PCI core's link wait. [`pcie_wait_for_link()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4678) fixes the delay at 100 ms; read it for that constant.

```c
/* drivers/pci/pci.c:4671 */
/**
 * pcie_wait_for_link - Wait until link is active or inactive
 * @pdev: Bridge device
 * @active: waiting for active or inactive?
 *
 * Use this to wait till link becomes active or inactive.
 */
bool pcie_wait_for_link(struct pci_dev *pdev, bool active)
{
	return pcie_wait_for_link_delay(pdev, active, 100);
}
```

The wait itself is [`pcie_wait_for_link_delay()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4629), which also serves a port that cannot report link activity; read it for the 20 ms before the first poll, the retrain after a timeout, and the sleep after success.

```c
/* drivers/pci/pci.c:4621 */
/**
 * pcie_wait_for_link_delay - Wait until link is active or inactive
 * @pdev: Bridge device
 * @active: waiting for active or inactive?
 * @delay: Delay to wait after link has become active (in ms)
 *
 * Use this to wait till link becomes active or inactive.
 */
static bool pcie_wait_for_link_delay(struct pci_dev *pdev, bool active,
				     int delay)
{
	int rc;

	/*
	 * Some controllers might not implement link active reporting. In this
	 * case, we wait for 1000 ms + any delay requested by the caller.
	 */
	if (!pdev->link_active_reporting) {
		msleep(PCIE_LINK_RETRAIN_TIMEOUT_MS + delay);
		return true;
	}

	/*
	 * PCIe r4.0 sec 6.6.1, a component must enter LTSSM Detect within 20ms,
	 * after which we should expect the link to be active if the reset was
	 * successful. If so, software must wait a minimum 100ms before sending
	 * configuration requests to devices downstream this port.
	 *
	 * If the link fails to activate, either the device was physically
	 * removed or the link is permanently failed.
	 */
	if (active)
		msleep(20);
	rc = pcie_wait_for_link_status(pdev, false, active);
	if (active) {
		if (rc)
			rc = pcie_failed_link_retrain(pdev);
		if (rc)
			return false;

		msleep(delay);
		return true;
	}

	if (rc)
		return false;

	return true;
}
```

The port's [`link_active_reporting`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L507) decides between the two shapes in the figure below. A port without it gets one sleep of the retrain timeout plus the delay and is reported up without being read. A port with it sleeps 20 ms, polls DLLLA, and on success sleeps `delay`, the parameter the caller passed, 100 ms here; the comment cites PCIe r4.0 sec 6.6.1 for both waits. The poll uses one Link Status bit chosen by its arguments; read [`pcie_wait_for_link_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4535) for the 1 ms step and the limit.

```c
/* drivers/pci/pci.c:4526 */
/**
 * pcie_wait_for_link_status - Wait for link status change
 * @pdev: Device whose link to wait for.
 * @use_lt: Use the LT bit if TRUE, or the DLLLA bit if FALSE.
 * @active: Waiting for active or inactive?
 *
 * Return 0 if successful, or -ETIMEDOUT if status has not changed within
 * PCIE_LINK_RETRAIN_TIMEOUT_MS milliseconds.
 */
static int pcie_wait_for_link_status(struct pci_dev *pdev,
				     bool use_lt, bool active)
{
	u16 lnksta_mask, lnksta_match;
	unsigned long end_jiffies;
	u16 lnksta;

	lnksta_mask = use_lt ? PCI_EXP_LNKSTA_LT : PCI_EXP_LNKSTA_DLLLA;
	lnksta_match = active ? lnksta_mask : 0;

	end_jiffies = jiffies + msecs_to_jiffies(PCIE_LINK_RETRAIN_TIMEOUT_MS);
	do {
		pcie_capability_read_word(pdev, PCI_EXP_LNKSTA, &lnksta);
		if ((lnksta & lnksta_mask) == lnksta_match)
			return 0;
		msleep(1);
	} while (time_before(jiffies, end_jiffies));

	return -ETIMEDOUT;
}
```

With `use_lt` false the mask is [`PCI_EXP_LNKSTA_DLLLA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L593), and with `active` true the poll ends when that bit is set, after up to [`PCIE_LINK_RETRAIN_TIMEOUT_MS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L22) of 1 ms sleeps. The limit is defined in the PCI core's private header.

```c
/* drivers/pci/pci.h:22 */
#define PCIE_LINK_RETRAIN_TIMEOUT_MS	1000
```

A timeout is not the end of the wait: the link wait gives the erratum retrain of [`pcie_failed_link_retrain()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/quirks.c#L95) one try, which [`CONFIG_PCI_QUIRKS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L62) compiles from drivers/pci/quirks.c. Read its first lines for the ports it applies to.

```c
/* drivers/pci/quirks.c:95 */
int pcie_failed_link_retrain(struct pci_dev *dev)
{
	u16 lnksta, lnkctl2, oldlnkctl2;
	enum pci_bus_speed speed_cap;
	int ret = -ENOTTY;

	if (!pci_is_pcie(dev) || !pcie_downstream_port(dev) ||
	    !pcie_cap_has_lnkctl2(dev) || !dev->link_active_reporting)
		return ret;
```

The retrain returns -ENOTTY at once for a port that is not a PCIe Downstream Port, lacks Link Control 2 or cannot report link activity, and the wait then fails. Without CONFIG_PCI_QUIRKS the definition is a stub in drivers/pci/pci.h that returns -ENOTTY for every port.

```c
/* drivers/pci/pci.h:1069 */
static inline int pcie_failed_link_retrain(struct pci_dev *dev)
{
	return -ENOTTY;
}
```

A port with link activity reporting that times out therefore fails the wait unless the erratum retrain succeeds. The figure places the two shapes of the wait on one time axis.

```text
    pcie_wait_for_link_delay with and without link activity reporting
    ─────────────────────────────────────────────────────────────────
    (schematic: the bars are not to scale)

    time (ms) ──────────────────────────────────────────────────────────────────────────────────────▶
                    0       20                                      ≤ 1020                 + 100
    with            ├───────┼─────────────────────────────────────────────┼─────────────────────┤
    reporting        «2»     «3» DLLLA read every 1 ms                     «5» settle
                             «4» on timeout: erratum retrain, else fail

    without         ├───────────────────────────────────────────────────────────────────────────┤
    reporting        «1» one sleep of PCIE_LINK_RETRAIN_TIMEOUT_MS + 100, then success

    «1» pcie_wait_for_link_delay pci.c:4639 sleeps 1000 ms plus the delay when the port cannot report DLLLA
    «2» pcie_wait_for_link_delay :4653 sleeps 20 ms before the first Link Status read
    «3» pcie_wait_for_link_delay :4654 polls DLLLA through pcie_wait_for_link_status
    «4» pcie_wait_for_link_delay :4657 tries the erratum retrain after a timeout
    «5» pcie_wait_for_link_delay :4661 sleeps the settle delay once DLLLA is set
```

«1» [`pcie_wait_for_link_delay()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4629) sleeps the retrain timeout plus the delay when the port cannot report DLLLA. «2» pcie_wait_for_link_delay() sleeps 20 ms before the first Link Status read. «3» pcie_wait_for_link_delay() polls DLLLA through pcie_wait_for_link_status(). «4» pcie_wait_for_link_delay() tries the erratum retrain after a timeout. «5» pcie_wait_for_link_delay() sleeps the settle delay once DLLLA is set.

The PCI core's wait for the devices behind a bridge, [`pci_bridge_wait_for_secondary_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4724), leaves hot-added devices to this delay, as its comment says.

```c
/* drivers/pci/pci.c:4724 */
int pci_bridge_wait_for_secondary_bus(struct pci_dev *dev, char *reset_type)
{
	struct pci_dev *child __free(pci_dev_put) = NULL;
	int delay;

	if (pci_dev_is_disconnected(dev))
		return 0;

	if (!pci_is_bridge(dev))
		return 0;

	down_read(&pci_bus_sem);

	/*
	 * We only deal with devices that are present currently on the bus.
	 * For any hot-added devices the access delay is handled in pciehp
	 * board_added(). In case of ACPI hotplug the firmware is expected
	 * to configure the devices before OS is notified.
	 */
	if (!dev->subordinate || list_empty(&dev->subordinate->devices)) {
		up_read(&pci_bus_sem);
		return 0;
	}
```

That function returns early for a bridge whose secondary bus has no devices, and its comment leaves hot-added devices to board_added(), so the settle delay a new card gets is the one of pciehp's link wait. commit [4827d63891b6](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=4827d63891b6a839dac49c6ab62e61c4b011c4f2) ("PCI/PM: Add pcie_wait_for_link_delay()") introduced the variable delay that pcie_wait_for_link() now fixes at 100 ms.

### Presence and a Vendor ID answer confirm the card

An active link proves that something trained with the port, and two further polls make sure it is a card that can be enumerated. The first, [`pcie_wait_for_presence()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L277), is for a port whose in-band presence detection pcie_init() disabled, where Presence Detect State comes from the slot's out-of-band signal; read it for the 10 ms step and the 1250 ms limit.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:277 */
static void pcie_wait_for_presence(struct pci_dev *pdev)
{
	int timeout = 1250;
	u16 slot_status;

	do {
		pcie_capability_read_word(pdev, PCI_EXP_SLTSTA, &slot_status);
		if (slot_status & PCI_EXP_SLTSTA_PDS)
			return;
		msleep(10);
		timeout -= 10;
	} while (timeout > 0);
}
```

`timeout` is a local that counts down from 1250 in steps of 10, and the poll returns when [`PCI_EXP_SLTSTA_PDS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L640) is set or the budget is spent. It returns nothing, so a presence that never appears is not a failure here; the Vendor ID probe after it decides. commit [f496648b99f8](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=f496648b99f8f7f6711f7c30a6327381f37dd1e8) ("PCI: pciehp: Wait for PDS if in-band presence is disabled") added the wait. The probe is [`pci_bus_check_dev()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L251); read it for its own polling loop and the debug message it prints after a retry.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:251 */
static bool pci_bus_check_dev(struct pci_bus *bus, int devfn)
{
	u32 l;
	int count = 0;
	int delay = 1000, step = 20;
	bool found = false;

	do {
		found = pci_bus_read_dev_vendor_id(bus, devfn, &l, 0);
		count++;

		if (found)
			break;

		msleep(step);
		delay -= step;
	} while (delay > 0);

	if (count > 1)
		pr_debug("pci %04x:%02x:%02x.%d id reading try %d times with interval %d ms to get %08x\n",
			pci_domain_nr(bus), bus->number, PCI_SLOT(devfn),
			PCI_FUNC(devfn), count, step, l);

	return found;
}
```

`delay`, `step` and `count` are locals: the loop reads the Vendor ID every 20 ms until it gets an answer or 1000 ms have passed, and it counts the reads. The read is [`pci_bus_read_dev_vendor_id()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2586) with a timeout argument of 0, the exported entry of the PCI core's Vendor ID read.

```c
/* drivers/pci/probe.c:2586 */
bool pci_bus_read_dev_vendor_id(struct pci_bus *bus, int devfn, u32 *l,
				int timeout)
{
	return pci_bus_generic_read_dev_vendor_id(bus, devfn, l, timeout);
}
```

It forwards to [`pci_bus_generic_read_dev_vendor_id()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2569), which reads the dword at [`PCI_VENDOR_ID`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L38) and decides what the value means; read it for the values that count as no answer.

```c
/* drivers/pci/probe.c:2569 */
bool pci_bus_generic_read_dev_vendor_id(struct pci_bus *bus, int devfn, u32 *l,
					int timeout)
{
	if (pci_bus_read_config_dword(bus, devfn, PCI_VENDOR_ID, l))
		return false;

	/* Some broken boards return 0 or ~0 (PCI_ERROR_RESPONSE) if a slot is empty: */
	if (PCI_POSSIBLE_ERROR(*l) || *l == 0x00000000 ||
	    *l == 0x0000ffff || *l == 0xffff0000)
		return false;

	if (pci_bus_rrs_vendor_id(*l))
		return pci_bus_wait_rrs(bus, devfn, l, timeout);

	return true;
}
```

All ones, zero and the two half-filled values mean no function answered. A value whose low half is the reserved Vendor ID of a Configuration RRS completion means the function asked to be retried, and [`pci_bus_rrs_vendor_id()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L289) makes that test.

```c
/* drivers/pci/pci.h:289 */
static inline bool pci_bus_rrs_vendor_id(u32 l)
{
	return (l & 0xffff) == PCI_VENDOR_ID_PCI_SIG;
}
```

The read then goes to [`pci_bus_wait_rrs()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2525), which gives up at once when the timeout is 0; read its first lines for that exit.

```c
/* drivers/pci/probe.c:2525 */
static bool pci_bus_wait_rrs(struct pci_bus *bus, int devfn, u32 *l,
			     int timeout)
{
	int delay = 1;

	if (!pci_bus_rrs_vendor_id(*l))
		return true;	/* not a Configuration RRS completion */

	if (!timeout)
		return false;	/* RRS, but caller doesn't want to wait */
```

pci_bus_check_dev() therefore does its own retrying in 20 ms steps and never sleeps inside the PCI core's RRS backoff. commit [2f5d8e4ff947](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=2f5d8e4ff947ad6673397083b48719cd6c59cd61) ("PCI: pciehp: replace unconditional sleep with config space access check") introduced the probe in place of an unconditional sleep. The figure puts the two polls on one time scale.

```text
    The two polls after the link wait, on one time scale
    ────────────────────────────────────────────────────

    time (ms)     0           250         500         750         1000        1250
                  ├───────────┼───────────┼───────────┼───────────┼───────────┤

    PDS poll      ├───────────────────────────────────────────────────────────┤ 125 reads, 10 ms apart

    Vendor ID     ├───────────────────────────────────────────────┤ 50 reads, 20 ms apart

    each poll returns at the first read that finds its bit or a valid ID
```

A card that answers inside these budgets passes the gate, and board_added() moves on to the power fault test and then to enumeration.

### pciehp_configure_device enumerates under the rescan lock

With the gate open, the card has to become kernel objects: a [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) per function on the bus behind the slot, bus numbers and windows for any bridge it brings, resources for its BARs, and a bound driver. [`pciehp_configure_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_pci.c#L32) runs the same steps the PCI core runs at boot, applied to that one bus, and it takes the PCI core's rescan lock so that no rescan or removal changes the tree under it. Its 51 lines are read in three pieces.

| piece | lines | stage |
|---|---|---|
| ❶ | pciehp_pci.c:32-52 | takes the rescan lock and stops when devfn 0 already has a device |
| ❷ | pciehp_pci.c:53-66 | scans the slot, adds the bridges, assigns resources and applies the payload policy |
| ❸ | pciehp_pci.c:67-82 | adds the devices with reset_lock released, caches the serial number and unlocks |

❶ The first piece, with the kerneldoc that states what the return values mean, takes the lock and checks the slot.

```c
/* drivers/pci/hotplug/pciehp_pci.c:24 */
/**
 * pciehp_configure_device() - enumerate PCI devices below a hotplug bridge
 * @ctrl: PCIe hotplug controller
 *
 * Enumerate PCI devices below a hotplug bridge and add them to the system.
 * Return 0 on success, %-EEXIST if the devices are already enumerated or
 * %-ENODEV if enumeration failed.
 */
int pciehp_configure_device(struct controller *ctrl)
{
	struct pci_dev *dev;
	struct pci_dev *bridge = ctrl->pcie->port;
	struct pci_bus *parent = bridge->subordinate;
	int num, ret = 0;

	pci_lock_rescan_remove();

	dev = pci_get_slot(parent, PCI_DEVFN(0, 0));
	if (dev) {
		/*
		 * The device is already there. Either configured by the
		 * boot firmware or a previous hotplug event.
		 */
		ctrl_dbg(ctrl, "Device %s already exists at %04x:%02x:00, skipping hot-add\n",
			 pci_name(dev), pci_domain_nr(parent), parent->number);
		pci_dev_put(dev);
		ret = -EEXIST;
		goto out;
	}
```

`bridge` is a local that holds the port and `parent` one that holds the bus behind it. The lock is the mutex of [`pci_lock_rescan_remove()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L3512) and [`pci_unlock_rescan_remove()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L3518); read their definitions for the rule the comment above the mutex states.

```c
/* drivers/pci/probe.c:3506 */
/*
 * pci_rescan_bus(), pci_rescan_bus_bridge_resize() and PCI device removal
 * routines should always be executed under this mutex.
 */
DEFINE_MUTEX(pci_rescan_remove_lock);

void pci_lock_rescan_remove(void)
{
	mutex_lock(&pci_rescan_remove_lock);
}
EXPORT_SYMBOL_GPL(pci_lock_rescan_remove);

void pci_unlock_rescan_remove(void)
{
	mutex_unlock(&pci_rescan_remove_lock);
}
EXPORT_SYMBOL_GPL(pci_unlock_rescan_remove);
```

Every rescan and every removal of PCI devices takes this one mutex, so the hot-add cannot meet a removal of the same subtree or a sysfs rescan halfway. The check that follows uses [`pci_get_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/search.c#L196), which searches the bus's [`devices`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L706) list for a devfn and takes a reference on what it finds; read it for the lock it searches under.

```c
/* drivers/pci/search.c:182 */
/**
 * pci_get_slot - locate PCI device for a given PCI slot
 * @bus: PCI bus on which desired PCI device resides
 * @devfn: encodes number of PCI slot in which the desired PCI
 * device resides and the logical device number within that slot
 * in case of multi-function devices.
 *
 * Given a PCI bus and slot/function number, the desired PCI device
 * is located in the list of PCI devices.
 * If the device is found, its reference count is increased and this
 * function returns a pointer to its data structure.  The caller must
 * decrement the reference count by calling pci_dev_put().
 * If no device is found, %NULL is returned.
 */
struct pci_dev *pci_get_slot(struct pci_bus *bus, unsigned int devfn)
{
	struct pci_dev *dev;

	down_read(&pci_bus_sem);

	list_for_each_entry(dev, &bus->devices, bus_list) {
		if (dev->devfn == devfn)
			goto out;
	}

	dev = NULL;
 out:
	pci_dev_get(dev);
	up_read(&pci_bus_sem);
	return dev;
}
```

A device already at devfn 0 means boot firmware or an earlier event enumerated the card, and the function returns -EEXIST, which board_added() treats as success. commit [499022396a38](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=499022396a381d1b681105b74ac366017ce051e9) ("PCI: pciehp: Fix race condition handling surprise link down") added this check together with its debug message.

❷ The second piece of [`pciehp_configure_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_pci.c#L32) runs enumeration and resource setup for the bus behind the slot.

```c
/* drivers/pci/hotplug/pciehp_pci.c:53 */

	num = pci_scan_slot(parent, PCI_DEVFN(0, 0));
	if (num == 0) {
		ctrl_err(ctrl, "No new device found\n");
		ret = -ENODEV;
		goto out;
	}

	for_each_pci_bridge(dev, parent)
		pci_hp_add_bridge(dev);

	pci_assign_unassigned_bridge_resources(bridge);
	pcie_bus_configure_settings(parent);

```

`num` is a local counting the new functions [`pci_scan_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2866) found, and zero ends the hot-add with -ENODEV and the message that no new device was found. Each function on the bus that is a bridge goes to [`pci_hp_add_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L3547), whose return value pciehp_configure_device() does not test. [`pci_assign_unassigned_bridge_resources()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/setup-bus.c#L2261) receives the port, and [`pcie_bus_configure_settings()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L3031) the bus behind it; the next three subsections read these four calls.

❸ The third piece of [`pciehp_configure_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_pci.c#L32) makes the devices visible and binds drivers to them, with one lock released for that step.

```c
/* drivers/pci/hotplug/pciehp_pci.c:67 */
	/*
	 * Release reset_lock during driver binding
	 * to avoid AB-BA deadlock with device_lock.
	 */
	up_read(&ctrl->reset_lock);
	pci_bus_add_devices(parent);
	down_read_nested(&ctrl->reset_lock, ctrl->depth);

	dev = pci_get_slot(parent, PCI_DEVFN(0, 0));
	ctrl->dsn = pci_get_dsn(dev);
	pci_dev_put(dev);

 out:
	pci_unlock_rescan_remove();
	return ret;
}
```

[`pci_bus_add_devices()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/bus.c#L385) runs between the release and the retake of [`reset_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114), for the reason a later subsection reads. The serial number of devfn 0 then goes to [`dsn`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L93) through [`pci_get_dsn()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L555), and the rescan lock is released on every exit through `out`. The figure places the stages of the function under the two locks.

```text
    The two locks around the stages of pciehp_configure_device
    ──────────────────────────────────────────────────────────

    time ──────────────────────────────────────────────────────────────────────────────────────────────▶
                       «A»    «B»    «C»    «D»    «E»    «F»    «G»    «H»    «I»    «J»    «K»
                        ▼      ▼      ▼      ▼      ▼      ▼      ▼      ▼      ▼      ▼      ▼
    rescan lock         ├─────────────────────────────────────────────────────────────────────┤

    reset_lock read ──────────────────────────────────────────────┤ free        ├───────────────────────
    (IRQ thread)                                                  ╎             ╎
                                                                  ╎             ╎
    bus behind              devfn   funcs  child  BARs   MPS          drivers        DSN
    the slot                0 free  listed buses  placed              bound          cached

    «A» pciehp_configure_device pciehp_pci.c:39 takes the rescan lock for the whole enumeration
    «B» pciehp_configure_device :41 looks up devfn 0 and stops with -EEXIST when a device is there
    «C» pciehp_configure_device :54 scans devfn 0 and its sibling functions
    «D» pciehp_configure_device :62 numbers and scans a bridge the card brings
    «E» pciehp_configure_device :64 sizes and assigns the windows and BARs below the port
    «F» pciehp_configure_device :65 applies the payload policy to the new bus
    «G» pciehp_configure_device :71 releases reset_lock before binding
    «H» pciehp_configure_device :72 adds the new devices and binds their drivers
    «I» pciehp_configure_device :73 takes reset_lock again for reading
    «J» pciehp_configure_device :76 caches the serial number of devfn 0
    «K» pciehp_configure_device :80 releases the rescan lock
```

«A» [`pciehp_configure_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_pci.c#L32) takes the rescan lock for the whole enumeration. «B» pciehp_configure_device() looks up devfn 0 and stops with -EEXIST when a device is there. «C» pciehp_configure_device() scans devfn 0 and its sibling functions. «D» pciehp_configure_device() numbers and scans each bridge the card brings. «E» pciehp_configure_device() sizes and assigns the windows and BARs below the port. «F» pciehp_configure_device() applies the payload policy to the new bus. «G» pciehp_configure_device() releases reset_lock before binding. «H» pciehp_configure_device() adds the new devices and binds their drivers. «I» pciehp_configure_device() takes reset_lock again for reading. «J» pciehp_configure_device() caches the serial number of devfn 0. «K» pciehp_configure_device() releases the rescan lock.

The rescan lock spans the whole enumeration, while reset_lock, held by the IRQ thread since before board_added(), has one gap around «H».

### The slot scan adds functions and numbers bridges

A PCIe card in a slot is one device, device number 0 behind the Downstream Port, with one or more functions, and the scan has to find each function and create its object. [`pci_scan_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2866) does that for one device number of a bus; read it for the loop over functions and for what it counts.

```c
/* drivers/pci/probe.c:2855 */
/**
 * pci_scan_slot - Scan a PCI slot on a bus for devices
 * @bus: PCI bus to scan
 * @devfn: slot number to scan (must have zero function)
 *
 * Scan a PCI slot on the specified PCI bus for devices, adding
 * discovered devices to the @bus->devices list.  New devices
 * will not have is_added set.
 *
 * Returns the number of new devices found.
 */
int pci_scan_slot(struct pci_bus *bus, int devfn)
{
	struct pci_dev *dev;
	int fn = 0, nr = 0;

	if (only_one_child(bus) && (devfn > 0))
		return 0; /* Already scanned the entire slot */

	do {
		dev = pci_scan_single_device(bus, devfn + fn);
		if (dev) {
			if (!pci_dev_is_added(dev))
				nr++;
			if (fn > 0)
				dev->multifunction = 1;
		} else if (fn == 0) {
			/*
			 * Function 0 is required unless we are running on
			 * a hypervisor that passes through individual PCI
			 * functions.
			 */
			if (!hypervisor_isolated_pci_functions())
				break;
		}
		fn = next_fn(bus, dev, fn);
	} while (fn >= 0);

	/* Only one slot has PCIe device */
	if (bus->self && nr)
		pcie_aspm_init_link_state(bus->self);

	return nr;
}
```

The kerneldoc states the count: functions that are new, which the loop tests with `pci_dev_is_added()` because a function already added would not be. A missing Function 0 ends the loop, unless the hypervisor test the comment describes passes single functions through; the loop otherwise moves to the next function the device can have and marks every function past 0 as part of a multi-function device in [`multifunction`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L462). A scan that found a new function also initializes ASPM for the port's link, a step outside this page. A function with a bridge header then gets its own bus from [`pci_hp_add_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L3547); read it for where the bus number comes from.

```c
/* drivers/pci/probe.c:3547 */
int pci_hp_add_bridge(struct pci_dev *dev)
{
	struct pci_bus *parent = dev->bus;
	int busnr, start = parent->busn_res.start;
	unsigned int available_buses = 0;
	int end = parent->busn_res.end;

	for (busnr = start; busnr <= end; busnr++) {
		if (!pci_find_bus(pci_domain_nr(parent), busnr))
			break;
	}
	if (busnr-- > end) {
		pci_err(dev, "No bus number available for hot-added bridge\n");
		return -1;
	}

	/* Scan bridges that are already configured */
	busnr = pci_scan_bridge(parent, dev, busnr, 0);

	/*
	 * Distribute the available bus numbers between hotplug-capable
	 * bridges to make extending the chain later possible.
	 */
	available_buses = end - busnr;

	/* Scan bridges that need to be reconfigured */
	pci_scan_bridge_extend(parent, dev, busnr, available_buses, 1);

	if (!dev->subordinate)
		return -1;

	return 0;
}
```

`busnr` is a local that the loop advances over the parent's [`busn_res`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L712) range until it finds a number no bus uses, and the scan of an already configured bridge receives the number below it as the highest one in use. The bridge pass that follows passes the rest of the range as the numbers available below the new bridge, which, as the comment says, makes it possible to extend the chain later. No free number in the range ends the call with the message that no bus number is available, and a bridge left without a [`subordinate`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L355) bus returns -1. The figure shows the bus behind the slot before the scan and after it found a bridge at Function 0 and a second function.

```text
    The bus behind the slot before and after the scan, with a bridge at function 0
    ──────────────────────────────────────────────────────────────────────────────

    before                                  after
    ┌────────────────────────────┐          ┌────────────────────────────┐
    │ bus N, behind the slot     │          │ bus N, behind the slot     │
    │ busn_res  N .. M           │  ──▶     │ busn_res  N .. M           │
    │ devices   (empty)          │          │ devices  ────┐             │
    └────────────────────────────┘          └──────────────┼─────────────┘
                                                           │
                                                           ▼
                                            ┌────────────────────────────┐       ┌────────────────────┐
                                            │ N:00.0, function 0         ├──────▶│ N:00.1, function 1 │
                                            │ multifunction 1            │ next  │ devfn 0x01         │
                                            │ subordinate  ────┐         │       └────────────────────┘
                                            └──────────────────┼─────────┘
                                                               │
                                                               ▼
                                            ┌────────────────────────────┐
                                            │ bus K, a child bus         │
                                            │ K: first free in N+1..M    │
                                            └────────────────────────────┘
    devices links functions in scan order; a bridge function gets a child bus
```

The bus behind the slot now lists the card's functions, and each bridge among them has a child bus numbered inside the port's range. None of them has resources yet, which the next call assigns.

So far, the slot is powered with a trained link, the gate has seen Function 0 answer, and under the rescan lock the bus behind the slot lists a [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) per new function with bus numbers given to the bridges among them. reset_lock is still held for reading, and the controller is in POWERON_STATE.

### Resource assignment places BARs inside the port's windows

The new functions' BARs and the windows of any bridge in the card need addresses, and those addresses must lie inside the windows the port already forwards, since the port's own windows lie inside its parent's. [`pci_assign_unassigned_bridge_resources()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/setup-bus.c#L2261) sizes and assigns everything below a bridge; read it for its two rounds and what it does to the port afterwards.

```c
/* drivers/pci/setup-bus.c:2261 */
void pci_assign_unassigned_bridge_resources(struct pci_dev *bridge)
{
	struct pci_bus *parent = bridge->subordinate;
	/* List of resources that want additional resources */
	LIST_HEAD(add_list);
	int tried_times = 0;
	LIST_HEAD(fail_head);
	int ret;

	while (1) {
		__pci_bus_size_bridges(parent, &add_list);

		/*
		 * Distribute remaining resources (if any) equally between
		 * hotplug bridges below. This makes it possible to extend
		 * the hierarchy later without running out of resources.
		 */
		pci_bridge_distribute_available_resources(bridge, &add_list);

		__pci_bridge_assign_resources(bridge, &add_list, &fail_head);
		tried_times++;

		if (list_empty(&fail_head))
			break;

		if (tried_times >= 2) {
			/* Still fail, don't need to try more */
			pci_dev_res_free_list(&fail_head);
			break;
		}

		pci_prepare_next_assign_round(&fail_head, tried_times,
					      whole_subtree);
	}

	ret = pci_reenable_device(bridge);
	if (ret)
		pci_err(bridge, "Error reenabling bridge (%d)\n", ret);
	pci_set_master(bridge);
}
```

`parent` is a local holding the bus behind the port, and `add_list` and `fail_head` are lists of resources that want more space and of resources that failed. Each round sizes the bridges below, spreads any space left in the port's windows across the hotplug bridges below it, and assigns. A round with failures prepares the failed resources and tries again once, and a second failure leaves them unassigned. The port is then re-enabled and set as a bus master, with an error message if the re-enable fails.

The space a new card finds in the port's windows was reserved when those windows were sized. The sizing in [`__pci_bus_size_bridges()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/setup-bus.c#L1388) adds a fixed headroom for a bus whose bridge is a hotplug bridge; read its stage for the test and the three sizes.

```c
/* drivers/pci/setup-bus.c:1388 */
void __pci_bus_size_bridges(struct pci_bus *bus, struct list_head *realloc_head)
{
	struct pci_dev *dev;
	resource_size_t additional_io_size = 0, additional_mmio_size = 0,
			additional_mmio_pref_size = 0;
	struct resource *b_res;
	struct pci_host_bridge *host;
	... /* 30 lines, to :1425 */
	switch (hdr_type) {
	case PCI_HEADER_TYPE_CARDBUS:
		/* Don't size CardBuses yet */
		break;

	case PCI_HEADER_TYPE_BRIDGE:
		pci_bridge_check_ranges(bus);
		if (bus->self->is_hotplug_bridge) {
			additional_io_size  = pci_hotplug_io_size;
			additional_mmio_size = pci_hotplug_mmio_size;
			additional_mmio_pref_size = pci_hotplug_mmio_pref_size;
		}
		fallthrough;
```

`bus->self` is the bridge above the bus being sized, and its [`is_hotplug_bridge`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L483) decides whether the three sizes are passed on as additional sizes for the I/O, memory and prefetchable windows. The same sizing ran when the port's windows were first sized at boot, and it runs again in the first round above for the bus behind the port, whose bridge is the hotplug port itself. How the window sizing turns these additional sizes into a window, and how the reservation is reallocated, is left out here, since neither depends on the hot-add. The three sizes are variables of the PCI core with defaults and the boot parameters the comments name.

```c
/* drivers/pci/pci.c:106 */
#define DEFAULT_HOTPLUG_IO_SIZE		(256)
#define DEFAULT_HOTPLUG_MMIO_SIZE	(2*1024*1024)
#define DEFAULT_HOTPLUG_MMIO_PREF_SIZE	(2*1024*1024)
/* hpiosize=nn can override this */
unsigned long pci_hotplug_io_size  = DEFAULT_HOTPLUG_IO_SIZE;
/*
 * pci=hpmmiosize=nnM overrides non-prefetchable MMIO size,
 * pci=hpmmioprefsize=nnM overrides prefetchable MMIO size;
 * pci=hpmemsize=nnM overrides both
 */
unsigned long pci_hotplug_mmio_size = DEFAULT_HOTPLUG_MMIO_SIZE;
unsigned long pci_hotplug_mmio_pref_size = DEFAULT_HOTPLUG_MMIO_PREF_SIZE;

#define DEFAULT_HOTPLUG_BUS_SIZE	1
unsigned long pci_hotplug_bus_size = DEFAULT_HOTPLUG_BUS_SIZE;
```

[`pci_hotplug_io_size`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L110) defaults to 256 bytes of I/O space, and [`pci_hotplug_mmio_size`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L116) and [`pci_hotplug_mmio_pref_size`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L117) default to 2 MiB each of memory and prefetchable memory. The figure follows one BAR against the port's memory window.

```text
    A new BAR against the port's memory window
    ──────────────────────────────────────────

    address ────────────────────────────────────────────────────────────────────────────────────────────▶

    boot          ├───────────────────────────────────────────────────────┤ the port's MEM window
                   sized for the devices present at boot plus the hotplug headroom

    after         ├───────────────────────────────────────────────────────┤
                    ├───────────────────┤ the new BAR, inside the window

    too large     ├───────────────────────────────────────────────────────┤
                    ├─────────────────────────────────────────────────────────────────────┤
                    fails twice, then stays unassigned
```

A BAR that fits lands inside the window the port already forwards, and one that does not fit in two rounds stays unassigned, so its function is enumerated without the space its driver needs.

### Payload sizes change only when a boot parameter asks

A hot-added card may support a smaller Max Payload Size than its port is set to, and the PCI core can apply a policy that brings the port and the card to a common value. [`pcie_bus_configure_settings()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L3031) applies one of several policies to the port and the new bus; read it for which policy computes a common size and where it writes.

```c
/* drivers/pci/probe.c:3026 */
/*
 * pcie_bus_configure_settings() requires that pci_walk_bus work in a top-down,
 * parents then children fashion.  If this changes, then this code will not
 * work as designed.
 */
void pcie_bus_configure_settings(struct pci_bus *bus)
{
	u8 smpss = 0;

	if (!bus->self)
		return;

	if (!pci_is_pcie(bus->self))
		return;

	/*
	 * FIXME - Peer to peer DMA is possible, though the endpoint would need
	 * to be aware of the MPS of the destination.  To work around this,
	 * simply force the MPS of the entire system to the smallest possible.
	 */
	if (pcie_bus_config == PCIE_BUS_PEER2PEER)
		smpss = 0;

	if (pcie_bus_config == PCIE_BUS_SAFE) {
		smpss = bus->self->pcie_mpss;

		pcie_find_smpss(bus->self, &smpss);
		pci_walk_bus(bus, pcie_find_smpss, &smpss);
	}

	pcie_bus_configure_set(bus->self, &smpss);
	pci_walk_bus(bus, pcie_bus_configure_set, &smpss);
}
```

The policy is [`pcie_bus_config`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L124), a variable whose values the enum below names.

```c
/* include/linux/pci.h:1187 */
enum pcie_bus_config_types {
	PCIE_BUS_TUNE_OFF,	/* Don't touch MPS at all */
	PCIE_BUS_DEFAULT,	/* Ensure MPS matches upstream bridge */
	PCIE_BUS_SAFE,		/* Use largest MPS boot-time devices support */
	PCIE_BUS_PERFORMANCE,	/* Use MPS and MRRS for best performance */
	PCIE_BUS_PEER2PEER,	/* Set MPS = 128 for all devices */
};
```

```c
/* drivers/pci/pci.c:123 */
/* PCIe MPS/MRRS strategy; can be overridden by kernel command-line param */
enum pcie_bus_config_types pcie_bus_config = PCIE_BUS_DEFAULT;
```

The default is [`PCIE_BUS_DEFAULT`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L1189), and the pci= parameter of [`pci_setup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L6743) selects the others; read its lines for the strings it matches.

```c
/* drivers/pci/pci.c:6743 */
static int __init pci_setup(char *str)
{
	while (str) {
		char *k = strchr(str, ',');
		if (k)
			*k++ = 0;
		if (*str && (str = pcibios_setup(str)) && *str) {
				... /* 24 lines, to :6774 */
				pcie_ecrc_get_policy(str + 5);
			} else if (!strncmp(str, "hpiosize=", 9)) {
				pci_hotplug_io_size = memparse(str + 9, &str);
			} else if (!strncmp(str, "hpmmiosize=", 11)) {
				pci_hotplug_mmio_size = memparse(str + 11, &str);
			} else if (!strncmp(str, "hpmmioprefsize=", 15)) {
				pci_hotplug_mmio_pref_size = memparse(str + 15, &str);
			} else if (!strncmp(str, "hpmemsize=", 10)) {
				pci_hotplug_mmio_size = memparse(str + 10, &str);
				pci_hotplug_mmio_pref_size = pci_hotplug_mmio_size;
			} else if (!strncmp(str, "hpbussize=", 10)) {
				pci_hotplug_bus_size =
					simple_strtoul(str + 10, &str, 0);
				if (pci_hotplug_bus_size > 0xff)
					pci_hotplug_bus_size = DEFAULT_HOTPLUG_BUS_SIZE;
			} else if (!strncmp(str, "pcie_bus_tune_off", 17)) {
				pcie_bus_config = PCIE_BUS_TUNE_OFF;
			} else if (!strncmp(str, "pcie_bus_safe", 13)) {
				pcie_bus_config = PCIE_BUS_SAFE;
			} else if (!strncmp(str, "pcie_bus_perf", 13)) {
				pcie_bus_config = PCIE_BUS_PERFORMANCE;
			} else if (!strncmp(str, "pcie_bus_peer2peer", 18)) {
				pcie_bus_config = PCIE_BUS_PEER2PEER;
```

The same lines set the headroom sizes of the previous subsection from hpiosize, hpmmiosize, hpmmioprefsize and hpmemsize. Under [`PCIE_BUS_SAFE`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L1190), [`pcie_find_smpss()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2901) lowers the starting value to the smallest supported size of the port and of every device below it; read it for the case its comment gives for hot-add.

```c
/* drivers/pci/probe.c:2901 */
static int pcie_find_smpss(struct pci_dev *dev, void *data)
{
	u8 *smpss = data;

	if (!pci_is_pcie(dev))
		return 0;

	/*
	 * We don't have a way to change MPS settings on devices that have
	 * drivers attached.  A hot-added device might support only the minimum
	 * MPS setting (MPS=128).  Therefore, if the fabric contains a bridge
	 * where devices may be hot-added, we limit the fabric MPS to 128 so
	 * hot-added devices will work correctly.
	 *
	 * However, if we hot-add a device to a slot directly below a Root
	 * Port, it's impossible for there to be other existing devices below
	 * the port.  We don't limit the MPS in this case because we can
	 * reconfigure MPS on both the Root Port and the hot-added device,
	 * and there are no other devices involved.
	 *
	 * Note that this PCIE_BUS_SAFE path assumes no peer-to-peer DMA.
	 */
	if (dev->is_hotplug_bridge &&
	    pci_pcie_type(dev) != PCI_EXP_TYPE_ROOT_PORT)
		*smpss = 0;

	if (*smpss > dev->pcie_mpss)
		*smpss = dev->pcie_mpss;

	return 0;
}
```

`smpss` points at the value being lowered, in the encoding of the Max Payload Size Supported field. A hotplug bridge that is not a Root Port forces it to 0, 128 bytes; the comment's reason is that a device hot-added below such a bridge may support no more, while devices with drivers bound cannot be changed. A slot directly below a Root Port keeps the smallest supported size of the port and the new card. [`pcie_bus_configure_set()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L3002) then writes that value to the port and to each device below it; read it for the two policies under which it writes nothing.

```c
/* drivers/pci/probe.c:3002 */
static int pcie_bus_configure_set(struct pci_dev *dev, void *data)
{
	int mps, orig_mps;

	if (!pci_is_pcie(dev))
		return 0;

	if (pcie_bus_config == PCIE_BUS_TUNE_OFF ||
	    pcie_bus_config == PCIE_BUS_DEFAULT)
		return 0;

	mps = 128 << *(u8 *)data;
	orig_mps = pcie_get_mps(dev);

	pcie_write_mps(dev, mps);
	pcie_write_mrrs(dev);

	pci_info(dev, "Max Payload Size set to %4d/%4d (was %4d), Max Read Rq %4d\n",
		 pcie_get_mps(dev), 128 << dev->pcie_mpss,
		 orig_mps, pcie_get_readrq(dev));

	return 0;
}
```

Under PCIE_BUS_DEFAULT and [`PCIE_BUS_TUNE_OFF`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L1188) the function returns before any write, so with no pci= payload parameter the hot-add's call writes nothing. [`PCIE_BUS_PEER2PEER`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L1192) starts from 0 and passes 128 bytes to the MPS write for every device. [`PCIE_BUS_PERFORMANCE`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L1191) starts from 0 as well and leaves the value to the MPS write the function calls, which handles that policy itself and is left out here. A write prints the Max Payload Size message from the function's last lines. The figure places the outcomes for one example on the payload scale.

```text
    What the payload call writes for a port and a new device of two sizes
    ─────────────────────────────────────────────────────────────────────
    (an example: a port supporting 2048 bytes and a device supporting 512)

    MPS (bytes)               128       256       512       1024      2048      4096
                              ├─────────┼─────────┼─────────┼─────────┼─────────┤

    supported                                     ┬ new device        ┬ port

    PCIE_BUS_SAFE,                                ● the smaller, written to both
    slot below a Root Port

    PCIE_BUS_SAFE,            ● 128, forced by the hotplug bridge
    below a switch port

    PCIE_BUS_PEER2PEER        ● 128, passed for every device
    DEFAULT, TUNE_OFF         nothing written by this call
```

With the default policy the call leaves every payload setting as it was, and the devices are now ready to be added.

### Binding runs with reset_lock released

Adding a device lets drivers probe it, and a driver probe runs under the device's lock, which the driver core takes. pciehp releases [`reset_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114) for that step; read the lines of [`pciehp_configure_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_pci.c#L32) again for the release and retake around it.

```c
/* drivers/pci/hotplug/pciehp_pci.c:32 */
int pciehp_configure_device(struct controller *ctrl)
{
	struct pci_dev *dev;
	struct pci_dev *bridge = ctrl->pcie->port;
	struct pci_bus *parent = bridge->subordinate;
	int num, ret = 0;
	... /* 29 lines, to :67 */
	/*
	 * Release reset_lock during driver binding
	 * to avoid AB-BA deadlock with device_lock.
	 */
	up_read(&ctrl->reset_lock);
	pci_bus_add_devices(parent);
	down_read_nested(&ctrl->reset_lock, ctrl->depth);
```

The comment names the hazard, an AB-BA deadlock with `device_lock()`, and commit [f5eff5591b8f](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=f5eff5591b8f9c5effd25c92c758a127765f74c1) ("PCI: pciehp: Fix AB-BA deadlock between reset_lock and device_lock") gives the two orders. Driver binding and unbinding take a device's lock while the IRQ thread holds the reset_lock of the hotplug port above it, and a slot reset takes that reset_lock while its caller already holds a device's lock. The reset side is [`pciehp_reset_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L939); read its first lines for the write hold it takes before the bus reset.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:939 */
int pciehp_reset_slot(struct hotplug_slot *hotplug_slot, bool probe)
{
	struct controller *ctrl = to_ctrl(hotplug_slot);
	struct pci_dev *pdev = ctrl_dev(ctrl);
	int rc;

	if (probe)
		return 0;

	down_write_nested(&ctrl->reset_lock, ctrl->depth);
```

The reset holds reset_lock for writing across the Secondary Bus Reset, so it waits for the readers to leave, and readers wait for it. The figure lays the two paths side by side.

```text
    Why binding runs with reset_lock released
    ─────────────────────────────────────────
    time ↓

    hot-add, the IRQ thread               ╎ reset_lock              ╎ reset of a device below the port
    ──────────────────────────────────────┼─────────────────────────┼────────────────────────────────────────
    @1 takes it for reading ─────────▶    ╎ held, reading           ╎
    enumerates the new devices            ╎                         ╎ device_lock held, reset asked
    @2 releases it before binding ───▶    ╎ free                    ╎
    binding takes device_lock             ╎ held, writing ◀───────  ╎ @4 takes it for writing
    of each new device                    ╎                         ╎ bus reset runs, then releases
    @3 takes it again ───────────────▶    ╎ held, reading           ╎ device_lock released

    without @2: the thread holds reset_lock and waits for device_lock,
    while the reset holds device_lock and waits for reset_lock

    @1 pciehp_ist pciehp_hpc.c:785 takes reset_lock for reading before the event handlers
    @2 pciehp_configure_device pciehp_pci.c:71 releases reset_lock before the devices are added
    @3 pciehp_configure_device :73 takes reset_lock for reading again after binding
    @4 pciehp_reset_slot pciehp_hpc.c:948 takes reset_lock for writing around the bus reset
```

@1 [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728) takes reset_lock for reading before the event handlers run. @2 [`pciehp_configure_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_pci.c#L32) releases reset_lock before the devices are added. @3 pciehp_configure_device() takes reset_lock for reading again after binding. @4 [`pciehp_reset_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L939) takes reset_lock for writing around the bus reset, which can now happen in the gap.

The devices are added by [`pci_bus_add_devices()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/bus.c#L385); read it for the order in which it visits the new bus and the buses below.

```c
/* drivers/pci/bus.c:379 */
/**
 * pci_bus_add_devices - start driver for PCI devices
 * @bus: bus to check for new devices
 *
 * Start driver for PCI devices and add some sysfs entries.
 */
void pci_bus_add_devices(const struct pci_bus *bus)
{
	struct pci_dev *dev;
	struct pci_bus *child;

	list_for_each_entry(dev, &bus->devices, bus_list) {
		/* Skip already-added devices */
		if (pci_dev_is_added(dev))
			continue;
		pci_bus_add_device(dev);
	}

	list_for_each_entry(dev, &bus->devices, bus_list) {
		/* Skip if device attach failed */
		if (!pci_dev_is_added(dev))
			continue;
		child = dev->subordinate;
		if (child)
			pci_bus_add_devices(child);
	}
}
```

The first loop adds every device of the bus not yet added, and the second follows the [`subordinate`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L355) bus of each device whose add succeeded. Devices of a bridge's child bus are therefore added after the bridge itself. Each device goes through [`pci_bus_add_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/bus.c#L345); read it for the steps between a device existing and a driver being bound to it.

```c
/* drivers/pci/bus.c:339 */
/**
 * pci_bus_add_device - start driver for a single device
 * @dev: device to add
 *
 * This adds add sysfs entries and start device drivers
 */
void pci_bus_add_device(struct pci_dev *dev)
{
	struct device_node *dn = dev->dev.of_node;

	/*
	 * Can not put in pci_device_add yet because resources
	 * are not assigned yet for some devices.
	 */
	pcibios_bus_add_device(dev);
	pci_fixup_device(pci_fixup_final, dev);
	if (pci_is_bridge(dev))
		of_pci_make_dev_node(dev);
	pci_proc_attach_device(dev);
	pci_bridge_d3_update(dev);

	/* Save config space for error recoverability */
	pci_save_state(dev);

	/*
	 * Enable runtime PM, which potentially allows the device to
	 * suspend immediately, only after the PCI state has been
	 * configured completely.
	 */
	pm_runtime_enable(&dev->dev);

	if (!dn || of_device_is_available(dn))
		pci_dev_allow_binding(dev);

	device_initial_probe(&dev->dev);

	pci_dev_assign_added(dev);
}
```

The device gets its final fixups, a devicetree step for bridges, its /proc/bus/pci entry, its saved configuration space and runtime PM before any driver sees it. Binding is allowed when the device has no devicetree node or an available one, and `device_initial_probe()` hands the device to the driver core, which probes the matching driver, NVMe for a storage card or xHCI for a USB controller. The device is marked added only after that call returns.

The binding stage thus runs outside reset_lock and inside the rescan lock, and a slot reset can complete while a driver of the new card probes. The function then takes reset_lock back and finishes as the next subsection reads.

### The enable path caches the serial number and turns the slot on

After binding, two things remain: remember which card was enumerated, and tell the user and the state machine that the slot is on. The serial number is what identifies the card later. [`pci_get_dsn()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L555) reads it; read its lines for where the two dwords come from.

```c
/* drivers/pci/pci.c:545 */

/**
 * pci_get_dsn - Read and return the 8-byte Device Serial Number
 * @dev: PCI device to query
 *
 * Looks up the PCI_EXT_CAP_ID_DSN and reads the 8 bytes of the Device Serial
 * Number.
 *
 * Returns the DSN, or zero if the capability does not exist.
 */
u64 pci_get_dsn(struct pci_dev *dev)
{
	u32 dword;
	u64 dsn;
	int pos;

	pos = pci_find_ext_capability(dev, PCI_EXT_CAP_ID_DSN);
	if (!pos)
		return 0;

	/*
	 * The Device Serial Number is two dwords offset 4 bytes from the
	 * capability position. The specification says that the first dword is
	 * the lower half, and the second dword is the upper half.
	 */
	pos += 4;
	pci_read_config_dword(dev, pos, &dword);
	dsn = (u64)dword;
	pci_read_config_dword(dev, pos + 4, &dword);
	dsn |= ((u64)dword) << 32;

	return dsn;
}
```

The capability's offset comes from the extended capability list, and the serial number is the two dwords after its header, low half first. A card without the capability yields 0, which the controller caches like any other value. [`pciehp_device_replaced()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L567) compares the cached value with a new read; read its first and last lines.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:567 */
bool pciehp_device_replaced(struct controller *ctrl)
{
	struct pci_dev *pdev __free(pci_dev_put) = NULL;
	... /* 20 lines, to :590 */
	if (pci_get_dsn(pdev) != ctrl->dsn)
		return true;

	return false;
}
```

A changed serial number makes the function report a replaced device. commit [9d573d19547b](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=9d573d19547b3fae0c1d4e5fce52bdad3fda3664) ("PCI: pciehp: Detect device replacement during system sleep") added the cache for that comparison.

Two callers in drivers/pci/hotplug run the comparison, the resume path at [`pciehp_core.c:306`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L306) and the ignored-link-change path at [`pciehp_hpc.c:618`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L618). The figure follows the number from the capability to the comparison.

```text
    Where the cached serial number comes from and what reads it
    ───────────────────────────────────────────────────────────

    function 0 of the card, Device Serial Number capability at pos
    ┌──────────────────────────────────────────┐
    │ pos + 0   extended capability header     │
    │ pos + 4   serial number, low dword       ├────┐
    │ pos + 8   serial number, high dword      ├────┤
    └──────────────────────────────────────────┘    │
                                                    │ one u64; 0 without the capability
                                                    │
                                                    ▼
                                  ┌──────────────────────────────────────┐
                                  │ struct controller   dsn              ├───▶ compared with a new read
                                  └──────────────────────────────────────┘     at resume and after an
                                                                               ignored link change
```

Back in [`board_added()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L62), a return of 0 from enumeration turns the indicators to their final values; read the lines again.

```c
/* drivers/pci/hotplug/pciehp_ctrl.c:62 */
static int board_added(struct controller *ctrl)
{
	int retval = 0;
	... /* 33 lines, to :98 */
	pciehp_set_indicators(ctrl, PCI_EXP_SLTCTL_PWR_IND_ON,
			      PCI_EXP_SLTCTL_ATTN_IND_OFF);
	return 0;
```

The Power Indicator turns on and the Attention Indicator off, through the same capability tests as before. [`pciehp_enable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L342) then records the result in the controller; read the lines again for the write.

```c
/* drivers/pci/hotplug/pciehp_ctrl.c:342 */
static int pciehp_enable_slot(struct controller *ctrl)
{
	int ret;
	... /* 9 lines, to :354 */
	mutex_lock(&ctrl->state_lock);
	ctrl->state = ret ? OFF_STATE : ON_STATE;
	mutex_unlock(&ctrl->state_lock);

	return ret;
}
```

With a return of 0, [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109) becomes ON_STATE under [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110), and [`pciehp_handle_presence_or_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L232) stores the same 0 in [`request_result`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L117) for a sysfs request that waits on it. A non-zero return leaves the slot in OFF_STATE, powered off by [`set_slot_off()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L34) when the failure came after power-on.

So far, a card has been powered, gated, enumerated, given resources and bound, with the indicators showing a working slot, the serial number cached and the controller in ON_STATE. The IRQ thread releases reset_lock as pciehp_ist() returns, and the rest of the page lists what a reader can watch along the way.

### Messages and tracepoints mark each stage of a hot-add

A hot-add prints a line when a check fails and at a few milestones, and it fires two tracepoints, so a log and a trace together show where a failed hot-add stopped. pciehp prints through three macros that pass the port's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) to the PCI core's message macros; read them with the comment above them, which says how to turn the debug lines on.

```c
/* drivers/pci/hotplug/pciehp.h:31 */
/*
 * Set CONFIG_DYNAMIC_DEBUG=y and boot with 'dyndbg="file pciehp* +p"' to
 * enable debug messages.
 */
#define ctrl_dbg(ctrl, format, arg...)					\
	pci_dbg(ctrl->pcie->port, format, ## arg)
#define ctrl_err(ctrl, format, arg...)					\
	pci_err(ctrl->pcie->port, format, ## arg)
#define ctrl_info(ctrl, format, arg...)					\
	pci_info(ctrl->pcie->port, format, ## arg)
#define ctrl_warn(ctrl, format, arg...)					\
	pci_warn(ctrl->pcie->port, format, ## arg)
```

Each message therefore names the port, and the three pciehp files of this path prefix it with "pciehp: " through `dev_fmt()` at [`pciehp_ctrl.c:16`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L16), [`pciehp_pci.c:16`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_pci.c#L16) and [`pciehp_hpc.c:15`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L15). The PCI core macros are thin wrappers of the driver core's.

```c
/* include/linux/pci.h:2888 */
#define pci_emerg(pdev, fmt, arg...)	dev_emerg(&(pdev)->dev, fmt, ##arg)
#define pci_alert(pdev, fmt, arg...)	dev_alert(&(pdev)->dev, fmt, ##arg)
#define pci_crit(pdev, fmt, arg...)	dev_crit(&(pdev)->dev, fmt, ##arg)
#define pci_err(pdev, fmt, arg...)	dev_err(&(pdev)->dev, fmt, ##arg)
#define pci_warn(pdev, fmt, arg...)	dev_warn(&(pdev)->dev, fmt, ##arg)
#define pci_warn_once(pdev, fmt, arg...) dev_warn_once(&(pdev)->dev, fmt, ##arg)
#define pci_notice(pdev, fmt, arg...)	dev_notice(&(pdev)->dev, fmt, ##arg)
#define pci_info(pdev, fmt, arg...)	dev_info(&(pdev)->dev, fmt, ##arg)
#define pci_dbg(pdev, fmt, arg...)	dev_dbg(&(pdev)->dev, fmt, ##arg)
```

[`pci_dbg()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2896) is `dev_dbg()`, so with [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) set each debug line below is a dynamic-debug site that the dyndbg query of the comment, or a write to /sys/kernel/debug/dynamic_debug/control, enables at run time. With [`CONFIG_PCI_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L70), which this page assumes unset, the PCI files are built with `-DDEBUG` and the same lines print without that step. The slot named in the messages comes from [`slot_name()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L202).

```c
/* drivers/pci/hotplug/pciehp.h:202 */
static inline const char *slot_name(struct controller *ctrl)
{
	return hotplug_slot_name(&ctrl->hotplug_slot);
}
```

The table lists the messages a hot-add can print, in the order the path reaches them.

| level | site | message | what it tells the reader |
|---|---|---|---|
| info | [`pciehp_ctrl.c:297`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L297) | Slot(%s): Card present | presence was seen as the slot left OFF_STATE |
| info | [`pciehp_ctrl.c:304`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L304) | Slot(%s): Link Up | DLLLA was seen as the slot left OFF_STATE |
| info | [`pciehp_ctrl.c:324`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L324) | Slot(%s): Latch open | the MRL check refused the enable |
| info | [`pciehp_ctrl.c:333`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L333) | Slot(%s): Already enabled | power was on already, nothing was done |
| debug | [`pciehp_hpc.c:548`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L548) | %s: SLOTCTRL %x write cmd %x | the power-on command and the Slot Control offset |
| error | [`pciehp_hpc.c:554`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L554) | %s: Can not enable the link! | the link enable failed |
| debug | [`pciehp_hpc.c:529`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L529) | %s: SLOTCTRL %x write cmd %x | an indicator command and its value |
| info | [`pciehp_hpc.c:298`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L298) | Slot(%s): No link | DLLLA never came up, retrain included |
| debug | [`pciehp_hpc.c:270`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L270) | pci %04x:%02x:%02x.%d id reading try %d times with interval %d ms to get %08x | the Vendor ID probe needed more than one read, and the last value read |
| debug | [`pciehp_hpc.c:314`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L314) | %s: lnk_status = %x | Link Status after the waits |
| info | [`pciehp_hpc.c:317`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L317) | Slot(%s): Cannot train link: status %#06x | LT set or a zero width, with the status word |
| info | [`pciehp_hpc.c:327`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L327) | Slot(%s): No device found | the link trained but devfn 0 never answered |
| error | [`pciehp_ctrl.c:84`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L84) | Slot(%s): Power fault | a fault stopped the bring-up after the gate |
| debug | [`pciehp_pci.c:47`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_pci.c#L47) | Device %s already exists at %04x:%02x:00, skipping hot-add | devfn 0 was enumerated already |
| error | [`pciehp_pci.c:56`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_pci.c#L56) | No new device found | the slot scan found no new function |
| error | [`probe.c:3559`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L3559) | No bus number available for hot-added bridge | the port's bus range is full |
| error | [`setup-bus.c:2298`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/setup-bus.c#L2298) | Error reenabling bridge (%d) | the port could not be re-enabled after assignment |
| info | [`probe.c:3019`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L3019) | Max Payload Size set to ... | a pci= payload policy other than the default wrote MPS |
| error | [`pciehp_ctrl.c:92`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L92) | Cannot add device at %04x:%02x:00 | enumeration failed and the slot is being turned off |
| info | [`quirks.c:112`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/quirks.c#L112), [`quirks.c:120`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/quirks.c#L120), [`quirks.c:128`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/quirks.c#L128) | broken device, retraining ..., removing 2.5GT/s ..., retraining failed | the erratum retrain ran after a link timeout |

Two tracepoints fire on the path, and the table lists them with the classes that do not.

| class | on a hot-add | site |
|---|---|---|
| pci:pci_hp_event | CARD_PRESENT and LINK_UP as the slot leaves OFF_STATE, before power-on | [`pciehp_ctrl.c:299`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L299), [`pciehp_ctrl.c:305`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L305) |
| pci:pcie_link_event | one record with reason PCIE_HOTPLUG once the gate passes its training check | [`drivers/pci/pci.h:644`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L644) |
| other tracepoints | none: the pci trace system defines these two events in include/trace/events/pci.h, and the AER event of the RAS trace system belongs to error reporting, which this path does not enter | [`include/trace/events/pci.h:43`](https://elixir.bootlin.com/linux/v7.2/source/include/trace/events/pci.h#L43), [`include/trace/events/pci.h:81`](https://elixir.bootlin.com/linux/v7.2/source/include/trace/events/pci.h#L81) |

Both events are described in [`Documentation/trace/events-pci.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/trace/events-pci.rst), with an example of a hot-add's two pci_hp_event records.

### Threads, sysfs files and parameters expose the path

A hot-add crosses from interrupt context to a thread and, for a sysfs request, from a user's write to that thread, and several files and parameters let a reader start it, watch it or change its limits. The sysfs request is the one hand-off this page has not shown. The slot's power file in the hotplug core calls the slot's enable operation on a write of 1; read the lines of [`power_write_file()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L67).

```c
/* drivers/pci/hotplug/pci_hotplug_core.c:67 */
static ssize_t power_write_file(struct pci_slot *pci_slot, const char *buf,
				size_t count)
{
	struct hotplug_slot *slot = pci_slot->hotplug;
	unsigned long lpower;
	u8 power;
	int retval = 0;

	lpower = simple_strtoul(buf, NULL, 10);
	power = (u8)(lpower & 0xff);
	dbg("power = %d\n", power);

	switch (power) {
	case 0:
		if (slot->ops->disable_slot)
			retval = slot->ops->disable_slot(slot);
		break;

	case 1:
		if (slot->ops->enable_slot)
			retval = slot->ops->enable_slot(slot);
		break;

	default:
		err("Illegal value specified for power\n");
		retval = -EINVAL;
	}

	if (retval)
		return retval;
	return count;
}
```

For pciehp the enable operation is [`pciehp_sysfs_enable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L393), which turns the request into a PDC event for the IRQ thread and waits for the thread to finish.

```c
/* drivers/pci/hotplug/pciehp_ctrl.c:393 */
int pciehp_sysfs_enable_slot(struct hotplug_slot *hotplug_slot)
{
	struct controller *ctrl = to_ctrl(hotplug_slot);

	mutex_lock(&ctrl->state_lock);
	switch (ctrl->state) {
	case BLINKINGON_STATE:
	case OFF_STATE:
		mutex_unlock(&ctrl->state_lock);
		/*
		 * The IRQ thread becomes a no-op if the user pulls out the
		 * card before the thread wakes up, so initialize to -ENODEV.
		 */
		ctrl->request_result = -ENODEV;
		pciehp_request(ctrl, PCI_EXP_SLTSTA_PDC);
		wait_event(ctrl->requester,
			   !atomic_read(&ctrl->pending_events) &&
			   !ctrl->ist_running);
		return ctrl->request_result;
```

[`request_result`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L117) starts as -ENODEV so that a card pulled before the thread runs reports failure, and the waiter wakes when no event is pending and the thread is not running. The hot-add itself still runs on the IRQ thread. The table lists the hand-offs a hot-add crosses.

| hand-off | what crosses it | site |
|---|---|---|
| hard interrupt to IRQ thread | the latched Slot Status events | [`pciehp_hpc.c:70`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L70) |
| poll thread, with pciehp_poll_mode | the same events, read every pciehp_poll_time seconds | [`pciehp_hpc.c:63`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L63) |
| sysfs write to IRQ thread | a PDC request and a wait on [`requester`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L118) | [`pciehp_ctrl.c:407`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L407) |
| runtime PM of the port | a synchronous resume before the bring-up and a put after it | [`pciehp_ctrl.c:346`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L346) |
| driver core probe | the new device, through `device_initial_probe()`; the driver core may run the probe asynchronously for a driver that asks for it | [`bus.c:373`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/bus.c#L373) |

The files and parameters are in the next table. No debugfs file, procfs file of pciehp or fault-injection point covers the hot-add path in drivers/pci/hotplug/pciehp*.

| surface | what it does on a hot-add | site |
|---|---|---|
| /sys/bus/pci/slots/N/power | writing 1 requests an enable, reading shows the power state | [`pci_hotplug_core.c:87`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L87) |
| /sys/bus/pci/slots/N/attention | the raw indicator accessors on a port with hotplug_user_indicators | [`pciehp_core.c:72-74`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L72) |
| pciehp.pciehp_poll_mode, pciehp.pciehp_poll_time | poll the slot from a thread instead of an interrupt, and how often | [`pciehp_core.c:41-42`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L41) |
| pci=hpiosize=, hpmmiosize=, hpmmioprefsize=, hpmemsize=, hpbussize= | the headroom a hotplug bridge's windows and bus range get when sized | [`pci.c:6776-6788`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L6776) |
| pci=pcie_bus_tune_off, pcie_bus_safe, pcie_bus_perf, pcie_bus_peer2peer | the payload policy of the hot-add's payload call | [`pci.c:6789-6796`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L6789) |
| dyndbg, /sys/kernel/debug/dynamic_debug/control | turns on the debug lines of the message table | [`pciehp.h:31-34`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L31) |
| /sys/kernel/tracing/events/pci/ | enables pci_hp_event and pcie_link_event | [`Documentation/trace/events-pci.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/trace/events-pci.rst) |

The parameters of pciehp are module parameters, and with [`CONFIG_HOTPLUG_PCI_PCIE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L16) built in they are given on the kernel command line with the pciehp. prefix, as the comment above them says.

```c
/* drivers/pci/hotplug/pciehp_core.c:32 */

/* Global variables */
bool pciehp_poll_mode;
int pciehp_poll_time;

/*
 * not really modular, but the easiest way to keep compat with existing
 * bootargs behaviour is to continue using module_param here.
 */
module_param(pciehp_poll_mode, bool, 0644);
module_param(pciehp_poll_time, int, 0644);
MODULE_PARM_DESC(pciehp_poll_mode, "Using polling mechanism for hot-plug events or not");
MODULE_PARM_DESC(pciehp_poll_time, "Polling mechanism frequency, in seconds");
```

A reader who wants to see a hot-add step by step can therefore enable the two pci tracepoints, turn on the pciehp debug lines, and write 1 to the slot's power file with a card inserted.
