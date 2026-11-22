# Hotplug slot registers

> CAUTION: AI-GENERATED CONTENT
>
> STRICTLY DO NOT SUBMIT THIS UPSTREAM UNLESS YOU ARE AN EXPERT INTIMATELY FAMILIAR WITH THIS SUBSYSTEM.

A PCIe port that accepts cards while the system runs describes its slot through a set of slot registers, which say what the slot can do, report what state it is in and carry what software asks of it. The native hotplug driver, pciehp, binds to such a port as one of the port driver's services and reaches the slot through those registers and the port's Link Status. Each action pciehp takes on the slot, from lighting an indicator to switching power, is a write to Slot Control that the port has to finish before the next one begins. This page traces how pciehp caches the slot's capabilities, issues and completes those writes, and reads presence, latch, power fault and link state, up to the files user space sees for the slot.

```text
    A hotplug port's registers and the controller that caches and drives them
    ─────────────────────────────────────────────────────────────────────────

    ┌───────────────────────────────────┐                      ┌───────────────────────────────────────────────────┐
    │ struct controller, one per slot   │                      │ PCIe capability of the hotplug port               │
    ├───────────────────────────────────┤                      ├───────────────────────────────────────────────────┤
    │ ctrl_lock    one writer at a time │                      │ +0x10  Link Control         Link Disable bit      │
    │ queue        the writer's wait    │                      ├───────────────────────────────────────────────────┤
    │ cmd_started  when it was written  │                      │ +0x12  Link Status          link up, width        │
    │                                   │                      ├───────────────────────────────────────────────────┤
    │ slot_cap     the features         │◀──── copied once ────│ +0x14  Slot Capabilities    fixed features        │
    │                                   │                      ├───────────────────────────────────────────────────┤
    │ slot_ctrl    the last command     │───── one command ───▶│ +0x18  Slot Control         enables, LEDs, power  │
    │                                   │      at a time       ├───────────────────────────────────────────────────┤
    │ cmd_busy     command outstanding  │◀─ Command Completed ─│ +0x1a  Slot Status          events, presence      │
    │                                   │   ends the command   ├───────────────────────────────────────────────────┤
    │ inband_presence_disabled          │◀──── set at probe ───│ +0x34  Slot Capabilities 2  in-band PD disable    │
    │ hotplug_slot.ops                  │                      │                                                   │
    └─────────────────┬─────────────────┘                      └─────────────────────────┬─────────────────────────┘
                      ▲ through the slot operations                                      │ read each time, not cached
                      │                                                                  ▼
    ┌───────────────────────────────────┐                      ┌───────────────────────────────────────────────────┐
    │ /sys/bus/pci/slots/<slot>/ files  │                      │ presence, latch, power fault and link state       │
    └───────────────────────────────────┘                      └───────────────────────────────────────────────────┘
```

## SUMMARY

pciehp keeps one [`struct controller`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L91) per hotplug port, and both the specification's Hot-Plug Controller and its slot map onto it, since the comment above the struct states a one-to-one relationship between controller and slot. The table fixes the names the rest of the page uses for the specification's terms.

| Specification term | Kernel representation | Held or reached through |
|---|---|---|
| hotplug port | the port's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) | [`ctrl_dev()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L49), through [`pcie`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L92) and [`port`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L61) |
| Slot Capabilities | [`PCI_EXP_SLTCAP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L597) | [`slot_cap`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L95), copied at probe |
| a command | one write to [`PCI_EXP_SLTCTL`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L610) | [`pcie_do_write_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L157), its value kept in [`slot_ctrl`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L98) |
| Command Completed | [`PCI_EXP_SLTSTA_CC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L638) | [`cmd_busy`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L101), cleared when it arrives |
| a card in the slot | [`PCI_EXP_SLTSTA_PDS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L640) or [`PCI_EXP_LNKSTA_DLLLA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L593) | [`pciehp_card_present_or_link_active()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L463) |
| the slot user space sees | [`struct hotplug_slot`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L57) | its [`ops`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L58), filled by [`init_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L51) |

The primary journey is a command, in which a writer takes [`ctrl_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L99), waits out the previous command, merges its bits into Slot Control and marks the new command outstanding. The governing invariant is that pciehp starts no Slot Control write while [`cmd_busy`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L101) is set, until the timeout counted from [`cmd_started`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L100) runs out, and that a port without Command Completed support skips that wait.

## SPECIFICATIONS

The registers are defined by the PCI Express Base Specification, which the tree cites by revision and section in comments beside the code this page shows. No comment gives a section title, so each entry carries the revision and section its comment gives and names the citing site.

- PCIe r4.0, sec 6.7.3.2, cited by [`pciehp.h:58-60`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L58) for the one-second interval between Slot Control writes when no Command Completed interrupt arrives.
- PCIe r4.0, sec 6.7.3.4, cited by [`pciehp_hpc.c:630-633`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L630) for hotplug interrupts that occur only when Slot Control enables them.
- PCIe Base Spec r5.0 sec 6.7.3.4, cited by [`pciehp_hpc.c:689-694`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L689) for the event bits that must all be zero before a port using MSI sends another interrupt.
- PCIe r5.0, appendix I implementation note, cited by [`pciehp.h:53-55`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L53) for turning in-band presence detection off where the port supports it.
- PCIe Base Spec 3.0, sec 7.8, cited by [`access.c:447-452`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/access.c#L447) for the slot registers of a function without a slot, which read as zero except Presence Detect State.
- PCIe r6.2 sec 7.9.3, cited by [`pciehp.h:49-51`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L49) for the Device Serial Number that the replacement check compares.
- PCIe r4.0 sec 6.6.1, cited by [`pci.c:4644-4647`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4644) for the 20 ms and 100 ms delays of the link wait.

## COVERAGE

### The slot registers and the fields this page reads (include/uapi/linux/pci_regs.h)

- [`'PCI_EXP_SLTCAP'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L597): the offset of Slot Capabilities, read once at probe into the controller.
- [`'PCI_EXP_SLTCTL'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L610): the offset of Slot Control, written only through the command path.
- [`'PCI_EXP_SLTSTA'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L633): the offset of Slot Status, read for state and written to clear events.
- [`'PCI_EXP_SLTCAP2'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L716): the offset of Slot Capabilities 2, read once for In-band PD Disable Supported.
- [`'PCI_EXP_SLTCTL_PCC'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L626): the Power Controller Control bit of Slot Control, 0 for power on and 1 for off.
- [`'PCI_EXP_SLTCTL_PIC'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L622): the two-bit Power Indicator Control field of Slot Control.
- [`'PCI_EXP_SLTCTL_AIC'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L617): the two-bit Attention Indicator Control field of Slot Control.
- [`'PCI_EXP_SLTSTA_PDS'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L640): the Presence Detect State bit of Slot Status.
- [`'PCI_EXP_SLTSTA_DLLSC'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L642): the Data Link Layer State Changed event bit of Slot Status.
- [`'PCI_EXP_SLTSTA_CC'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L638): the Command Completed event bit of Slot Status.

### The controller's register state (drivers/pci/hotplug/pciehp.h)

- [`'controller.slot_cap'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L95): the copy of Slot Capabilities that the feature macros test.
- [`'controller.inband_presence_disabled'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L96): set at probe when in-band presence detection is turned off, read by the link check.
- [`'controller.slot_ctrl'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L98): the value of the last Slot Control command.
- [`'controller.cmd_started'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L100): the jiffies of the last Slot Control write, the start of the completion timeout.
- [`'controller.cmd_busy'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L101): set while a Slot Control command waits for Command Completed.

### The command path (drivers/pci/hotplug/pciehp_hpc.c)

- [`'\<pcie_do_write_cmd\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L157): merges a command into Slot Control under the controller's lock, between waits for completion.
- [`'\<pcie_write_cmd\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L213): issues a command and waits for it to complete.
- [`'\<pcie_write_cmd_nowait\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L219): issues a command and leaves the wait to the next command.
- [`'\<pcie_wait_cmd\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L112): waits for an outstanding command until Command Completed or the timeout.
- [`'\<pcie_poll_cmd\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L86): polls Slot Status for Command Completed and clears it.

### Indicators, power and power faults (drivers/pci/hotplug/pciehp_hpc.c)

- [`'\<pciehp_set_indicators\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L513): sets the Power Indicator, the Attention Indicator or both by one command.
- [`'\<pciehp_get_attention_status\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L365): decodes the Attention Indicator Control field into on, blink or off.
- [`'\<pciehp_set_raw_indicator_status\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L483): writes both indicator fields from one four-bit value.
- [`'\<pciehp_get_raw_indicator_status\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L351): reads both indicator fields as one four-bit value.
- [`'\<pciehp_get_power_status\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L395): decodes the Power Controller Control bit into on or off.
- [`'\<pciehp_power_on_slot\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L534): clears a stale power fault, switches the slot on and re-enables the link.
- [`'\<pciehp_power_off_slot\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L559): switches the slot off and waits for the command.
- [`'\<pciehp_query_power_fault\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L474): reads the Power Fault Detected bit of Slot Status.

### Presence, latch and link (drivers/pci/hotplug/pciehp_hpc.c)

- [`'\<pciehp_get_latch_status\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L417): reads the MRL Sensor State bit of Slot Status.
- [`'\<pciehp_card_present\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L438): reads the Presence Detect State bit of Slot Status.
- [`'\<pciehp_check_link_active\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L235): reads the Data Link Layer Link Active bit of Link Status.
- [`'\<pciehp_card_present_or_link_active\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L463): answers whether the slot is occupied from presence, then from the link.
- [`'\<pciehp_check_link_status\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L291): decides after power on whether the link trained and a device answers.
- [`'\<pciehp_device_replaced\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L567): compares the cached identity of the slot's function 00.0 with what it reports now.

### The slot operations of pciehp (drivers/pci/hotplug/pciehp_core.c)

- [`'set_attention_status'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L102): the operation behind a write to the attention file, through the indicator command.
- [`'get_power_status'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L118): the operation behind a read of the power file.
- [`'get_latch_status'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L129): the operation behind a read of the latch file.
- [`'get_adapter_status'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L140): the operation behind a read of the adapter file.

## DOCUMENTATION

- [`Documentation/PCI/pciebus-howto.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/PCI/pciebus-howto.rst): the port bus driver and its services, of which native hotplug is the one pciehp provides for a port.
- [`Documentation/trace/events-pci.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/trace/events-pci.rst): the [`pcie_link_event`](https://elixir.bootlin.com/linux/v7.2/source/include/trace/events/pci.h#L81) tracepoint and its reason 4 for a hotplug event, which the link check fires.
- [`Documentation/admin-guide/dynamic-debug-howto.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/admin-guide/dynamic-debug-howto.rst): the control file and boot parameter that turn on the [`ctrl_dbg()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L35) sites of pciehp.

## OTHER SOURCES

- [PCI-SIG specifications](https://pcisig.com/specifications): the source of the PCI Express Base Specification sections 7.5.3.9 through 7.5.3.11 that define these three registers.
- [PCI hotplug slot registers (drivers/pci/hotplug/pciehp_hpc.c)](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/tree/drivers/pci/hotplug/pciehp_hpc.c): the controller code that reads SLTCAP and serializes SLTCTL writes against the Command Completed handshake.

### Added by Claude Opus 5.5

- [PCI: pciehp: Add quirk for Command Completed errata (commit d22b36218455)](https://lkml.kernel.org/r/8770820b-85a0-172b-7230-3a44524e6c9f@molgen.mpg.de)
- [PCI: pciehp: Compute timeout from hotplug command start time (commit 40b960831cfa)](http://www.intel.com/content/www/us/en/processors/xeon/xeon-e7-v2-spec-update.html)
- [PCI: pciehp: Disable in-band presence detect when possible (commit 202853595e53)](https://lore.kernel.org/r/20191025190047.38130-2-stuart.w.hayes@gmail.com)
- [PCI: pciehp: Tolerate Presence Detect hardwired to zero (commit 80696f991424)](https://bugzilla.kernel.org/show_bug.cgi?id=200839)
- [PCI: pciehp: Add pciehp_set_indicators() to set both indicators (commit 688033f52d71)](https://lore.kernel.org/r/20190903111021.1559-2-efremov@linux.com)
- [PCI: pciehp: Retain Power Indicator bits for userspace indicators (commit 5560a612c20d)](https://lore.kernel.org/r/20240722141440.7210-1-blazej.kucman@intel.com)
- [PCI: pciehp: Detect device replacement during system sleep (commit 9d573d19547b)](https://lore.kernel.org/r/a1afaa12f341d146ecbea27c1743661c71683833.1716992815.git.lukas@wunner.de)
- [PCI: pciehp: Use PCI_POSSIBLE_ERROR() to check config reads (commit a3b0f10db148)](https://lore.kernel.org/r/e185b052fbfd530df703a36dd31126cb870eed95.1637243717.git.naveennaidu479@gmail.com)

## REGISTERS

The paths on this page touch seven registers of the port's PCIe capability and, for the replacement check, the identity registers of the function behind the slot. pciehp reaches the capability registers at an offset from [`pci_pcie_cap()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2649) through the capability accessors, and the map shows where they stand in the capability.

```text
    Where the registers sit in the PCIe capability of a hotplug port
    ────────────────────────────────────────────────────────────────

    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    +0x10 │      Link Status (31:16)      │      Link Control (15:0)      │
          ├───────────────────────────────┴───────────────────────────────┤
    +0x14 │                    Slot Capabilities (31:0)                   │
          ├───────────────────────────────┬───────────────────────────────┤
    +0x18 │      Slot Status (31:16)      │      Slot Control (15:0)      │
          ├───────────────────────────────┼───────────────────────────────┤
    +0x30 │     Link Status 2 (31:16)     │     Link Control 2 (15:0)     │
          ├───────────────────────────────┴───────────────────────────────┤
    +0x34 │                   Slot Capabilities 2 (31:0)                  │
          └───────────────────────────────────────────────────────────────┘

    Link Control = PCI_EXP_LNKCTL (0x10), Link Status = PCI_EXP_LNKSTA (0x12)
    Slot Capabilities = PCI_EXP_SLTCAP (0x14, cached in controller.slot_cap)
    Slot Control = PCI_EXP_SLTCTL (0x18, last write cached in controller.slot_ctrl), Slot Status = PCI_EXP_SLTSTA (0x1a)
    Link Status 2 = PCI_EXP_LNKSTA2 (0x32); Link Control 2 is not touched on these paths
    Slot Capabilities 2 = PCI_EXP_SLTCAP2 (0x34); the dwords from +0x1c to +0x2c are not drawn
    every offset is relative to pci_pcie_cap() of the port
```

Slot Capabilities, [`PCI_EXP_SLTCAP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L597), is fixed by the hardware, and probe copies it into [`slot_cap`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L95) once. Its presence bits decide which actions pciehp attempts on these paths. A clear Power Controller Present bit skips the power commands, a clear indicator bit skips that indicator's command, and the MRL Sensor Present bit decides whether the latch can be read. No Command Completed Support decides whether a writer waits for completion, and the Physical Slot Number names the slot.

```text
    Slot Capabilities register, offset 0x14 of the PCIe capability
    ──────────────────────────────────────────────────────────────

    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x14  │           PSN           │N│I│ Q │      SPLV     │C│S│P│A│M│W│B│
          │         (31:19)         │ │ │   │     (14:7)    │ │ │ │ │ │ │ │
          └─────────────────────────┴─┴─┴───┴───────────────┴─┴─┴─┴─┴─┴─┴─┘

    B = PCI_EXP_SLTCAP_ABP (Attention Button Present, ATTN_BUTTN())
    W = PCI_EXP_SLTCAP_PCP (Power Controller Present, POWER_CTRL())
    M = PCI_EXP_SLTCAP_MRLSP (MRL Sensor Present, MRL_SENS())
    A = PCI_EXP_SLTCAP_AIP (Attention Indicator Present, ATTN_LED(); cleared with hotplug_user_indicators)
    P = PCI_EXP_SLTCAP_PIP (Power Indicator Present, PWR_LED(); cleared with hotplug_user_indicators)
    S = PCI_EXP_SLTCAP_HPS (Hot-Plug Surprise, printed at probe)
    C = PCI_EXP_SLTCAP_HPC (Hot-Plug Capable, printed at probe and tested by quirk_cmd_compl())
    SPLV = PCI_EXP_SLTCAP_SPLV (Slot Power Limit Value), Q = PCI_EXP_SLTCAP_SPLS (Slot Power Limit Scale): not read here
    I = PCI_EXP_SLTCAP_EIP (Electromechanical Interlock Present, printed at probe)
    N = PCI_EXP_SLTCAP_NCCS (No Command Completed Support, NO_CMD_CMPL(); forced with is_thunderbolt)
    PSN = PCI_EXP_SLTCAP_PSN (Physical Slot Number, PSN(); the slot's name)
    the whole register is cached in controller.slot_cap
```

Slot Control, [`PCI_EXP_SLTCTL`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L610), holds two kinds of fields. The low six bits and the Data Link Layer State Changed Enable bit choose which Slot Status events raise an interrupt, and the indicator, power and interlock fields drive the slot. A write to any of them is a command that the port acknowledges through Command Completed, and [`slot_ctrl`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L98) keeps the value of the last one.

```text
    Slot Control register, offset 0x18 of the PCIe capability
    ─────────────────────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x18  │·│I│S│L│E│P│PIC│AIC│H│C│D│M│F│B│
          └─┴─┴─┴─┴─┴─┴───┴───┴─┴─┴─┴─┴─┴─┘

    B = PCI_EXP_SLTCTL_ABPE (Attention Button Pressed Enable)   F = PCI_EXP_SLTCTL_PFDE (Power Fault Detected Enable)
    M = PCI_EXP_SLTCTL_MRLSCE (MRL Sensor Changed Enable)       D = PCI_EXP_SLTCTL_PDCE (Presence Detect Changed Enable)
    C = PCI_EXP_SLTCTL_CCIE (Command Completed Interrupt Enable) H = PCI_EXP_SLTCTL_HPIE (Hot-Plug Interrupt Enable)
    AIC = PCI_EXP_SLTCTL_AIC (Attention Indicator Control, bits 7:6: _ATTN_IND_ON 01, _BLINK 10, _OFF 11)
    PIC = PCI_EXP_SLTCTL_PIC (Power Indicator Control, bits 9:8: _PWR_IND_ON 01, _BLINK 10, _OFF 11)
    P = PCI_EXP_SLTCTL_PCC (Power Controller Control: PCI_EXP_SLTCTL_PWR_ON 0, PCI_EXP_SLTCTL_PWR_OFF 1)
    E = PCI_EXP_SLTCTL_EIC (Electromechanical Interlock Control, part of CC_ERRATUM_MASK)
    L = PCI_EXP_SLTCTL_DLLSCE (Data Link Layer State Changed Enable)
    S = PCI_EXP_SLTCTL_ASPL_DISABLE (Auto Slot Power Limit Disable, not written here)
    I = PCI_EXP_SLTCTL_IBPD_DISABLE (In-band PD Disable, written at probe)    · = bit 15, unnamed in pci_regs.h
    the last value written is cached in controller.slot_ctrl
```

Slot Status, [`PCI_EXP_SLTSTA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L633), mixes events and states. An event bit such as Command Completed or Power Fault Detected stays set until software writes 1 to it, while a state bit such as Presence Detect State or MRL Sensor State follows the hardware. These paths read the state bits for presence and latch, read and clear Command Completed and Power Fault Detected, and clear stale events at probe.

```text
    Slot Status register, offset 0x1a of the PCIe capability
    ────────────────────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x1a  │    (15:9)   │L│E│S│R│C│D│M│F│B│
          └─────────────┴─┴─┴─┴─┴─┴─┴─┴─┴─┘

    B = PCI_EXP_SLTSTA_ABP (Attention Button Pressed, event)    F = PCI_EXP_SLTSTA_PFD (Power Fault Detected, event)
    M = PCI_EXP_SLTSTA_MRLSC (MRL Sensor Changed, event)        D = PCI_EXP_SLTSTA_PDC (Presence Detect Changed, event)
    C = PCI_EXP_SLTSTA_CC (Command Completed, event)
    R = PCI_EXP_SLTSTA_MRLSS (MRL Sensor State, state)          S = PCI_EXP_SLTSTA_PDS (Presence Detect State, state)
    E = PCI_EXP_SLTSTA_EIS (Electromechanical Interlock Status, state, not read here)
    L = PCI_EXP_SLTSTA_DLLSC (Data Link Layer State Changed, event)
    (15:9) = bits with no macro in pci_regs.h; an event bit is cleared by writing 1 to it
```

Slot Capabilities 2, [`PCI_EXP_SLTCAP2`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L716), is read at probe for its In-band PD Disable Supported bit. When the port has it, probe sets [`PCI_EXP_SLTCTL_IBPD_DISABLE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L632) in Slot Control, and from then on Presence Detect State reports the out-of-band presence signal alone.

```text
    Slot Capabilities 2 register, offset 0x34 of the PCIe capability
    ────────────────────────────────────────────────────────────────

    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x34  │                            (31:1)                           │I│
          └─────────────────────────────────────────────────────────────┴┬┘
                                                                         │
    IBPD ────────────────────────────────────────────────────────────────┘

    IBPD = PCI_EXP_SLTCAP2_IBPD (In-band PD Disable Supported, 0x00000001, read once at probe)
    (31:1) = bits with no macro in pci_regs.h
```

Link Control, [`PCI_EXP_LNKCTL`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L564), is written on these paths for one bit, the Link Disable bit that power on clears so that the link to a new card can train.

```text
    Link Control register, offset 0x10 of the PCIe capability
    ─────────────────────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x10  │·│·│·│·│·│·│·│·│·│·│·│L│·│·│·│·│
          └─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴┬┴─┴─┴─┴─┘
                                 │
    LD ──────────────────────────┘

    LD = PCI_EXP_LNKCTL_LD (Link Disable, 0x0010, cleared by __pciehp_link_set() when power comes on)
    ·  = the other Link Control fields, ASPM, retrain and clocking controls that the clear-and-set leaves as they are
```

Link Status, [`PCI_EXP_LNKSTA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L577), tells pciehp whether the link below the port is up. The Data Link Layer Link Active bit answers presence for ports whose Presence Detect State does not, and the link check after power on rejects a link that is still training or reports no negotiated width.

```text
    Link Status register, offset 0x12 of the PCIe capability
    ────────────────────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x12  │A│B│D│K│T│·│    nlw    │  cls  │
          │ │ │ │ │ │ │   (9:4)   │ (3:0) │
          └─┴─┴─┴─┴─┴─┴───────────┴───────┘

    cls = PCI_EXP_LNKSTA_CLS (Current Link Speed, mapped into the secondary bus's cur_bus_speed)
    nlw = PCI_EXP_LNKSTA_NLW (Negotiated Link Width, zero means no link was negotiated)
    T = PCI_EXP_LNKSTA_LT (Link Training)          D = PCI_EXP_LNKSTA_DLLLA (Data Link Layer Link Active)
    K = PCI_EXP_LNKSTA_SLC (Slot Clock Configuration, not read here)
    B = PCI_EXP_LNKSTA_LBMS (Link Bandwidth Management Status, not read here)
    A = PCI_EXP_LNKSTA_LABS (Link Autonomous Bandwidth Status, not read here)
    · = bit 10, unnamed in pci_regs.h
```

Link Status 2, [`PCI_EXP_LNKSTA2`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L713), is read by the link check for one bit, Flit Mode Status, which it records for the bus behind the port together with the link speed from Link Status.

```text
    Link Status 2 register, offset 0x32 of the PCIe capability
    ──────────────────────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x32  │·│·│·│·│·│F│·│·│·│·│·│·│·│·│·│·│
          └─┴─┴─┴─┴─┴┬┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┘
                     │
    FLIT ────────────┘

    FLIT = PCI_EXP_LNKSTA2_FLIT (0x0400, Flit Mode Status, copied into the secondary bus's flit_mode)
    ·    = fields of Link Status 2 that the link check does not read
```

The replacement check reads three dwords of the configuration header of function 00.0 behind the slot. It compares each with the values the PCI core cached in that function's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) when it enumerated the function.

```text
    Header dwords of function 00.0 that the replacement check reads
    ───────────────────────────────────────────────────────────────

    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    DW0   │       Device ID (31:16)       │        Vendor ID (15:0)       │
          ├───────────────────────────────┴───────────────┬───────────────┤
    DW2   │               Class Code (31:8)               │ Revision (7:0)│
          ├───────────────────────────────┬───────────────┴───────────────┤
    DW11  │      Subsystem ID (31:16)     │    Subsys Vendor ID (15:0)    │
          └───────────────────────────────┴───────────────────────────────┘

    DW0  = PCI_VENDOR_ID (0x00) and PCI_DEVICE_ID (0x02), compared with vendor | device << 16
    DW2  = PCI_CLASS_REVISION (0x08), compared with revision | class << 8
    DW11 = PCI_SUBSYSTEM_VENDOR_ID (0x2c) and PCI_SUBSYSTEM_ID (0x2e), compared for a normal header only,
           with subsystem_vendor | subsystem_device << 16
```

The same check compares the Device Serial Number, which [`pci_get_dsn()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L555) reads from an extended capability of function 00.0, with the copy probe kept in [`dsn`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L93).

```text
    Device Serial Number capability of function 00.0
    ────────────────────────────────────────────────

    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    +0x0  │       Extended capability header, ID PCI_EXT_CAP_ID_DSN       │
          ├───────────────────────────────────────────────────────────────┤
    +0x4  │               Serial Number, lower dword (31:0)               │
          ├───────────────────────────────────────────────────────────────┤
    +0x8  │               Serial Number, upper dword (31:0)               │
          └───────────────────────────────────────────────────────────────┘

    PCI_EXT_CAP_ID_DSN = 0x03, the capability pci_get_dsn() finds in extended configuration space
    the two dwords form the 64-bit value kept in controller.dsn at probe and compared after resume
    PCI_EXT_CAP_DSN_SIZEOF = 12, the three dwords drawn
```

## DETAILS

The first subsections set up the [`struct controller`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L91) that stands for the slot and the copy of Slot Capabilities probe stores in it. The middle subsections follow one Slot Control command from the merge under the controller's lock to its completion by interrupt, by polling or by deadline, including the ports that cannot report completion. The indicator, power and power fault subsections apply that command to the fields of Slot Control, and the presence, link and replacement subsections read Slot Status, Link Status and the function behind the slot. The page ends with the slot files that reach these registers from user space and with the messages, tracepoint, hand-offs and files that make the paths visible.

### Kconfig assumptions

The page documents x86-64 with ACPI, built from the x86-64 default configuration resolved at v7.2 plus the options this documentation set adds, among them the native hotplug driver and dynamic debug, which the default configuration leaves unset. The table lists the options the prose below names, with the value assumed and what each decides on these paths.

| Option | Assumed | What it decides here |
|---|---|---|
| [`CONFIG_HOTPLUG_PCI_PCIE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L16) | y | builds pciehp and the [`broken_cmd_compl`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L521) member of [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) |
| [`CONFIG_HOTPLUG_PCI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/Kconfig#L6) | y | builds the hotplug core whose slot files call the slot operations |
| [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5) | y | builds the port driver that pciehp binds to as a service |
| [`CONFIG_PCI_MSI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L44) | y | lets the interrupt handler re-read Slot Status for a port using MSI |
| [`CONFIG_PM`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L217) | y | builds the runtime resume hook that marks a command outstanding |
| [`CONFIG_PM_SLEEP`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L140) | y | builds the system resume hook that marks a command outstanding and checks for a replaced device |
| [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) | y | makes the [`ctrl_dbg()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L35) sites switchable at run time |
| [`CONFIG_PCI_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L70) | not set | would define `DEBUG` for drivers/pci and print those sites from boot |

The table indexes the prose, and each option's effect is stated again where it applies in the subsections below.

### One controller stands for the slot and its register state

Between one register access and the next, pciehp has to remember three kinds of facts about a slot, the features the hardware fixed, the last command it sent and whether that command is still in progress. It keeps them in a [`struct controller`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L91), one per hotplug port, which [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) allocates when pciehp probes the port. The port is reached through [`pcie`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L92), a [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59) that is portdrv's service instance for the hotplug service, whose [`port`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L61) is the port's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352).

The table names each member of the struct, grouped as the struct's own comments group them, with what it holds and where this page meets it.

| Member | Group | What it holds | On this page |
|---|---|---|---|
| [`pcie`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L92) | none | the service instance, and through it the port | every register access |
| [`dsn`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L93) | none | the Device Serial Number of function 00.0 | the replacement check |
| [`slot_cap`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L95) | capabilities and quirks | the probe-time copy of Slot Capabilities | the feature macros |
| [`inband_presence_disabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L96) | capabilities and quirks | whether probe turned in-band presence detection off | the link check |
| [`slot_ctrl`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L98) | control register access | the value of the last command | the command path and the wait |
| [`ctrl_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L99) | control register access | the mutex that lets one command writer through | the command path |
| [`cmd_started`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L100) | control register access | the jiffies of the last Slot Control write | the deadline of the wait |
| [`cmd_busy`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L101) | control register access | whether a command waits for Command Completed | the wait, the handler, resume |
| [`queue`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L102) | control register access | where a writer sleeps until completion | the wait and the handler |
| [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104) | event handling | events the handler passes to its thread | the power and link checks |
| [`notification_enabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L105) | event handling | whether the interrupt was requested | not read here |
| [`power_fault_detected`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L106) | event handling | a power fault seen and still unhandled | the power fault pair |
| [`poll_thread`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L107) | event handling | the thread that polls when there is no interrupt | the hand-offs |
| [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109), [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110), [`button_work`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L111) | state machine | the slot's state, its lock and the button delay work | not read here |
| [`hotplug_slot`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L113) | hotplug core interface | the slot registered with the hotplug core | the slot files |
| [`reset_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114), [`depth`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L115) | hotplug core interface | a lock against reads during a slot reset and its nesting level | not read here |
| [`ist_running`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L116), [`request_result`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L117), [`requester`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L118) | hotplug core interface | state of a pending request from user space | not read here |

The definition below is the whole struct, so that the groups of the table can be found in it, and the comments at the end of its group lines are the struct's own.

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

The first two groups are the slot's register state, and the rest of the page reads them. The event handling and state machine groups belong to the interrupt and state machine paths, which this page meets at [`power_fault_detected`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L106), [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104) and [`poll_thread`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L107) only.

The register helpers of [`pciehp_hpc.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c) reach the port through [`ctrl_dev()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L49), a one-line helper that follows the two pointers.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:49 */
static inline struct pci_dev *ctrl_dev(struct controller *ctrl)
{
	return ctrl->pcie->port;
}
```

[`ctrl_dev()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L49) returns the port's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352), whose [`pcie_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L379) is the base that the capability accessors add a register offset to. The slot operations go the other way, from the [`struct hotplug_slot`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L57) that the hotplug core passes them back to the controller, through [`to_ctrl()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L207).

```c
/* drivers/pci/hotplug/pciehp.h:207 */
static inline struct controller *to_ctrl(struct hotplug_slot *hotplug_slot)
{
	return container_of(hotplug_slot, struct controller, hotplug_slot);
}
```

[`to_ctrl()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L207) works because [`hotplug_slot`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L113) is embedded in the controller, so `container_of()` subtracts the member's offset. The figure places the controller between the port it drives and the operations it hands to the hotplug core.

```text
    The controller reaches the port, its registers and its slot operations
    ──────────────────────────────────────────────────────────────────────

    ┌─────────────────────────────────┐             ┌───────────────────────────────────┐
    │ struct controller               │             │ struct pcie_device                │
    ├─────────────────────────────────┤             ├───────────────────────────────────┤
    │ pcie ───────────────────────────┼────────────▶│ port ─────────────────────────────┼───────┐
    │                                 │             │ irq   the service interrupt       │       │
    │ slot_cap, slot_ctrl             │             └───────────────────────────────────┘       │
    │ cmd_busy, cmd_started           │                                                         │
    │ inband_presence_disabled        │                                                         ▼
    │ ┌─────────────────────────────┐ │                         ┌──────────────────────────────────────────────────┐
    │ │ hotplug_slot, embedded      │ │                         │ struct pci_dev, the hotplug port                 │
    │ │                             │ │                         ├──────────────────────────────────────────────────┤
    │ │ ops ────────────┐           │ │                         │ pcie_cap     the PCIe capability's offset        │
    │ └─────────────────┼───────────┘ │                         │ subordinate  the bus behind the slot             │
    └───────────────────┼─────────────┘                         │ broken_cmd_compl, hotplug_user_indicators        │
                        │                                       └──────────────┬───────────────────────────────────┘
                        │ installed by init_slot()                             │
                        │                                                      │ pci_pcie_cap() + PCI_EXP_SLT*
                        ▼                                                      ▼
    ┌─────────────────────────────────────────────┐             ┌──────────────────────────────────────────────────┐
    │ struct hotplug_slot_ops                     │             │ Slot Capabilities, Slot Control, Slot Status     │
    │ get_power_status, get_adapter_status,       │             └──────────────────────────────────────────────────┘
    │ get_latch_status, set_attention_status      │
    └─────────────────────────────────────────────┘

    ctrl_dev(ctrl) follows pcie and port; to_ctrl() goes back from the embedded hotplug_slot to its controller
```

The controller points at the port through two pointers and holds the slot by value, which is how one structure serves both the specification's Hot-Plug Controller and its slot. Three members of the control register group are written by several functions, and the strip follows one controller through a command and a system resume; the subsections that follow show each marked write in the order of its mark.

```text
    The command fields of one controller across a command and a resume
    ──────────────────────────────────────────────────────────────────

    time ──────────────────────────────────────────────────────────────────────────────────────────▶
                   alloc         issue           CC seen           resume            next issue
                   ▼             ▼               ▼                 ▼                 ▼
                  ┌─────────────┬───────────────────────────────────────────────────┬────────────────┐
    slot_ctrl     │ ① 0         │ ③ the merged value                                │ ③ next         │
                  └─────────────┴───────────────────────────────────────────────────┴────────────────┘
                  ┌─────────────┬───────────────┬─────────────────┬─────────────────┬────────────────┐
    cmd_busy      │ ① 0         │ ② 1           │ ⑤ ⑥ ⑦ 0         │ ⑨ 1             │ ② 1            │
                  └─────────────┴───────────────┴─────────────────┴─────────────────┴────────────────┘
                  ┌─────────────┬─────────────────────────────────┬─────────────────┬────────────────┐
    cmd_started   │ ① 0         │ ④ jiffies at issue              │ ⑧ at resume     │ ④ next         │
                  └─────────────┴─────────────────────────────────┴─────────────────┴────────────────┘

    fields: slot_ctrl, cmd_busy, cmd_started of struct controller; ⑤ ⑥ ⑦ are alternatives

    ① pcie_init            pciehp_hpc.c:1014  allocates the controller zeroed through kzalloc_obj
    ② pcie_do_write_cmd    :179  sets cmd_busy before the Slot Control write
    ③ pcie_do_write_cmd    :181  records the merged command value in slot_ctrl
    ④ pcie_do_write_cmd    :183  stamps cmd_started right after the write
    ⑤ pcie_do_write_cmd    :194  clears cmd_busy when the erratum suppresses completion
    ⑥ pcie_poll_cmd        :102  clears cmd_busy after it clears Command Completed
    ⑦ pciehp_isr           :708  clears cmd_busy when the interrupt reports Command Completed
    ⑧ pciehp_resume_noirq  pciehp_core.c:293  stamps cmd_started for the restored Slot Control
    ⑨ pciehp_resume_noirq  :294  sets cmd_busy so the next command waits first
```

① [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) allocates the controller zeroed, so the three fields start at 0. ② [`pcie_do_write_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L157) sets [`cmd_busy`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L101) before it writes Slot Control. ③ `pcie_do_write_cmd()` stores the merged value in [`slot_ctrl`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L98). ④ `pcie_do_write_cmd()` stamps [`cmd_started`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L100) with the time of the write. ⑤ `pcie_do_write_cmd()` clears `cmd_busy` again when the port has the Command Completed erratum and the command changed no Control bit. ⑥ [`pcie_poll_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L86) clears `cmd_busy` when it finds Command Completed in Slot Status. ⑦ [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623) clears `cmd_busy` when an interrupt reports Command Completed. ⑧ [`pciehp_resume_noirq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L288) stamps `cmd_started` after a system resume. ⑨ `pciehp_resume_noirq()` sets `cmd_busy`, because the PCI core has just restored Slot Control.

Two writers of these fields are not drawn. [`pciehp_runtime_resume()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L336) in [`pciehp_core.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c) makes the same two writes as ⑧ and ⑨ after a runtime resume with [`CONFIG_PM`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L217) set, and the strip shows one resume. [`pciehp_release_ctrl()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1096) in [`pciehp_hpc.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c) frees the controller when pciehp leaves the port, which belongs to the remove path. Between ② and the first of ⑤, ⑥ and ⑦, the register holds a value the port may not have acted on yet, and and the next writer waits that interval out.

### Probe reads Slot Capabilities once and macros test the copy

The features of a slot stay fixed while the port exists, so pciehp reads Slot Capabilities once, when [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) builds the controller, and the decisions after probe test the copy. The copy can differ from the register, because probe overrides bits that the hardware reports wrongly or that user space has taken over.

The register is defined in [`pci_regs.h`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h), where [`PCI_EXP_SLTCAP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L597) is its offset in the PCIe capability and the masks below it name its fields. The excerpt is the block that defines the register, read for the bits that pciehp tests.

```c
/* include/uapi/linux/pci_regs.h:597 */
#define PCI_EXP_SLTCAP		0x14	/* Slot Capabilities */
#define  PCI_EXP_SLTCAP_ABP	0x00000001 /* Attention Button Present */
#define  PCI_EXP_SLTCAP_PCP	0x00000002 /* Power Controller Present */
#define  PCI_EXP_SLTCAP_MRLSP	0x00000004 /* MRL Sensor Present */
#define  PCI_EXP_SLTCAP_AIP	0x00000008 /* Attention Indicator Present */
#define  PCI_EXP_SLTCAP_PIP	0x00000010 /* Power Indicator Present */
#define  PCI_EXP_SLTCAP_HPS	0x00000020 /* Hot-Plug Surprise */
#define  PCI_EXP_SLTCAP_HPC	0x00000040 /* Hot-Plug Capable */
#define  PCI_EXP_SLTCAP_SPLV	0x00007f80 /* Slot Power Limit Value */
#define  PCI_EXP_SLTCAP_SPLS	0x00018000 /* Slot Power Limit Scale */
#define  PCI_EXP_SLTCAP_EIP	0x00020000 /* Electromechanical Interlock Present */
#define  PCI_EXP_SLTCAP_NCCS	0x00040000 /* No Command Completed Support */
#define  PCI_EXP_SLTCAP_PSN	0xfff80000 /* Physical Slot Number */
```

[`PCI_EXP_SLTCAP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L597) is 0x14, the offset the accessors add to the capability's base, and the masks are the fields the Slot Capabilities drawing above places on the bit ruler. The presence bits from [`PCI_EXP_SLTCAP_ABP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L598) to [`PCI_EXP_SLTCAP_PIP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L602), [`PCI_EXP_SLTCAP_NCCS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L608) and [`PCI_EXP_SLTCAP_PSN`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L609) steer these paths, and pciehp reads neither power limit field.

[`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) belongs to pciehp's probe path, and the stage below runs from its start to the store into [`slot_cap`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L95). Read it for the allocation, the read of Slot Capabilities and the two adjustments made before the store.

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

	/*
	 * We assume no Thunderbolt controllers support Command Complete events,
	 * but some controllers falsely claim they do.
	 */
	if (pdev->is_thunderbolt)
		slot_cap |= PCI_EXP_SLTCAP_NCCS;

	ctrl->slot_cap = slot_cap;
```

`kzalloc_obj()` returns the controller zeroed, mark ① of the strip. [`pcie_capability_read_dword()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/access.c#L462) reads the register into `slot_cap`, a local of [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006), and two flags of the port's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) adjust that local before it is stored. A port with [`hotplug_user_indicators`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L425) set, whose comment says user sysfs controls the indicators exclusively, loses its Attention and Power Indicator Present bits. A port with [`is_thunderbolt`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L486) set gains [`PCI_EXP_SLTCAP_NCCS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L608), because, as the comment says, the code assumes such ports lack Command Completed support although some claim it.

The figure compares the register with the stored copy, cell for cell.

```text
    Slot Capabilities before and after probe stores it in slot_cap
    ──────────────────────────────────────────────────────────────

                  31:19       18          17:5          4         3         2:0
                ┌───────────┬───────────┬─────────────┬─────────┬─────────┬─────────────┐
    SLTCAP      │ PSN       │ NCCS      │ as read     │ PIP     │ AIP     │ as read     │
                └───────────┴───────────┴─────────────┴─────────┴─────────┴─────────────┘
          │
          │ probe copies the word, adjusting two places
          │
          ▼
                ┌───────────┬───────────┬─────────────┬─────────┬─────────┬─────────────┐
    slot_cap    │ PSN       │ NCCS      │ as read     │ PIP     │ AIP     │ as read     │
                └───────────┴───────────┴─────────────┴─────────┴─────────┴─────────────┘
                               ▲                           ▲         ▲
                               set when is_thunderbolt               cleared together when
                                                                     hotplug_user_indicators
```

Outside the two adjustments the copy equals the register, and the store at the end of the stage is the one assignment to [`slot_cap`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L95) in pciehp. pciehp reads the copy through one-line macros in [`pciehp.h`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h), each of which tests one field of it.

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

Each macro yields the masked field, nonzero when the feature is present, and [`PSN()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L162) shifts the Physical Slot Number down from bit 19. The macros are the questions later code asks about the slot, and the table gives the decision each one steers on these paths.

| Macro | Field of Slot Capabilities | What it decides here |
|---|---|---|
| [`ATTN_BUTTN()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L156) | Attention Button Present | whether notifications enable the button event or Presence Detect Changed |
| [`POWER_CTRL()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L157) | Power Controller Present | whether add, remove and probe issue power commands |
| [`MRL_SENS()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L158) | MRL Sensor Present | whether the latch is read and the latch operation installed |
| [`ATTN_LED()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L159) | Attention Indicator Present | whether the attention field joins a command and the attention operations are installed |
| [`PWR_LED()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L160) | Power Indicator Present | whether the power indicator field joins a command |
| [`NO_CMD_CMPL()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L161) | No Command Completed Support | whether a writer waits for completion |
| [`PSN()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L162) | Physical Slot Number | the slot's name in sysfs and in messages |

The controller now holds a fixed description of the slot, and the first thing that description steers is a command written to Slot Control, which the next subsection follows.

### Every Slot Control change is one merged command

Slot Control carries interrupt enables, indicator fields and the power bit side by side, and several pciehp paths change different fields of it. The specification text quoted in commit commit [469e764c4a3c](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=469e764c4a3c7260b353b7bc1bd56c283cb001da) ("PCI: pciehp: Obey compulsory command delay after resume") requires software to wait for a command to complete before it issues the next. pciehp therefore sends each change through [`pcie_do_write_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L157), which lets one writer through at a time and merges each change into the register's current value.

The register is defined in [`pci_regs.h`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h) next to Slot Capabilities, where [`PCI_EXP_SLTCTL`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L610) is its offset and the masks and values below it are the fields a command changes.

```c
/* include/uapi/linux/pci_regs.h:610 */
#define PCI_EXP_SLTCTL		0x18	/* Slot Control */
#define  PCI_EXP_SLTCTL_ABPE	0x0001	/* Attention Button Pressed Enable */
#define  PCI_EXP_SLTCTL_PFDE	0x0002	/* Power Fault Detected Enable */
#define  PCI_EXP_SLTCTL_MRLSCE	0x0004	/* MRL Sensor Changed Enable */
#define  PCI_EXP_SLTCTL_PDCE	0x0008	/* Presence Detect Changed Enable */
#define  PCI_EXP_SLTCTL_CCIE	0x0010	/* Command Completed Interrupt Enable */
#define  PCI_EXP_SLTCTL_HPIE	0x0020	/* Hot-Plug Interrupt Enable */
#define  PCI_EXP_SLTCTL_AIC	0x00c0	/* Attention Indicator Control */
#define  PCI_EXP_SLTCTL_ATTN_IND_SHIFT 6      /* Attention Indicator shift */
#define  PCI_EXP_SLTCTL_ATTN_IND_ON    0x0040 /* Attention Indicator on */
#define  PCI_EXP_SLTCTL_ATTN_IND_BLINK 0x0080 /* Attention Indicator blinking */
#define  PCI_EXP_SLTCTL_ATTN_IND_OFF   0x00c0 /* Attention Indicator off */
#define  PCI_EXP_SLTCTL_PIC	0x0300	/* Power Indicator Control */
#define  PCI_EXP_SLTCTL_PWR_IND_ON     0x0100 /* Power Indicator on */
#define  PCI_EXP_SLTCTL_PWR_IND_BLINK  0x0200 /* Power Indicator blinking */
#define  PCI_EXP_SLTCTL_PWR_IND_OFF    0x0300 /* Power Indicator off */
#define  PCI_EXP_SLTCTL_PCC	0x0400	/* Power Controller Control */
#define  PCI_EXP_SLTCTL_PWR_ON         0x0000 /* Power On */
#define  PCI_EXP_SLTCTL_PWR_OFF        0x0400 /* Power Off */
#define  PCI_EXP_SLTCTL_EIC	0x0800	/* Electromechanical Interlock Control */
#define  PCI_EXP_SLTCTL_DLLSCE	0x1000	/* Data Link Layer State Changed Enable */
#define  PCI_EXP_SLTCTL_ASPL_DISABLE	0x2000 /* Auto Slot Power Limit Disable */
#define  PCI_EXP_SLTCTL_IBPD_DISABLE	0x4000 /* In-band PD disable */
```

[`PCI_EXP_SLTCTL`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L610) is 0x18. The enables run from [`PCI_EXP_SLTCTL_ABPE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L611) at bit 0 to [`PCI_EXP_SLTCTL_HPIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L616) at bit 5, with [`PCI_EXP_SLTCTL_DLLSCE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L630) at bit 12. The fields that drive the slot are [`PCI_EXP_SLTCTL_AIC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L617) and [`PCI_EXP_SLTCTL_PIC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L622), two bits each with on, blink and off values, and the bit [`PCI_EXP_SLTCTL_PCC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L626), whose value 0 is power on.

A command names the bits it sets in `cmd` and the field it changes in `mask`, and the merge keeps every bit outside the mask. The figure shows one power-on command merged into an example value.

```text
    One power-on command merged into Slot Control
    ─────────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    read  │0│0│0│1│0│1│1│1│1│1│1│1│1│0│0│0│  0x17f8, slot_ctrl as read
          ├─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┤
    mask  │ │ │ │ │ │1│ │ │ │ │ │ │ │ │ │ │  PCI_EXP_SLTCTL_PCC, the field to change
          ├─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┤
    cmd   │ │ │ │ │ │0│ │ │ │ │ │ │ │ │ │ │  PCI_EXP_SLTCTL_PWR_ON & mask
          ├─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┤
    write │0│0│0│1│0│0│1│1│1│1│1│1│1│0│0│0│  0x13f8, written and kept in slot_ctrl
          └─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┘

    read: an example port with DLLSCE, HPIE, CCIE and PDCE set, both indicators off and power off
    write = (read & ~mask) | (cmd & mask): bit 10 drops to 0, every bit outside the mask keeps its value
    power off is the same command with PCI_EXP_SLTCTL_PWR_OFF, which puts 1 back in bit 10
```

Only bit 10 changes, because the mask holds only [`PCI_EXP_SLTCTL_PCC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L626), and the enables and indicators keep the values the read returned. [`pcie_do_write_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L157) takes the controller, `cmd`, `mask` and a flag `wait`, all of them parameters, and it is read in three pieces.

| Piece | Lines | Stage |
|---|---|---|
| ❶ | pciehp_hpc.c:157-169 | takes the lock and waits out the previous command |
| ❷ | pciehp_hpc.c:170-184 | reads, merges and writes Slot Control, marking the command outstanding |
| ❸ | pciehp_hpc.c:185-205 | applies the erratum, waits for this command when asked, and unlocks |

Piece ❶ of [`pcie_do_write_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L157) takes [`ctrl_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L99) and waits for any command still outstanding before it touches the register.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:157 */
static void pcie_do_write_cmd(struct controller *ctrl, u16 cmd,
			      u16 mask, bool wait)
{
	struct pci_dev *pdev = ctrl_dev(ctrl);
	u16 slot_ctrl_orig, slot_ctrl;

	mutex_lock(&ctrl->ctrl_lock);

	/*
	 * Always wait for any previous command that might still be in progress
	 */
	pcie_wait_cmd(ctrl);

```

The mutex is held for the whole command, both waits included, so two paths that change different fields cannot interleave their reads and writes. [`pcie_wait_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L112) returns at once when no command is outstanding, as the next subsection shows.

Piece ❷ of [`pcie_do_write_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L157) reads the register, merges the change and writes it back, marking the command outstanding around the write.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:170 */
	pcie_capability_read_word(pdev, PCI_EXP_SLTCTL, &slot_ctrl);
	if (PCI_POSSIBLE_ERROR(slot_ctrl)) {
		ctrl_info(ctrl, "%s: no response from device\n", __func__);
		goto out;
	}

	slot_ctrl_orig = slot_ctrl;
	slot_ctrl &= ~mask;
	slot_ctrl |= (cmd & mask);
	ctrl->cmd_busy = 1;
	smp_mb();
	ctrl->slot_ctrl = slot_ctrl;
	pcie_capability_write_word(pdev, PCI_EXP_SLTCTL, slot_ctrl);
	ctrl->cmd_started = jiffies;

```

The local `slot_ctrl` of [`pcie_do_write_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L157) keeps the bits outside `mask` and takes the bits of `cmd` inside it. A read that returns all ones, which [`PCI_POSSIBLE_ERROR()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L175) recognizes, abandons the command before any write. [`cmd_busy`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L101) is set, and the full barrier `smp_mb()` orders that store before the stores after it, the store of the merged value into [`slot_ctrl`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L98) and the register write. [`cmd_started`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L100) then records the time of the write, so marks ②, ③ and ④ of the strip fall in this piece.

Piece ❸ of [`pcie_do_write_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L157) handles ports that report completion for some commands only, waits for this command when the caller asked, and releases the lock.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:185 */
	/*
	 * Controllers with the Intel CF118 and similar errata advertise
	 * Command Completed support, but they only set Command Completed
	 * if we change the "Control" bits for power, power indicator,
	 * attention indicator, or interlock.  If we only change the
	 * "Enable" bits, they never set the Command Completed bit.
	 */
	if (pdev->broken_cmd_compl &&
	    (slot_ctrl_orig & CC_ERRATUM_MASK) == (slot_ctrl & CC_ERRATUM_MASK))
		ctrl->cmd_busy = 0;

	/*
	 * Optionally wait for the hardware to be ready for a new command,
	 * indicating completion of the above issued command.
	 */
	if (wait)
		pcie_wait_cmd(ctrl);

out:
	mutex_unlock(&ctrl->ctrl_lock);
}
```

With `wait` false the function returns while the command can still be outstanding, and the first wait of the next command absorbs it. The test on [`broken_cmd_compl`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L521), mark ⑤ of the strip, belongs to the ports that report completion for some commands only, which a later subsection reads. In [`pciehp_hpc.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c) the two wrappers below are the callers of [`pcie_do_write_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L157), and each fixes `wait`.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:207 */
/**
 * pcie_write_cmd - Issue controller command
 * @ctrl: controller to which the command is issued
 * @cmd:  command value written to slot control register
 * @mask: bitmask of slot control register to be modified
 */
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

[`pcie_write_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L213) waits after the write, so its caller continues with the command complete or timed out, and [`pcie_write_cmd_nowait()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L219) leaves that wait to the next command. Commit commit [a5dd4b4b0570](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=a5dd4b4b0570b3bf880d563969b245dfbd170c1e) ("PCI: pciehp: Wait for hotplug command completion where necessary") split them, and its message says that power on enables the link and relies on the power command having completed, while power off and the disabling of notifications precede the freeing of data structures. The table lists the callers of the two wrappers in [`pciehp_hpc.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c), five of the waiting one and four of the other.

| Caller | Wrapper and site | Slot Control bits the command changes |
|---|---|---|
| [`pciehp_power_on_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L534) | [`pcie_write_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L213) at [`pciehp_hpc.c:547`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L547) | [`PCI_EXP_SLTCTL_PCC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L626) to power on |
| [`pciehp_power_off_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L559) | [`pcie_write_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L213) at [`pciehp_hpc.c:561`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L561) | [`PCI_EXP_SLTCTL_PCC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L626) to power off |
| [`pcie_disable_notification()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L861) | [`pcie_write_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L213) at [`pciehp_hpc.c:869`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L869) | clears the event enables |
| [`pcie_enable_interrupt()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L880) | [`pcie_write_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L213) at [`pciehp_hpc.c:887`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L887) | sets [`PCI_EXP_SLTCTL_DLLSCE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L630) and, without polling, [`PCI_EXP_SLTCTL_HPIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L616) |
| [`pcie_disable_interrupt()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L890) | [`pcie_write_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L213) at [`pciehp_hpc.c:902`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L902) | clears [`PCI_EXP_SLTCTL_HPIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L616) and [`PCI_EXP_SLTCTL_DLLSCE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L630) |
| [`pciehp_set_raw_indicator_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L483) | [`pcie_write_cmd_nowait()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L219) at [`pciehp_hpc.c:492`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L492) | [`PCI_EXP_SLTCTL_AIC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L617) and [`PCI_EXP_SLTCTL_PIC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L622) as one value |
| [`pciehp_set_indicators()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L513) | [`pcie_write_cmd_nowait()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L219) at [`pciehp_hpc.c:528`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L528) | [`PCI_EXP_SLTCTL_PIC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L622), [`PCI_EXP_SLTCTL_AIC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L617) or both |
| [`pcie_enable_notification()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L821) | [`pcie_write_cmd_nowait()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L219) at [`pciehp_hpc.c:856`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L856) | sets the event enables |
| [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) | [`pcie_write_cmd_nowait()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L219) at [`pciehp_hpc.c:1047`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1047) | sets [`PCI_EXP_SLTCTL_IBPD_DISABLE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L632) |

A command now leaves [`cmd_busy`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L101) set and its time in [`cmd_started`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L100), and what clears the flag is the subject of the next subsection.

### A command stays outstanding until completion or a deadline

The port reports that it has finished a command by setting Command Completed in Slot Status, and pciehp learns of it either from its interrupt handler or by reading Slot Status itself. [`pcie_wait_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L112) decides which, and it bounds the wait by a deadline counted from [`cmd_started`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L100), so a command the port never acknowledges delays the next one by the timeout at most. The figure follows one command across the writer, the port and the interrupt handler.

```text
    One command handed between the writer, the port and the interrupt handler
    ─────────────────────────────────────────────────────────────────────────

    time ↓
    writer, holding ctrl_lock       ╎ port                           ╎ hard IRQ handler
    ────────────────────────────────┼────────────────────────────────┼────────────────────────────────
    waits out the previous command  ╎                                ╎
    cmd_busy = 1                    ╎                                ╎
    Slot Control ← merged value ──────▶ latches the command          ╎
    cmd_started = jiffies           ╎ acts on power or indicators    ╎
    nowait: unlocks and returns     ╎                                ╎
    wait: sleeps on queue           ╎                                ╎
                                    ╎ sets Command Completed ──────────▶ reads CC in Slot Status
                                    ╎                                ╎ clears CC, cmd_busy = 0
    woken, the wait ends ◀─────────────────────────────────────────── wakes queue
    ctrl_lock released              ╎ ready for the next command     ╎

    without HPIE and CCIE in slot_ctrl the writer reads Slot Status itself every 10 ms and clears CC
    the wait gives up 1000 ms after cmd_started, or 2500 ms when pciehp_poll_mode is set
```

The writer holds [`ctrl_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L99) throughout, and the handler's part is to clear [`cmd_busy`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L101) and wake [`queue`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L102). [`pcie_wait_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L112) runs at the start of every command and, for [`pcie_write_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L213), again after the write; read it for the two early returns, the deadline and the choice between sleeping and polling.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:112 */
static void pcie_wait_cmd(struct controller *ctrl)
{
	unsigned int msecs = pciehp_poll_mode ? 2500 : 1000;
	unsigned long duration = msecs_to_jiffies(msecs);
	unsigned long cmd_timeout = ctrl->cmd_started + duration;
	unsigned long now, timeout;
	int rc;

	/*
	 * If the controller does not generate notifications for command
	 * completions, we never need to wait between writes.
	 */
	if (NO_CMD_CMPL(ctrl))
		return;

	if (!ctrl->cmd_busy)
		return;

	/*
	 * Even if the command has already timed out, we want to call
	 * pcie_poll_cmd() so it can clear PCI_EXP_SLTSTA_CC.
	 */
	now = jiffies;
	if (time_before_eq(cmd_timeout, now))
		timeout = 1;
	else
		timeout = cmd_timeout - now;

	if (ctrl->slot_ctrl & PCI_EXP_SLTCTL_HPIE &&
	    ctrl->slot_ctrl & PCI_EXP_SLTCTL_CCIE)
		rc = wait_event_timeout(ctrl->queue, !ctrl->cmd_busy, timeout);
	else
		rc = pcie_poll_cmd(ctrl, jiffies_to_msecs(timeout));

	if (!rc)
		ctrl_info(ctrl, "Timeout on hotplug command %#06x (issued %u msec ago)\n",
			  ctrl->slot_ctrl,
			  jiffies_to_msecs(jiffies - ctrl->cmd_started));
}
```

The deadline is [`cmd_started`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L100) plus 1000 ms, or 2500 ms when [`pciehp_poll_mode`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L34) is set. A deadline already passed leaves a timeout of one jiffy, so that, as the comment says, [`pcie_poll_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L86) still runs and can clear Command Completed. The writer sleeps on [`queue`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L102) when the last command left both [`PCI_EXP_SLTCTL_HPIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L616) and [`PCI_EXP_SLTCTL_CCIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L615) set in [`slot_ctrl`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L98), the two enables for a completion interrupt, and polls otherwise. A zero result from either wait prints the timeout message with the command value and its age in milliseconds.

The figure puts the two cases of the deadline on one axis.

```text
    How long the next writer waits, measured from the last write
    ────────────────────────────────────────────────────────────
    one axis of time since cmd_started; duration is 1000 ms, or 2500 ms when pciehp_poll_mode is set

    cmd_started                         cmd_timeout
    ├─────────────┬─────────────────────┬────────────┬────────▶ jiffies
                  │                     │            └─ now, past the deadline: timeout = 1, one more check
                  │                     └─ cmd_started + duration, the deadline
                  └─ now, before the deadline: timeout = cmd_timeout - now

    in the polling path that one check also clears a Command Completed that arrived late
```

Because the deadline counts from the write, a command issued without waiting costs the next writer only the rest of its timeout, which commit commit [40b960831cfa](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=40b960831cfa8ee34d4b1035ddd7074bc5b01ecf) ("PCI: pciehp: Compute timeout from hotplug command start time") introduced. [`pcie_poll_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L86) is the polling side that the wait uses when completion interrupts are off; read it for the 10 ms loop and the write that clears Command Completed.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:86 */
static int pcie_poll_cmd(struct controller *ctrl, int timeout)
{
	struct pci_dev *pdev = ctrl_dev(ctrl);
	u16 slot_status;

	do {
		pcie_capability_read_word(pdev, PCI_EXP_SLTSTA, &slot_status);
		if (PCI_POSSIBLE_ERROR(slot_status)) {
			ctrl_info(ctrl, "%s: no response from device\n",
				  __func__);
			return 0;
		}

		if (slot_status & PCI_EXP_SLTSTA_CC) {
			pcie_capability_write_word(pdev, PCI_EXP_SLTSTA,
						   PCI_EXP_SLTSTA_CC);
			ctrl->cmd_busy = 0;
			smp_mb();
			return 1;
		}
		msleep(10);
		timeout -= 10;
	} while (timeout >= 0);
	return 0;	/* timeout */
}
```

The loop reads Slot Status every 10 ms until `timeout`, its parameter in milliseconds, runs out, and a set [`PCI_EXP_SLTSTA_CC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L638) is written back to clear it, since an event bit of Slot Status clears when software writes 1 to it. Clearing [`cmd_busy`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L101) there is mark ⑥ of the strip. A read of all ones prints that the device does not respond and returns 0, the same result as a timeout.

With completion interrupts on, the clearing happens in [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623), the hard interrupt handler, which handles Command Completed itself, as its comment explains. The stage below starts at the handler's signature and folds the lines that read Slot Status and write its event bits back, which the power fault subsection shows.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:623 */
static irqreturn_t pciehp_isr(int irq, void *dev_id)
{
	... /* 78 lines, to :703 */
	/*
	 * Command Completed notifications are not deferred to the
	 * IRQ thread because it may be waiting for their arrival.
	 */
	if (events & PCI_EXP_SLTSTA_CC) {
		ctrl->cmd_busy = 0;
		smp_mb();
		wake_up(&ctrl->queue);

		if (events == PCI_EXP_SLTSTA_CC)
			return IRQ_HANDLED;

		events &= ~PCI_EXP_SLTSTA_CC;
	}
```

By line 703 the handler has collected the event bits in `events`, a local of [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623). [`cmd_busy`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L101) is cleared and published by `smp_mb()` before `wake_up()`, mark ⑦ of the strip, and an interrupt that carried Command Completed alone ends there. The comment gives the reason for doing it in hard interrupt context, which is that the thread may itself be waiting for the completion.

A command thus ends when its flag drops, by polling, by interrupt or at the deadline, and the next subsection turns to ports whose completion never comes or comes for some commands only.

### Ports without usable completion skip or shorten the wait

Some ports never set Command Completed, and some set it only when a command changes certain fields, so a writer that waited for each command would stall until the deadline. pciehp handles the first kind through the No Command Completed Support bit of its copy of Slot Capabilities, and the second through a flag that a fixup sets on the port's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352).

For the first kind, [`NO_CMD_CMPL()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L161) tests [`PCI_EXP_SLTCAP_NCCS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L608) in [`slot_cap`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L95), and the first early return of [`pcie_wait_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L112) skips the wait. The lines are shown again with the function's start.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:112 */
static void pcie_wait_cmd(struct controller *ctrl)
{
	... /* 6 lines, to :120 */
	/*
	 * If the controller does not generate notifications for command
	 * completions, we never need to wait between writes.
	 */
	if (NO_CMD_CMPL(ctrl))
		return;
```

[`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) sets the same bit in the copy for ports flagged [`is_thunderbolt`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L486), as the probe subsection showed, so those ports skip the wait as well. For the second kind, [`quirk_cmd_compl()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1102) reads Slot Capabilities straight from the port before pciehp exists for it, and the macro lines after it register it as an early class fixup for a list of bridge IDs.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:1102 */
static void quirk_cmd_compl(struct pci_dev *pdev)
{
	u32 slot_cap;

	if (pci_is_pcie(pdev)) {
		pcie_capability_read_dword(pdev, PCI_EXP_SLTCAP, &slot_cap);
		if (slot_cap & PCI_EXP_SLTCAP_HPC &&
		    !(slot_cap & PCI_EXP_SLTCAP_NCCS))
			pdev->broken_cmd_compl = 1;
	}
}
DECLARE_PCI_FIXUP_CLASS_EARLY(PCI_VENDOR_ID_INTEL, PCI_ANY_ID,
			      PCI_CLASS_BRIDGE_PCI, 8, quirk_cmd_compl);
DECLARE_PCI_FIXUP_CLASS_EARLY(PCI_VENDOR_ID_QCOM, 0x010e,
			      PCI_CLASS_BRIDGE_PCI, 8, quirk_cmd_compl);
DECLARE_PCI_FIXUP_CLASS_EARLY(PCI_VENDOR_ID_QCOM, 0x0110,
			      PCI_CLASS_BRIDGE_PCI, 8, quirk_cmd_compl);
DECLARE_PCI_FIXUP_CLASS_EARLY(PCI_VENDOR_ID_QCOM, 0x0400,
			      PCI_CLASS_BRIDGE_PCI, 8, quirk_cmd_compl);
DECLARE_PCI_FIXUP_CLASS_EARLY(PCI_VENDOR_ID_QCOM, 0x0401,
			      PCI_CLASS_BRIDGE_PCI, 8, quirk_cmd_compl);
DECLARE_PCI_FIXUP_CLASS_EARLY(PCI_VENDOR_ID_HXT, 0x0401,
			      PCI_CLASS_BRIDGE_PCI, 8, quirk_cmd_compl);
```

The fixup sets [`broken_cmd_compl`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L521) when [`PCI_EXP_SLTCAP_HPC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L604) is set and [`PCI_EXP_SLTCAP_NCCS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L608) is clear, which is a hotplug port that writers would wait on. Each [`DECLARE_PCI_FIXUP_CLASS_EARLY`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2439) line names a vendor and a device or `PCI_ANY_ID`, the PCI-to-PCI bridge class and a class shift of 8. The member exists only with [`CONFIG_HOTPLUG_PCI_PCIE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L16) set, and with the option unset neither the member nor pciehp is built.

The erratum test in [`pcie_do_write_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L157) compares the Control bits of Slot Control before and after the merge, and the figure separates them from the enables.

```text
    Slot Control, the Control bits the erratum test compares and the Enable bits it ignores
    ───────────────────────────────────────────────────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x18  │·│I│A│l│E│P│PIC│AIC│h│c│p│m│f│b│
          └─┴─┴─┴─┴─┴─┴───┴───┴─┴─┴─┴─┴─┴─┘
                  ├───────────┤  Control bits, CC_ERRATUM_MASK (11:6)
                              ├───────────┤  Enable bits (5:0), with l at bit 12

    E = PCI_EXP_SLTCTL_EIC (Electromechanical Interlock Control)   P = PCI_EXP_SLTCTL_PCC (Power Controller Control)
    PIC = PCI_EXP_SLTCTL_PIC (Power Indicator Control, 9:8)
    AIC = PCI_EXP_SLTCTL_AIC (Attention Indicator Control, 7:6)
    h = PCI_EXP_SLTCTL_HPIE (Hot-Plug Interrupt Enable)
    c = PCI_EXP_SLTCTL_CCIE (Command Completed Interrupt Enable)
    p = PCI_EXP_SLTCTL_PDCE (Presence Detect Changed Enable)       m = PCI_EXP_SLTCTL_MRLSCE (MRL Sensor Changed Enable)
    f = PCI_EXP_SLTCTL_PFDE (Power Fault Detected Enable)
    b = PCI_EXP_SLTCTL_ABPE (Attention Button Pressed Enable)
    l = PCI_EXP_SLTCTL_DLLSCE (Data Link Layer State Changed Enable, bit 12)
    I = PCI_EXP_SLTCTL_IBPD_DISABLE (bit 14), A = PCI_EXP_SLTCTL_ASPL_DISABLE (bit 13), · = bit 15, unnamed
    a command that changes only Enable bits leaves the Control bits equal, and the erratum test clears cmd_busy
```

[`CC_ERRATUM_MASK`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L152) is defined just above the function, and it covers bits 11 to 6, the interlock, power and both indicator fields that the comment calls the "Control" bits.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:152 */
#define CC_ERRATUM_MASK		(PCI_EXP_SLTCTL_PCC |	\
				 PCI_EXP_SLTCTL_PIC |	\
				 PCI_EXP_SLTCTL_AIC |	\
				 PCI_EXP_SLTCTL_EIC)
```

The test in [`pcie_do_write_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L157) that uses the mask clears [`cmd_busy`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L101) right after the write when the masked bits did not change, and the lines are shown again with the function's start.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:157 */
static void pcie_do_write_cmd(struct controller *ctrl, u16 cmd,
			      u16 mask, bool wait)
	... /* 33 lines, to :192 */
	if (pdev->broken_cmd_compl &&
	    (slot_ctrl_orig & CC_ERRATUM_MASK) == (slot_ctrl & CC_ERRATUM_MASK))
		ctrl->cmd_busy = 0;
```

A command that changed enable bits alone on such a port is treated as complete at once, mark ⑤ of the strip, and the next writer goes ahead without waiting. A command that changed a Control bit waits as on any other port, and the boot message of [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) adds "(with Cmd Compl erratum)" for a port with the flag set.

So far, the controller holds the slot's features in [`slot_cap`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L95), and a command has passed through the lock, the merge and the write, then the wait that ends at Command Completed, at the deadline or at once on ports that cannot report completion. That is the strip from mark ① to mark ⑦, and the next subsections apply the command to the indicator and power fields.

### Indicator commands go out without waiting for completion

A slot can carry two indicators, an Attention Indicator and a Power Indicator, and Slot Control holds a two-bit field for each, with values for on, blink and off. pciehp changes them through [`pciehp_set_indicators()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L513), which builds one command for either field or both, and user space reaches the attention field through the slot's attention file. The table gives the field values that the Slot Control excerpt above defines and the numbers the attention file uses for them.

| State | Power Indicator value | Attention Indicator value | Attention file value |
|---|---|---|---|
| on | [`PCI_EXP_SLTCTL_PWR_IND_ON`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L623), 0x0100 | [`PCI_EXP_SLTCTL_ATTN_IND_ON`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L619), 0x0040 | 1 |
| blink | [`PCI_EXP_SLTCTL_PWR_IND_BLINK`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L624), 0x0200 | [`PCI_EXP_SLTCTL_ATTN_IND_BLINK`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L620), 0x0080 | 2 |
| off | [`PCI_EXP_SLTCTL_PWR_IND_OFF`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L625), 0x0300 | [`PCI_EXP_SLTCTL_ATTN_IND_OFF`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L621), 0x00c0 | 0 |
| unchanged | [`INDICATOR_NOOP`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L181) | [`INDICATOR_NOOP`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L181) | none |

[`pciehp_set_indicators()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L513) takes a Power Indicator value in `pwr` and an Attention Indicator value in `attn`, both parameters, and its comment lists the values each accepts. Read it for the two conditions that let a field into the command.

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

Each field joins the command when the slot has that indicator, by [`PWR_LED()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L160) or [`ATTN_LED()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L159) on the copy of Slot Capabilities, and when its argument is not [`INDICATOR_NOOP`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L181), and the field's mask joins with it, so an absent or unchanged indicator keeps its bits. The command goes out through [`pcie_write_cmd_nowait()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L219), and a call that leaves both fields out writes nothing. The debug line prints the configuration offset of Slot Control, the capability's base plus [`PCI_EXP_SLTCTL`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L610), and the command value.

Reading the attention field back goes the other way. [`pciehp_get_attention_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L365) is the attention file's read operation when the slot has an Attention Indicator, and it reads Slot Control and decodes the field.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:365 */
int pciehp_get_attention_status(struct hotplug_slot *hotplug_slot, u8 *status)
{
	struct controller *ctrl = to_ctrl(hotplug_slot);
	struct pci_dev *pdev = ctrl_dev(ctrl);
	u16 slot_ctrl;

	pci_config_pm_runtime_get(pdev);
	pcie_capability_read_word(pdev, PCI_EXP_SLTCTL, &slot_ctrl);
	pci_config_pm_runtime_put(pdev);
	ctrl_dbg(ctrl, "%s: SLOTCTRL %x, value read %x\n", __func__,
		 pci_pcie_cap(ctrl->pcie->port) + PCI_EXP_SLTCTL, slot_ctrl);

	switch (slot_ctrl & PCI_EXP_SLTCTL_AIC) {
	case PCI_EXP_SLTCTL_ATTN_IND_ON:
		*status = 1;	/* On */
		break;
	case PCI_EXP_SLTCTL_ATTN_IND_BLINK:
		*status = 2;	/* Blink */
		break;
	case PCI_EXP_SLTCTL_ATTN_IND_OFF:
		*status = 0;	/* Off */
		break;
	default:
		*status = 0xFF;
		break;
	}

	return 0;
}
```

The decode maps the field onto the attention file's numbers of the table and returns 0xFF for the pattern 00, which [`pci_regs.h`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h) does not name. [`pci_config_pm_runtime_get()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2868) and [`pci_config_pm_runtime_put()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2890) bracket the read so that a port in D3cold is resumed for it, as the slot files subsection shows.

Some platforms use the four indicator bits for indicators of their own and let user space drive them, as the message of commit commit [576243b3f9ea](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=576243b3f9eaa47ab568ac49574b3a095c2365f1) ("PCI: pciehp: Allow exclusive userspace control of indicators") explains. For a port with [`hotplug_user_indicators`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L425) set, [`init_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L51) installs a raw pair of operations that treats both fields as one four-bit value, and [`pciehp_get_raw_indicator_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L351) is the reading half.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:351 */
int pciehp_get_raw_indicator_status(struct hotplug_slot *hotplug_slot,
				    u8 *status)
{
	struct controller *ctrl = to_ctrl(hotplug_slot);
	struct pci_dev *pdev = ctrl_dev(ctrl);
	u16 slot_ctrl;

	pci_config_pm_runtime_get(pdev);
	pcie_capability_read_word(pdev, PCI_EXP_SLTCTL, &slot_ctrl);
	pci_config_pm_runtime_put(pdev);
	*status = (slot_ctrl & (PCI_EXP_SLTCTL_AIC | PCI_EXP_SLTCTL_PIC)) >> 6;
	return 0;
}
```

The read masks [`PCI_EXP_SLTCTL_AIC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L617) and [`PCI_EXP_SLTCTL_PIC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L622) together and shifts them down by 6, so bits 9 to 6 of Slot Control become bits 3 to 0 of the value. [`pciehp_set_raw_indicator_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L483) is the writing half.

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

`FIELD_PREP()` shifts the four-bit `status`, a parameter, up into the same field, and the command goes out without waiting under the joint mask. Commit commit [5560a612c20d](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=5560a612c20d3daacbf5da7913deefa5c31742f4) ("PCI: pciehp: Retain Power Indicator bits for userspace indicators") made the mask cover both fields again after a conversion had cut it to the attention field. The figure lines up the two views of the four bits.

```text
    The raw attention value and Slot Control bits 9:6 are one field seen twice
    ──────────────────────────────────────────────────────────────────────────
    the rulers share one scale: a column pair is one bit on both

                             3   2   1   0
    raw value (u8)         ├───────┼───────┤
                             PIC     AIC
                             │           ▲
         set: FIELD_PREP()   │ << 6      │ >> 6   get: (slot_ctrl & (AIC | PIC))
                             ▼           │
                     15:10   9   8   7   6   5:0
    Slot Control   ├───────┼───────┼───────┼───────┤
                     kept    PIC     AIC     kept

    pciehp_set_raw_indicator_status() writes the four bits with mask AIC | PIC and no wait;
    pciehp_get_raw_indicator_status() reads Slot Control and shifts the same four bits down;
    pciehp_set_indicators() writes PIC and AIC as two fields, each one only when its LED is present
    and its argument is not INDICATOR_NOOP
```

The raw pair and [`pciehp_set_indicators()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L513) write the same two fields, and probe cleared the indicator presence bits for such a port, so pciehp's own indicator commands leave these bits alone. Indicator commands go out without waiting, and the wait they skip falls on the next command, which on the add and remove paths is a power command.

### Power commands wait for the port to complete them

A slot with a Power Controller has its power switched by [`PCI_EXP_SLTCTL_PCC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L626), and pciehp issues both directions through [`pcie_write_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L213), so the caller continues after the port completed the command or the deadline passed. Power on also clears a power fault left from an earlier attempt and re-enables the link, which the add path needs before it checks for a device. [`pciehp_power_on_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L534) is called by the add path when [`POWER_CTRL()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L157) holds; read it for the order of the fault clear, the command and the link enable.

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

Power Fault Detected is written back to clear it when set, and [`power_fault_detected`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L106) is reset, the marks ➊ and ➋ of the fault figure in the next subsection. The command writes [`PCI_EXP_SLTCTL_PWR_ON`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L627), value 0, under the mask [`PCI_EXP_SLTCTL_PCC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L626), the merge drawn earlier. [`pciehp_link_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L346) then clears Link Disable, and its result is the function's result.

[`pciehp_link_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L346) and the helper under it write Link Control through a clear-and-set accessor, which changes the masked bits and keeps the rest.

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

static int pciehp_link_enable(struct controller *ctrl)
{
	return __pciehp_link_set(ctrl, true);
}
```

With `enable`, its parameter, true, [`__pciehp_link_set()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L335) clears [`PCI_EXP_LNKCTL_LD`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L569) and keeps the other Link Control bits. It returns 0 in both directions, so at v7.2 the error message of power on never prints. [`pciehp_power_off_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L559) is the inverse, a waiting command with [`PCI_EXP_SLTCTL_PWR_OFF`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L628), value 1, followed by a debug line.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:559 */
void pciehp_power_off_slot(struct controller *ctrl)
{
	pcie_write_cmd(ctrl, PCI_EXP_SLTCTL_PWR_OFF, PCI_EXP_SLTCTL_PCC);
	ctrl_dbg(ctrl, "%s: SLOTCTRL %x write cmd %x\n", __func__,
		 pci_pcie_cap(ctrl->pcie->port) + PCI_EXP_SLTCTL,
		 PCI_EXP_SLTCTL_PWR_OFF);
}
```

Power off leaves Link Control and the fault record as they are. The remove and error paths reach it through [`set_slot_off()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L34), which shows what a caller does once the command has completed.

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

After the command the caller sleeps one second, the delay the comment asks for before anything relies on the power being gone, and then turns the Power Indicator off and the Attention Indicator on. [`pciehp_get_power_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L395) reads the power state back by decoding [`PCI_EXP_SLTCTL_PCC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L626) from Slot Control.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:395 */
void pciehp_get_power_status(struct controller *ctrl, u8 *status)
{
	struct pci_dev *pdev = ctrl_dev(ctrl);
	u16 slot_ctrl;

	pcie_capability_read_word(pdev, PCI_EXP_SLTCTL, &slot_ctrl);
	ctrl_dbg(ctrl, "%s: SLOTCTRL %x value read %x\n", __func__,
		 pci_pcie_cap(ctrl->pcie->port) + PCI_EXP_SLTCTL, slot_ctrl);

	switch (slot_ctrl & PCI_EXP_SLTCTL_PCC) {
	case PCI_EXP_SLTCTL_PWR_ON:
		*status = 1;	/* On */
		break;
	case PCI_EXP_SLTCTL_PWR_OFF:
		*status = 0;	/* Off */
		break;
	default:
		*status = 0xFF;
		break;
	}
}
```

The result is 1 for on and 0 for off, and the 0xFF branch cannot run, since the masked value is either [`PCI_EXP_SLTCTL_PWR_ON`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L627) or [`PCI_EXP_SLTCTL_PWR_OFF`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L628). Probe uses both functions on a slot that firmware left powered with nothing in it; the stage below starts at [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) and folds to that check.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:1006 */
struct controller *pcie_init(struct pcie_device *dev)
{
	... /* 68 lines, to :1076 */
	/*
	 * If empty slot's power status is on, turn power off.  The IRQ isn't
	 * requested yet, so avoid triggering a notification with this command.
	 */
	if (POWER_CTRL(ctrl)) {
		pciehp_get_power_status(ctrl, &poweron);
		if (!pciehp_card_present_or_link_active(ctrl) && poweron) {
			pcie_disable_notification(ctrl);
			pciehp_power_off_slot(ctrl);
		}
	}
```

When [`pciehp_card_present_or_link_active()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L463) finds the slot empty and power is on, [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) disables notifications before it switches power off, because, as the comment says, the interrupt is not requested yet and the command must not trigger a notification. Power commands thus end complete or timed out before their callers continue, and a power fault that the port reports is the next subject.

### A power fault is recorded in Slot Status and the controller

When the port detects a power fault it sets Power Fault Detected, an event bit, and pciehp keeps its own record in [`power_fault_detected`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L106). The handler's comment gives the purpose of the record, which is to report a fault once until something handles it, and the add path consults both after power on. [`pciehp_query_power_fault()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L474) reads the hardware half of the record.

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

It returns 1 while Power Fault Detected is set and leaves the bit set. [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623) writes the software half, and the stage below shows how it drops a fault already reported and clears the event bits it reports.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:623 */
static irqreturn_t pciehp_isr(int irq, void *dev_id)
{
	... /* 41 lines, to :666 */
	status &= PCI_EXP_SLTSTA_ABP | PCI_EXP_SLTSTA_PFD |
		  PCI_EXP_SLTSTA_PDC | PCI_EXP_SLTSTA_CC |
		  PCI_EXP_SLTSTA_DLLSC;

	/*
	 * If we've already reported a power fault, don't report it again
	 * until we've done something to handle it.
	 */
	if (ctrl->power_fault_detected)
		status &= ~PCI_EXP_SLTSTA_PFD;
	else if (status & PCI_EXP_SLTSTA_PFD)
		ctrl->power_fault_detected = true;

	events |= status;
	if (!events) {
		if (parent)
			pm_runtime_put(parent);
		return IRQ_NONE;
	}

	if (status) {
		pcie_capability_write_word(pdev, PCI_EXP_SLTSTA, status);

		/*
		 * In MSI mode, all event bits must be zero before the port
		 * will send a new interrupt (PCIe Base Spec r5.0 sec 6.7.3.4).
		 * So re-read the Slot Status register in case a bit was set
		 * between read and write.
		 */
		if (pci_dev_msi_enabled(pdev) && !pciehp_poll_mode)
			goto read_status;
	}
```

The handler keeps the event bits of Slot Status and drops Power Fault Detected from them when [`power_fault_detected`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L106) is already set, so a repeated fault stays set in the register and goes unreported. A first fault sets the flag, and the write back clears each event bit the handler kept, Power Fault Detected among them. With [`CONFIG_PCI_MSI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L44) set, the port using MSI and [`pciehp_poll_mode`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L34) clear, the handler reads Slot Status again after the write, for the rule its comment cites that a port sends no new interrupt while an event bit is set.

The figure draws the pair of the register bit and the flag and the actions that move it.

```text
    A power fault is recorded twice, in Slot Status and in the controller
    ─────────────────────────────────────────────────────────────────────

    ┌────────────────────────────────┐   the port detects a fault   ┌────────────────────────────────┐
    │ clear                          │─────────────────────────────▶│ latched, not yet reported      │
    │ PFD 0, power_fault_detected 0  │◀─────────────────────────────│ PFD 1, power_fault_detected 0  │
    └───────────┬────────────────────┘   ➊ ➋ power on               └──────────────┬─────────────────┘
                ▲                                                                  │
                │                                                                  │ ➌ ➍ the handler
                │                                                                  │       reports it
                │                                                                  ▼
                │                                                   ┌────────────────────────────────┐
                │                 ➊ ➋ power on                      │ reported                       │
                ├───────────────────────────────────────────────────│ PFD 0, power_fault_detected 1  │
                │                                                   └──────────────┬─────────────────┘
                │                                                                  │
                │                                                                  │ another fault
                │                                                                  │
                │                                                                  ▼
                │                                                   ┌────────────────────────────────┐
                │                 ➊ ➋ power on                      │ latched again, masked          │
                └───────────────────────────────────────────────────│ PFD 1, power_fault_detected 1  │
                                                                    └────────────────────────────────┘

    ➊ pciehp_power_on_slot  pciehp_hpc.c:543  writes PFD back to Slot Status, clearing it
    ➋ pciehp_power_on_slot  :545  resets power_fault_detected to zero before powering on
    ➌ pciehp_isr            :677  sets power_fault_detected on the first fault it sees
    ➍ pciehp_isr            :687  writes the reported event bits back, clearing PFD
    in the masked state the handler leaves PFD set and reports nothing more until power on
    pciehp_query_power_fault() reads PFD, the first half of the pair
```

➊ [`pciehp_power_on_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L534) writes Power Fault Detected back to clear it. ➋ `pciehp_power_on_slot()` resets [`power_fault_detected`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L106) to zero. ➌ [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623) sets the flag when it sees a first fault. ➍ `pciehp_isr()` writes the reported event bits back, which clears Power Fault Detected.

The pair returns to clear through power on alone, and the add path tests both halves after it has switched the slot on, as the link check subsection shows.

### Presence comes from Slot Status or from the link

Whether a card is in the slot decides whether pciehp brings the slot up or down, and the port reports it in two places, Presence Detect State in Slot Status and Data Link Layer Link Active in Link Status. pciehp reads each with a helper of its own and combines them for the callers that ask whether the slot is occupied. Slot Status is defined beside Slot Control in [`pci_regs.h`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h), and the excerpt is the register's block.

```c
/* include/uapi/linux/pci_regs.h:633 */
#define PCI_EXP_SLTSTA		0x1a	/* Slot Status */
#define  PCI_EXP_SLTSTA_ABP	0x0001	/* Attention Button Pressed */
#define  PCI_EXP_SLTSTA_PFD	0x0002	/* Power Fault Detected */
#define  PCI_EXP_SLTSTA_MRLSC	0x0004	/* MRL Sensor Changed */
#define  PCI_EXP_SLTSTA_PDC	0x0008	/* Presence Detect Changed */
#define  PCI_EXP_SLTSTA_CC	0x0010	/* Command Completed */
#define  PCI_EXP_SLTSTA_MRLSS	0x0020	/* MRL Sensor State */
#define  PCI_EXP_SLTSTA_PDS	0x0040	/* Presence Detect State */
#define  PCI_EXP_SLTSTA_EIS	0x0080	/* Electromechanical Interlock Status */
#define  PCI_EXP_SLTSTA_DLLSC	0x0100	/* Data Link Layer State Changed */
```

[`PCI_EXP_SLTSTA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L633) is 0x1a, and its masks divide into event bits, cleared by writing 1, and state bits, as the Slot Status drawing above marks. This subsection reads the state bits [`PCI_EXP_SLTSTA_PDS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L640) and [`PCI_EXP_SLTSTA_MRLSS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L639), and [`PCI_EXP_SLTSTA_DLLSC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L642) is the event bit that a change of the link sets.

pciehp reads Slot Status through [`pcie_capability_read_word()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/access.c#L427), which also defines what a function without a slot returns; read it for the zeroed result of a failed read and for the hardwired presence.

```c
/* drivers/pci/access.c:427 */
int pcie_capability_read_word(struct pci_dev *dev, int pos, u16 *val)
{
	int ret;

	*val = 0;
	if (pos & 1)
		return PCIBIOS_BAD_REGISTER_NUMBER;

	if (pcie_capability_reg_implemented(dev, pos)) {
		ret = pci_read_config_word(dev, pci_pcie_cap(dev) + pos, val);
		/*
		 * Reset *val to 0 if pci_read_config_word() fails; it may
		 * have been written as 0xFFFF (PCI_ERROR_RESPONSE) if the
		 * config read failed on PCI.
		 */
		if (ret)
			*val = 0;
		return ret;
	}

	/*
	 * For Functions that do not implement the Slot Capabilities,
	 * Slot Status, and Slot Control registers, these spaces must
	 * be hardwired to 0b, with the exception of the Presence Detect
	 * State bit in the Slot Status register of Downstream Ports,
	 * which must be hardwired to 1b.  (PCIe Base Spec 3.0, sec 7.8)
	 */
	if (pci_is_pcie(dev) && pcie_downstream_port(dev) &&
	    pos == PCI_EXP_SLTSTA)
		*val = PCI_EXP_SLTSTA_PDS;
```

A failed configuration read returns its error with the result set to 0. A downstream port without a slot reads Presence Detect State as set, by the comment's citation of the specification. The other failure the helpers test is a read that completes with all ones, which [`PCI_POSSIBLE_ERROR()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L175) recognizes by comparing with [`PCI_ERROR_RESPONSE`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L173).

```c
/* include/linux/pci.h:168 */
/*
 * Reading from a device that doesn't respond typically returns ~0.  A
 * successful read from a device may also return ~0, so you need additional
 * information to reliably identify errors.
 */
#define PCI_ERROR_RESPONSE		(~0ULL)
#define PCI_SET_ERROR_RESPONSE(val)	(*(val) = ((typeof(*(val))) PCI_ERROR_RESPONSE))
#define PCI_POSSIBLE_ERROR(val)		((val) == ((typeof(val)) PCI_ERROR_RESPONSE))
```

The comment states the limit of the test, that a working device can return all ones too, so the helpers treat it as a port that has gone. [`pciehp_card_present()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L438) answers from Presence Detect State alone.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:426 */
/**
 * pciehp_card_present() - Is the card present
 * @ctrl: PCIe hotplug controller
 *
 * Function checks whether the card is currently present in the slot and
 * in that case returns true. Note it is possible that the card is
 * removed immediately after the check so the caller may need to take
 * this into account.
 *
 * If the hotplug controller itself is not available anymore returns
 * %-ENODEV.
 */
int pciehp_card_present(struct controller *ctrl)
{
	struct pci_dev *pdev = ctrl_dev(ctrl);
	u16 slot_status;
	int ret;

	ret = pcie_capability_read_word(pdev, PCI_EXP_SLTSTA, &slot_status);
	if (ret == PCIBIOS_DEVICE_NOT_FOUND || PCI_POSSIBLE_ERROR(slot_status))
		return -ENODEV;

	return !!(slot_status & PCI_EXP_SLTSTA_PDS);
}
```

It returns -ENODEV when the read fails with [`PCIBIOS_DEVICE_NOT_FOUND`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L841) or returns all ones, and otherwise 1 or 0 from [`PCI_EXP_SLTSTA_PDS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L640). [`pciehp_check_link_active()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L235) answers from the link, reading Data Link Layer Link Active in Link Status.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:224 */
/**
 * pciehp_check_link_active() - Is the link active
 * @ctrl: PCIe hotplug controller
 *
 * Check whether the downstream link is currently active. Note it is
 * possible that the card is removed immediately after this so the
 * caller may need to take it into account.
 *
 * If the hotplug controller itself is not available anymore returns
 * %-ENODEV.
 */
int pciehp_check_link_active(struct controller *ctrl)
{
	struct pci_dev *pdev = ctrl_dev(ctrl);
	u16 lnk_status;
	int ret;

	ret = pcie_capability_read_word(pdev, PCI_EXP_LNKSTA, &lnk_status);
	if (ret == PCIBIOS_DEVICE_NOT_FOUND || PCI_POSSIBLE_ERROR(lnk_status))
		return -ENODEV;

	ret = !!(lnk_status & PCI_EXP_LNKSTA_DLLLA);
	ctrl_dbg(ctrl, "%s: lnk_status = %x\n", __func__, lnk_status);

	return ret;
}
```

It has the same three results, -ENODEV for a port that does not answer, and its debug line prints the whole of Link Status. [`pciehp_card_present_or_link_active()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L463) combines the two for callers that ask whether the slot is occupied, and its comment gives the reason for the second source.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:451 */
/**
 * pciehp_card_present_or_link_active() - whether given slot is occupied
 * @ctrl: PCIe hotplug controller
 *
 * Unlike pciehp_card_present(), which determines presence solely from the
 * Presence Detect State bit, this helper also returns true if the Link Active
 * bit is set.  This is a concession to broken hotplug ports which hardwire
 * Presence Detect State to zero, such as Wilocity's [1ae9:0200].
 *
 * Returns: %1 if the slot is occupied and %0 if it is not. If the hotplug
 *	    port is not present anymore returns %-ENODEV.
 */
int pciehp_card_present_or_link_active(struct controller *ctrl)
{
	int ret;

	ret = pciehp_card_present(ctrl);
	if (ret)
		return ret;

	return pciehp_check_link_active(ctrl);
}
```

Presence Detect State decides when it reads 1 or the port has gone, and the link decides when it reads 0, because, as the comment says, some broken ports hardwire Presence Detect State to zero; commit commit [80696f991424](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=80696f991424d05a784c0cf9c314ac09ac280406) ("PCI: pciehp: Tolerate Presence Detect hardwired to zero") added it. The event handler of the state machine asks the two questions apart, since it reports a card and a link in separate messages, and the stage below starts at [`pciehp_handle_presence_or_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L232) and folds to them.

```c
/* drivers/pci/hotplug/pciehp_ctrl.c:232 */
void pciehp_handle_presence_or_link_change(struct controller *ctrl, u32 events)
{
	... /* 35 lines, to :269 */
	/* Turn the slot on if it's occupied or link is up */
	mutex_lock(&ctrl->state_lock);
	present = pciehp_card_present(ctrl);
	link_active = pciehp_check_link_active(ctrl);
```

The handler takes both answers under [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110) and decides from them whether to bring the slot up. Presence Detect State is itself a combination, the OR of the in-band and the out-of-band presence signals according to the message of commit commit [202853595e53](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=202853595e53f981c86656c49fc1cc1e3620f558) ("PCI: pciehp: Disable in-band presence detect when possible"), and a port that supports In-band PD Disable can drop the in-band signal. [`PCI_EXP_SLTCAP2`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L716) holds the bit that says so.

```c
/* include/uapi/linux/pci_regs.h:716 */
#define PCI_EXP_SLTCAP2		0x34	/* Slot Capabilities 2 */
#define  PCI_EXP_SLTCAP2_IBPD	0x00000001 /* In-band PD Disable Supported */
```

[`PCI_EXP_SLTCAP2_IBPD`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L717) is bit 0 of the register at 0x34 and the one bit of Slot Capabilities 2 that [`pci_regs.h`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h) names. Probe reads it and turns in-band detection off by command when it is set; the stage below also clears stale Slot Status events and prints the slot's capabilities.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:1006 */
struct controller *pcie_init(struct pcie_device *dev)
{
	... /* 37 lines, to :1045 */
	pcie_capability_read_dword(pdev, PCI_EXP_SLTCAP2, &slot_cap2);
	if (slot_cap2 & PCI_EXP_SLTCAP2_IBPD) {
		pcie_write_cmd_nowait(ctrl, PCI_EXP_SLTCTL_IBPD_DISABLE,
				      PCI_EXP_SLTCTL_IBPD_DISABLE);
		ctrl->inband_presence_disabled = 1;
	}

	if (dmi_first_match(inband_presence_disabled_dmi_table))
		ctrl->inband_presence_disabled = 1;

	/* Clear all remaining event bits in Slot Status register. */
	pcie_capability_write_word(pdev, PCI_EXP_SLTSTA,
		PCI_EXP_SLTSTA_ABP | PCI_EXP_SLTSTA_PFD |
		PCI_EXP_SLTSTA_MRLSC | PCI_EXP_SLTSTA_CC |
		PCI_EXP_SLTSTA_DLLSC | PCI_EXP_SLTSTA_PDC);

	ctrl_info(ctrl, "Slot #%d AttnBtn%c PwrCtrl%c MRL%c AttnInd%c PwrInd%c HotPlug%c Surprise%c Interlock%c NoCompl%c IbPresDis%c LLActRep%c%s\n",
		FIELD_GET(PCI_EXP_SLTCAP_PSN, slot_cap),
		FLAG(slot_cap, PCI_EXP_SLTCAP_ABP),
		FLAG(slot_cap, PCI_EXP_SLTCAP_PCP),
		FLAG(slot_cap, PCI_EXP_SLTCAP_MRLSP),
		FLAG(slot_cap, PCI_EXP_SLTCAP_AIP),
		FLAG(slot_cap, PCI_EXP_SLTCAP_PIP),
		FLAG(slot_cap, PCI_EXP_SLTCAP_HPC),
		FLAG(slot_cap, PCI_EXP_SLTCAP_HPS),
		FLAG(slot_cap, PCI_EXP_SLTCAP_EIP),
		FLAG(slot_cap, PCI_EXP_SLTCAP_NCCS),
		FLAG(slot_cap2, PCI_EXP_SLTCAP2_IBPD),
		FLAG(pdev->link_active_reporting, true),
		pdev->broken_cmd_compl ? " (with Cmd Compl erratum)" : "");
```

A port with [`PCI_EXP_SLTCAP2_IBPD`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L717) gets [`PCI_EXP_SLTCTL_IBPD_DISABLE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L632) through [`pcie_write_cmd_nowait()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L219) and has [`inband_presence_disabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L96) set. A DMI match sets the flag without the command, and its table, [`inband_presence_disabled_dmi_table`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L31), is a list of platforms that this page leaves out as vendor-specific. The write to Slot Status then clears six event bits, [`PCI_EXP_SLTSTA_DLLSC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L642) among them, and the info line reports each capability bit as + or -. The figure joins the two sources of the answer and the bit that gates one of them.

```text
    Two register bits feed the answer to whether a slot is occupied
    ───────────────────────────────────────────────────────────────

    ┌────────────────────────┐  gated by IBPD Disable
    │ in-band presence       │───────┐
    └────────────────────────┘       │          ┌──────────────────────┐ PDS first
                                     ├─────────▶│ Slot Status PDS      │────────────┐
    ┌────────────────────────┐       │          └──────────────────────┘            │      ┌───────────────────────┐
    │ out-of-band presence   │───────┘                                              │      │ slot occupied         │
    └────────────────────────┘                                                      ├─────▶│ 1, 0, or -ENODEV      │
                                                                                    │      │ when the port is gone │
                                                                                    │      └───────────────────────┘
    ┌────────────────────────┐                  ┌──────────────────────┐            │
    │ the link is active     │─────────────────▶│ Link Status DLLLA    │────────────┘
    └────────────────────────┘                  └──────────────────────┘ then DLLLA


    PDS is the OR of the two presence sources, and the out-of-band source alone once IBPD Disable is set
    pciehp_card_present() reads PDS and pciehp_check_link_active() reads DLLLA;
    pciehp_card_present_or_link_active() returns the first answer that is not zero
```

With in-band detection off, Presence Detect State follows the out-of-band signal alone, and the link check reads [`inband_presence_disabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L96) to wait for it. Slot Status carries one more state bit this page uses, MRL Sensor State, which [`pciehp_get_latch_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L417) reads to tell whether the slot's retention latch is open.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:417 */
void pciehp_get_latch_status(struct controller *ctrl, u8 *status)
{
	struct pci_dev *pdev = ctrl_dev(ctrl);
	u16 slot_status;

	pcie_capability_read_word(pdev, PCI_EXP_SLTSTA, &slot_status);
	*status = !!(slot_status & PCI_EXP_SLTSTA_MRLSS);
}
```

It returns 1 for an open latch and has no error path, and [`MRL_SENS()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L158) decides whether anything calls it. The enable path shows the latch read and the power read in use, refusing a slot whose latch is open and returning early for a slot already powered.

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

The enable path ends in [`board_added()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L62) when the latch is closed and the slot is off, so presence and latch are settled before power on, and the link check that follows power on is the next subject.

### The link check decides whether a powered slot holds a device

After power on, the add path still has to learn whether the link to the card trained and whether a function answers behind it, before it configures anything. [`pciehp_check_link_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L291) answers both questions with waits bounded by fixed timeouts, and the add path runs it between the indicator command and the power fault test. [`board_added()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L62) is the add path's function, and the stage below runs from its start through the power fault test.

```c
/* drivers/pci/hotplug/pciehp_ctrl.c:62 */
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
```

The slot is powered and its Power Indicator set to blink before the link check, and a failed check or a power fault in either half of the pair ends in [`set_slot_off()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L34), which the power subsection showed. The figure lays out the decisions [`pciehp_check_link_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L291) makes and the result each one leaves.

```text
    The checks a powered slot passes before its device is configured
    ────────────────────────────────────────────────────────────────

    ┌───────────────────────────────────────────┐  no          ┌─────────────────────────────────────┐
    │ link active within 1000 ms, polled        ├─────────────▶│ -1, "No link"                       │
    │ every 1 ms, then 100 ms more?             │              └─────────────────────────────────────┘
    └─────────────────────┬─────────────────────┘
                          │ yes
                          ▼
    ┌───────────────────────────────────────────┐
    │ in-band presence disabled: poll PDS       │
    │ every 10 ms for up to 1250 ms             │
    └─────────────────────┬─────────────────────┘
                          ▼
    ┌───────────────────────────────────────────┐
    │ device 00.0 answers a Vendor ID read,     │  yes: drop pending DLLSC and PDC
    │ retried every 20 ms for 1000 ms?          │
    └─────────────────────┬─────────────────────┘
                          │ either way
                          ▼
    ┌───────────────────────────────────────────┐  yes         ┌─────────────────────────────────────┐
    │ Link Training set, or no                  ├─────────────▶│ -1, "Cannot train link"             │
    │ Negotiated Link Width?                    │              └─────────────────────────────────────┘
    └─────────────────────┬─────────────────────┘
                          │ no
                          ▼
    ┌───────────────────────────────────────────┐
    │ record the link speed and flit mode,      │
    │ fire pcie_link_event                      │
    └─────────────────────┬─────────────────────┘
                          ▼
    ┌───────────────────────────────────────────┐  no          ┌─────────────────────────────────────┐
    │ was the device found?                     ├─────────────▶│ -1, "No device found"               │
    └─────────────────────┬─────────────────────┘              └─────────────────────────────────────┘
                          │ yes
                          ▼
                      returns 0

    a port without link_active_reporting sleeps 1100 ms in the first step and passes it
```

Three of the decisions end the check with -1 and a message, and the device test in the middle only records its answer, which the last decision reads after the link has been recorded. [`pciehp_check_link_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L291) is read in two pieces.

| Piece | Lines | Stage |
|---|---|---|
| Ⓐ | pciehp_hpc.c:291-312 | waits for the link and for presence, and asks whether function 00.0 answers |
| Ⓑ | pciehp_hpc.c:313-333 | tests Link Status, records the link and returns the verdict |

Piece Ⓐ of [`pciehp_check_link_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L291) waits for the link to come up, waits for presence when in-band detection is off, and looks for the function.

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

```

[`pcie_wait_for_link()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4678) reports false when the link did not come up, and the check fails with "No link". [`pcie_wait_for_presence()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L277) runs when [`inband_presence_disabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L96) is set and [`pci_bus_check_dev()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L251) asks whether function 00.0 of the bus behind the port answers. A function that answers removes [`PCI_EXP_SLTSTA_DLLSC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L642) and [`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637) from [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104), so the link and presence changes that this bring-up caused are not handled as new events.

Piece Ⓑ of [`pciehp_check_link_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L291) reads Link Status, records the link for the bus behind the port and returns the verdict.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:313 */
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

A link still in training, [`PCI_EXP_LNKSTA_LT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L591) set, or one with no negotiated width in [`PCI_EXP_LNKSTA_NLW`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L585) fails the check with "Cannot train link". Otherwise Link Status 2 is read and [`__pcie_update_link_speed()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L637) records the link with the reason [`PCIE_HOTPLUG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L634), and only then does a missing function fail the check with "No device found". [`__pcie_update_link_speed()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L637) is defined in [`drivers/pci/pci.h`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h), and it is where the link check fires a tracepoint.

```c
/* drivers/pci/pci.h:637 */
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

It stores the current speed and the Flit Mode Status in the [`struct pci_bus`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L702) behind the port and fires [`pcie_link_event`](https://elixir.bootlin.com/linux/v7.2/source/include/trace/events/pci.h#L81) with the reason, the negotiated width and the Link Status bits. The check thus leaves either -1 with a message, or 0 with the link recorded and a function known to answer, and the next subsection opens the waits it is built from.

### Bounded waits stand behind the link check

Each wait of the link check has a fixed bound, so a slot that never brings up a link or a device costs the add path a known delay. The link wait belongs to the PCI core and the other two to pciehp, and each polls a register or a configuration read in a loop. [`pcie_wait_for_link()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4678) fixes the delay after a successful wait at 100 ms.

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

[`pcie_wait_for_link_delay()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4629) does the work, with `active` true and `delay` 100 on this path, both of them parameters.

```c
/* drivers/pci/pci.c:4620 */

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
```

A port without [`link_active_reporting`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L507) cannot tell when its link is up, so the wait sleeps [`PCIE_LINK_RETRAIN_TIMEOUT_MS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L22) plus the delay and reports success. The constant is defined in [`drivers/pci/pci.h`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h).

```c
/* drivers/pci/pci.h:22 */
#define PCIE_LINK_RETRAIN_TIMEOUT_MS	1000
```

[`PCIE_LINK_RETRAIN_TIMEOUT_MS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L22) is 1000, so the sleep without link reporting is 1100 ms on this path. Otherwise it sleeps 20 ms, polls for Data Link Layer Link Active, and on a timeout hands the port to [`pcie_failed_link_retrain()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/quirks.c#L95), a PCI core quirk named here at the seam, before it gives up. The poll itself is [`pcie_wait_for_link_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4535), which reads Link Status every millisecond for up to [`PCIE_LINK_RETRAIN_TIMEOUT_MS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L22).

```c
/* drivers/pci/pci.c:4525 */

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
```

With its parameters `use_lt` false and `active` true, the loop waits for [`PCI_EXP_LNKSTA_DLLLA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L593) to be set, and it returns -ETIMEDOUT after 1000 ms. [`pcie_wait_for_presence()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L277) is the wait for presence that the link check adds when in-band detection is off.

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

It reads Slot Status every 10 ms for up to 1250 ms and returns as soon as [`PCI_EXP_SLTSTA_PDS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L640) is set, with no result, so a slot that never reports presence moves on after the bound. [`pci_bus_check_dev()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L251) is the search for function 00.0.

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

The loop asks for the Vendor ID with no wait of its own, sleeps 20 ms between tries and gives up after 1000 ms, and its debug line prints the number of tries when there was more than one.

So far, a slot has been powered by a waiting command, its fault record cleared, and its link and function checked under bounded waits, with the link recorded and the pending link and presence events dropped. The strip's fields have reached mark ⑦, and the resume marks remain, which the replacement check of the next subsection comes with.

### A replacement check compares cached identity with fresh reads

A card can be swapped while the system sleeps, and on resume the port still reports a card and a link, so presence alone cannot reveal the change. pciehp compares what the PCI core cached about function 00.0 when it enumerated the function with what that function reports now. The resume hook [`pciehp_resume_noirq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L288) runs the comparison, and it also makes the last two writes of the strip.

```c
/* drivers/pci/hotplug/pciehp_core.c:288 */
static int pciehp_resume_noirq(struct pcie_device *dev)
{
	struct controller *ctrl = get_service_data(dev);

	/* pci_restore_state() just wrote to the Slot Control register */
	ctrl->cmd_started = jiffies;
	ctrl->cmd_busy = true;

	/* clear spurious events from rediscovery of inserted card */
	if (ctrl->state == ON_STATE || ctrl->state == BLINKINGOFF_STATE) {
		pcie_clear_hotplug_events(ctrl);

		/*
		 * If hotplugged device was replaced with a different one
		 * during system sleep, mark the old device disconnected
		 * (to prevent its driver from accessing the new device)
		 * and synthesize a Presence Detect Changed event.
		 */
		if (pciehp_device_replaced(ctrl)) {
			ctrl_dbg(ctrl, "device replaced during system sleep\n");
			pci_walk_bus(ctrl->pcie->port->subordinate,
				     pci_dev_set_disconnected, NULL);
			pciehp_request(ctrl, PCI_EXP_SLTSTA_PDC);
		}
	}

	return 0;
}
```

The comment says that [`pci_restore_state()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L1826) of the PCI core, named here at the seam, has just written Slot Control, so the hook stamps [`cmd_started`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L100) and sets [`cmd_busy`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L101), marks ⑧ and ⑨ of the strip, and the next command waits for the restored one, the change commit commit [469e764c4a3c](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=469e764c4a3c7260b353b7bc1bd56c283cb001da) ("PCI: pciehp: Obey compulsory command delay after resume") made. For a slot that was on, the hook clears stale presence and link events and, when [`pciehp_device_replaced()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L567) says the card changed, marks the old devices disconnected and requests a Presence Detect Changed event. The hook is built with [`CONFIG_PM_SLEEP`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L140), and [`pciehp_device_replaced()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L567) does the comparison.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:567 */
bool pciehp_device_replaced(struct controller *ctrl)
{
	struct pci_dev *pdev __free(pci_dev_put) = NULL;
	u32 reg;

	if (pci_dev_is_disconnected(ctrl->pcie->port))
		return false;

	pdev = pci_get_slot(ctrl->pcie->port->subordinate, PCI_DEVFN(0, 0));
	if (!pdev)
		return true;

	if (pci_read_config_dword(pdev, PCI_VENDOR_ID, &reg) ||
	    reg != (pdev->vendor | (pdev->device << 16)) ||
	    pci_read_config_dword(pdev, PCI_CLASS_REVISION, &reg) ||
	    reg != (pdev->revision | (pdev->class << 8)))
		return true;

	if (pdev->hdr_type == PCI_HEADER_TYPE_NORMAL &&
	    (pci_read_config_dword(pdev, PCI_SUBSYSTEM_VENDOR_ID, &reg) ||
	     reg != (pdev->subsystem_vendor | (pdev->subsystem_device << 16))))
		return true;

	if (pci_get_dsn(pdev) != ctrl->dsn)
		return true;

	return false;
}
```

A port already marked disconnected answers false, and a missing function 00.0, a failed read or any difference answers true. The identity dwords are compared with [`vendor`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L362), [`device`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L363), [`revision`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L367) and [`class`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L366) packed as the header holds them, the subsystem dword only for a normal header, and the serial number with [`dsn`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L93). [`pci_get_dsn()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L555) reads that serial number from the Device Serial Number capability.

```c
/* drivers/pci/pci.c:546 */
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
```

A function without the capability gives 0, so two cards without it compare equal on this test and differ only through the header dwords. The figure sets the two sides of the comparison against each other.

```text
    The identity cached for function 00.0 against the identity it reports now
    ─────────────────────────────────────────────────────────────────────────

    cached when 00.0 was enumerated             read now from 00.0's configuration space
    ┌─────────────────────────────────────┐     ┌─────────────────────────────────────┐
    │ vendor | device << 16               │     │ dword at PCI_VENDOR_ID (0x00)       │
    │ revision | class << 8               │     │ dword at PCI_CLASS_REVISION (0x08)  │
    │ subsystem_vendor |                  │     │ dword at PCI_SUBSYSTEM_VENDOR_ID    │
    │   subsystem_device << 16            │     │   (0x2c), normal header only        │
    │ controller.dsn, kept at probe       │     │ pci_get_dsn(), the serial number    │
    │                                     │     │                                     │
    └──────────────────┬──────────────────┘     └──────────────────┬──────────────────┘
                       │                                           │
                       └──────────────────▶ equal? ◀───────────────┘
                                               │
                                               ▼
              true (replaced): no device at 00.0, a failed read or any difference
              false: the port is disconnected, or every pair is equal
```

The other caller of the comparison is the link change suppression path, which runs it after a recovery or a reset, named here at the seam with its call site.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:596 */
static void pciehp_ignore_link_change(struct controller *ctrl,
				      struct pci_dev *pdev, int irq,
				      u16 ignored_events)
{
	... /* 17 lines, to :617 */
	down_read_nested(&ctrl->reset_lock, ctrl->depth);
	if (!pciehp_check_link_active(ctrl) || pciehp_device_replaced(ctrl))
		pciehp_request(ctrl, ignored_events);
	up_read(&ctrl->reset_lock);
```

When the link is down or the card was replaced after the suppressed link change, [`pciehp_ignore_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L596) requests the ignored events again, so the state machine sees them. The replacement check thus turns a swapped card into a presence event, and the resume marks have set the controller up to wait for the restored Slot Control.

### Slot files reach the registers through the slot operations

User space sees a hotplug slot as a directory of files under `/sys/bus/pci/slots/`, created by the hotplug core, and reading or writing those files reaches pciehp through a [`struct hotplug_slot_ops`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L38). pciehp fills that struct at probe according to its copy of Slot Capabilities, so the files a slot shows follow from its features. The struct is defined in [`pci_hotplug.h`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h) with a comment for each operation.

```c
/* include/linux/pci_hotplug.h:17 */
/**
 * struct hotplug_slot_ops -the callbacks that the hotplug pci core can use
 * @enable_slot: Called when the user wants to enable a specific pci slot
 * @disable_slot: Called when the user wants to disable a specific pci slot
 * @set_attention_status: Called to set the specific slot's attention LED to
 * the specified value
 * @hardware_test: Called to run a specified hardware test on the specified
 * slot.
 * @get_power_status: Called to get the current power status of a slot.
 * @get_attention_status: Called to get the current attention status of a slot.
 * @get_latch_status: Called to get the current latch status of a slot.
 * @get_adapter_status: Called to get see if an adapter is present in the slot or not.
 * @reset_slot: Optional interface to allow override of a bus reset for the
 *	slot for cases where a secondary bus reset can result in spurious
 *	hotplug events or where a slot can be reset independent of the bus.
 *
 * The table of function pointers that is passed to the hotplug pci core by a
 * hotplug pci driver.  These functions are called by the hotplug pci core when
 * the user wants to do something to a specific slot (query it for information,
 * set an LED, enable / disable power, etc.)
 */
struct hotplug_slot_ops {
	int (*enable_slot)		(struct hotplug_slot *slot);
	int (*disable_slot)		(struct hotplug_slot *slot);
	int (*set_attention_status)	(struct hotplug_slot *slot, u8 value);
	int (*hardware_test)		(struct hotplug_slot *slot, u32 value);
	int (*get_power_status)		(struct hotplug_slot *slot, u8 *value);
	int (*get_attention_status)	(struct hotplug_slot *slot, u8 *value);
	int (*get_latch_status)		(struct hotplug_slot *slot, u8 *value);
	int (*get_adapter_status)	(struct hotplug_slot *slot, u8 *value);
	int (*reset_slot)		(struct hotplug_slot *slot, bool probe);
};
```

The operations this page covers are [`get_power_status`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L43), [`get_attention_status`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L44), [`set_attention_status`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L41), [`get_latch_status`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L45) and [`get_adapter_status`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L46). [`enable_slot`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L39), [`disable_slot`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L40) and [`reset_slot`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L47) belong to the state machine and the reset path, and [`hardware_test`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L42) stays unset in pciehp. [`init_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L51) fills the struct, and the stage below runs from its start to the registration of the slot.

```c
/* drivers/pci/hotplug/pciehp_core.c:51 */
static int init_slot(struct controller *ctrl)
{
	struct hotplug_slot_ops *ops;
	char name[SLOT_NAME_SIZE];
	int retval;

	/* Setup hotplug slot ops */
	ops = kzalloc_obj(*ops);
	if (!ops)
		return -ENOMEM;

	ops->enable_slot = pciehp_sysfs_enable_slot;
	ops->disable_slot = pciehp_sysfs_disable_slot;
	ops->get_power_status = get_power_status;
	ops->get_adapter_status = get_adapter_status;
	ops->reset_slot = pciehp_reset_slot;
	if (MRL_SENS(ctrl))
		ops->get_latch_status = get_latch_status;
	if (ATTN_LED(ctrl)) {
		ops->get_attention_status = pciehp_get_attention_status;
		ops->set_attention_status = set_attention_status;
	} else if (ctrl->pcie->port->hotplug_user_indicators) {
		ops->get_attention_status = pciehp_get_raw_indicator_status;
		ops->set_attention_status = pciehp_set_raw_indicator_status;
	}

	/* register this slot with the hotplug pci core */
	ctrl->hotplug_slot.ops = ops;
	snprintf(name, SLOT_NAME_SIZE, "%u", PSN(ctrl));

	retval = pci_hp_initialize(&ctrl->hotplug_slot,
				   ctrl->pcie->port->subordinate,
				   PCI_SLOT_ALL_DEVICES, name);
```

The power and adapter operations are installed for each slot, the latch operation when [`MRL_SENS()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L158) holds, and the attention pair when [`ATTN_LED()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L159) holds or, failing that, as the raw pair for a port with [`hotplug_user_indicators`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L425) set. [`PSN()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L162) gives the name the slot is registered with, the Physical Slot Number in decimal. The hotplug core decides whether a file exists by testing for the operations behind it.

```c
/* drivers/pci/hotplug/pci_hotplug_core.c:204 */
static bool has_power_file(struct hotplug_slot *slot)
{
	if ((slot->ops->enable_slot) ||
	    (slot->ops->disable_slot) ||
	    (slot->ops->get_power_status))
		return true;
	return false;
}

static bool has_attention_file(struct hotplug_slot *slot)
{
	if ((slot->ops->set_attention_status) ||
	    (slot->ops->get_attention_status))
		return true;
	return false;
}

static bool has_latch_file(struct hotplug_slot *slot)
{
	if (slot->ops->get_latch_status)
		return true;
	return false;
}

static bool has_adapter_file(struct hotplug_slot *slot)
{
	if (slot->ops->get_adapter_status)
		return true;
	return false;
}
```

[`fs_add_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L242) creates the files when the slot is registered, each after its test, and the stage below folds the link to the driver module.

```c
/* drivers/pci/hotplug/pci_hotplug_core.c:242 */
static int fs_add_slot(struct hotplug_slot *slot, struct pci_slot *pci_slot)
{
	... /* 13 lines, to :257 */
	if (has_power_file(slot)) {
		retval = sysfs_create_file(&pci_slot->kobj,
					   &hotplug_slot_attr_power.attr);
		if (retval)
			goto exit_power;
	}

	if (has_attention_file(slot)) {
		retval = sysfs_create_file(&pci_slot->kobj,
					   &hotplug_slot_attr_attention.attr);
		if (retval)
			goto exit_attention;
	}

	if (has_latch_file(slot)) {
		retval = sysfs_create_file(&pci_slot->kobj,
					   &hotplug_slot_attr_latch.attr);
		if (retval)
			goto exit_latch;
	}

	if (has_adapter_file(slot)) {
		retval = sysfs_create_file(&pci_slot->kobj,
					   &hotplug_slot_attr_presence.attr);
		if (retval)
			goto exit_adapter;
	}
```

A slot without an MRL sensor therefore has no latch file, and one with neither an Attention Indicator nor user indicators has no attention file. The core's readers are generated by [`GET_STATUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L40), one per status, each calling the operation when it is set and reporting 0 otherwise.

```c
/* drivers/pci/hotplug/pci_hotplug_core.c:39 */
/* Weee, fun with macros... */
#define GET_STATUS(name, type)	\
static int get_##name(struct hotplug_slot *slot, type *value)		\
{									\
	const struct hotplug_slot_ops *ops = slot->ops;			\
	int retval = 0;							\
	if (ops->get_##name)						\
		retval = ops->get_##name(slot, value);			\
	return retval;							\
}

GET_STATUS(power_status, u8)
GET_STATUS(attention_status, u8)
GET_STATUS(latch_status, u8)
GET_STATUS(adapter_status, u8)
```

The attention file's write is the one write to a slot file that this page follows, and [`attention_write_file()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L118) parses the text as a number and passes its low byte to the operation.

```c
/* drivers/pci/hotplug/pci_hotplug_core.c:118 */
static ssize_t attention_write_file(struct pci_slot *pci_slot, const char *buf,
				    size_t count)
{
	struct hotplug_slot *slot = pci_slot->hotplug;
	const struct hotplug_slot_ops *ops = slot->ops;
	unsigned long lattention;
	u8 attention;
	int retval = 0;

	lattention = simple_strtoul(buf, NULL, 10);
	attention = (u8)(lattention & 0xff);
	dbg(" - attention = %d\n", attention);

	if (ops->set_attention_status)
		retval = ops->set_attention_status(slot, attention);

	if (retval)
		return retval;
	return count;
}
```

The figure follows each file from the core through the operation pciehp installs to the register bits it lands on.

```text
    Four slot files cross the hotplug core into pciehp and land on register bits
    ────────────────────────────────────────────────────────────────────────────

                           power              attention              latch               adapter
                  ┌────────────────────┬────────────────────┬────────────────────┬────────────────────┐
    user space    │        read        │    read, write     │        read        │        read        │
    slot files    ╞════════════════════╪════════════════════╪════════════════════╪════════════════════╡
    hotplug core  │ GET_STATUS reader  │   reader, writer   │ GET_STATUS reader  │ GET_STATUS reader  │
    slot ops      ╞════════════════════╪════════════════════╪════════════════════╪════════════════════╡
    installed     │       always       │ AIP, or user LEDs  │     MRL sensor     │       always       │
    pciehp        │  get_power_status  │set_attention_status│  get_latch_status  │    get_adapter_    │
                  │                    │   and its getter   │                    │       status       │
                  │port kept reachable │port kept reachable │port kept reachable │port kept reachable │
    config space  ╞════════════════════╪════════════════════╪════════════════════╪════════════════════╡
    register bits │    Slot Control    │    Slot Control    │    Slot Status     │  Slot Status PDS,  │
                  │        PCC         │   AIC (PIC, raw)   │       MRLSS        │ Link Status DLLLA  │
                  └────────────────────┴────────────────────┴────────────────────┴────────────────────┘

    slot files: the files of the slot's struct pci_slot; slot ops: the struct hotplug_slot_ops pciehp hands the core
    installed: when init_slot() fills the operation; AIP is Attention Indicator Present in slot_cap,
    user LEDs is hotplug_user_indicators, which installs the raw pair instead
    kept reachable: pci_config_pm_runtime_get() and pci_config_pm_runtime_put() bracket the register access
```

Each operation of pciehp brackets its register access with [`pci_config_pm_runtime_get()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2868) and [`pci_config_pm_runtime_put()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2890), which keep the port's configuration space reachable for the access.

```c
/* drivers/pci/pci.c:2868 */
void pci_config_pm_runtime_get(struct pci_dev *pdev)
{
	struct device *dev = &pdev->dev;
	struct device *parent = dev->parent;

	if (parent)
		pm_runtime_get_sync(parent);
	pm_runtime_get_noresume(dev);
	/*
	 * pdev->current_state is set to PCI_D3cold during suspending,
	 * so wait until suspending completes
	 */
	pm_runtime_barrier(dev);
	/*
	 * Only need to resume devices in D3cold, because config
	 * registers are still accessible for devices suspended but
	 * not in D3cold.
	 */
	if (pdev->current_state == PCI_D3cold)
		pm_runtime_resume(dev);
}

void pci_config_pm_runtime_put(struct pci_dev *pdev)
{
	struct device *dev = &pdev->dev;
	struct device *parent = dev->parent;

	pm_runtime_put(dev);
	if (parent)
		pm_runtime_put_sync(parent);
}
```

The get resumes the parent synchronously and resumes the port itself when it is in D3cold, since, as the comment says, a suspended port above D3cold still answers configuration accesses. [`set_attention_status`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L102) is the write operation for a slot with an Attention Indicator.

```c
/* drivers/pci/hotplug/pciehp_core.c:99 */
/*
 * set_attention_status - Turns the Attention Indicator on, off or blinking
 */
static int set_attention_status(struct hotplug_slot *hotplug_slot, u8 status)
{
	struct controller *ctrl = to_ctrl(hotplug_slot);
	struct pci_dev *pdev = ctrl->pcie->port;

	if (status)
		status = FIELD_PREP(PCI_EXP_SLTCTL_AIC, status);
	else
		status = PCI_EXP_SLTCTL_ATTN_IND_OFF;

	pci_config_pm_runtime_get(pdev);
	pciehp_set_indicators(ctrl, INDICATOR_NOOP, status);
	pci_config_pm_runtime_put(pdev);
	return 0;
}
```

A nonzero file value is shifted into [`PCI_EXP_SLTCTL_AIC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L617) and 0 becomes [`PCI_EXP_SLTCTL_ATTN_IND_OFF`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L621), so the values 1, 2 and 0 of the indicator table land on on, blink and off, and the command leaves the Power Indicator unchanged through [`INDICATOR_NOOP`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L181). The power and latch reads are [`get_power_status`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L118) and [`get_latch_status`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L129).

```c
/* drivers/pci/hotplug/pciehp_core.c:118 */
static int get_power_status(struct hotplug_slot *hotplug_slot, u8 *value)
{
	struct controller *ctrl = to_ctrl(hotplug_slot);
	struct pci_dev *pdev = ctrl->pcie->port;

	pci_config_pm_runtime_get(pdev);
	pciehp_get_power_status(ctrl, value);
	pci_config_pm_runtime_put(pdev);
	return 0;
}

static int get_latch_status(struct hotplug_slot *hotplug_slot, u8 *value)
{
	struct controller *ctrl = to_ctrl(hotplug_slot);
	struct pci_dev *pdev = ctrl->pcie->port;

	pci_config_pm_runtime_get(pdev);
	pciehp_get_latch_status(ctrl, value);
	pci_config_pm_runtime_put(pdev);
	return 0;
}
```

Both call the helpers of the earlier subsections with the port kept reachable and return 0, so the power file shows 1 or 0 and the latch file 1 for an open latch. [`get_adapter_status`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L140) answers the adapter file from the occupancy helper.

```c
/* drivers/pci/hotplug/pciehp_core.c:140 */
static int get_adapter_status(struct hotplug_slot *hotplug_slot, u8 *value)
{
	struct controller *ctrl = to_ctrl(hotplug_slot);
	struct pci_dev *pdev = ctrl->pcie->port;
	int ret;

	pci_config_pm_runtime_get(pdev);
	ret = pciehp_card_present_or_link_active(ctrl);
	pci_config_pm_runtime_put(pdev);
	if (ret < 0)
		return ret;

	*value = ret;
	return 0;
}
```

The adapter file shows 1 when Presence Detect State or the link reports a card, and a port that has gone turns the read into the -ENODEV error. The slot files thus reach the same helpers as the kernel's own paths, with the port held powered around each access.

### Messages and a tracepoint report the register paths

The register paths print through four macros of [`pciehp.h`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h), which route each message to the port's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352), and the comment above them says how to enable the debug ones.

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

[`ctrl_dbg()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L35) is [`pci_dbg()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2896) on the port, a dynamic debug site with [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) set, which `dyndbg="file pciehp* +p"` at boot or the control file under `/sys/kernel/debug/dynamic_debug/` turns on; with [`CONFIG_PCI_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L70) set, `DEBUG` would turn them on from boot. [`ctrl_info()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L39) and [`ctrl_err()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L37) print at their levels unconditionally. The device messages of [`pciehp_hpc.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c) carry a prefix that [`dev_fmt`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L15) defines at the top of the file.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:15 */
#define dev_fmt(fmt) "pciehp: " fmt
```

The prefix "pciehp: " comes before the message text, after the port's name, so the lines of this page are found in the kernel log by the port's name and that prefix. [`dbg_ctrl()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L978) is the probe-time debug dump of the three slot registers.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:978 */
static inline void dbg_ctrl(struct controller *ctrl)
{
	struct pci_dev *pdev = ctrl->pcie->port;
	u16 reg16;

	ctrl_dbg(ctrl, "Slot Capabilities      : 0x%08x\n", ctrl->slot_cap);
	pcie_capability_read_word(pdev, PCI_EXP_SLTSTA, &reg16);
	ctrl_dbg(ctrl, "Slot Status            : 0x%04x\n", reg16);
	pcie_capability_read_word(pdev, PCI_EXP_SLTCTL, &reg16);
	ctrl_dbg(ctrl, "Slot Control           : 0x%04x\n", reg16);
}
```

The dump shows the copy in [`slot_cap`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L95) and fresh reads of Slot Status and Slot Control, so a reader who enables it sees the slot's state before notifications are enabled. The table lists the message sites of the paths on this page, with the state each reports.

| Site | Level | Message | What it reports |
|---|---|---|---|
| [`pciehp_hpc.c:94`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L94) | info | "%s: no response from device" | the poll of Command Completed read all ones |
| [`pciehp_hpc.c:147`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L147) | info | "Timeout on hotplug command %#06x (issued %u msec ago)" | a command passed its deadline, with its value and age |
| [`pciehp_hpc.c:172`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L172) | info | "%s: no response from device" | a command was abandoned on a read of all ones |
| [`pciehp_hpc.c:246`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L246) | debug | "%s: lnk_status = %x" | Link Status behind a link-active answer |
| [`pciehp_hpc.c:270`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L270) | debug, `pr_debug()` | "pci %04x:%02x:%02x.%d id reading try %d times ..." | how many Vendor ID reads function 00.0 needed |
| [`pciehp_hpc.c:298`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L298) | info | "Slot(%s): No link" | the link wait failed |
| [`pciehp_hpc.c:314`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L314) | debug | "%s: lnk_status = %x" | Link Status after the link wait |
| [`pciehp_hpc.c:317`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L317) | info | "Slot(%s): Cannot train link: status %#06x" | the link is training or has no width |
| [`pciehp_hpc.c:327`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L327) | info | "Slot(%s): No device found" | function 00.0 did not answer |
| [`pciehp_hpc.c:374`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L374) | debug | "%s: SLOTCTRL %x, value read %x" | Slot Control behind an attention read |
| [`pciehp_hpc.c:401`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L401) | debug | "%s: SLOTCTRL %x value read %x" | Slot Control behind a power read |
| [`pciehp_hpc.c:529`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L529) | debug | "%s: SLOTCTRL %x write cmd %x" | an indicator command |
| [`pciehp_hpc.c:548`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L548) | debug | "%s: SLOTCTRL %x write cmd %x" | the power-on command |
| [`pciehp_hpc.c:554`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L554) | err | "%s: Can not enable the link!" | a failed link enable, which v7.2 cannot produce |
| [`pciehp_hpc.c:562`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L562) | debug | "%s: SLOTCTRL %x write cmd %x" | the power-off command |
| [`pciehp_hpc.c:983-987`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L983) | debug | "Slot Capabilities : 0x%08x" and two more | the three slot registers at probe |
| [`pciehp_hpc.c:1061`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1061) | info | "Slot #%d AttnBtn%c PwrCtrl%c ..." | the slot number and each capability bit, with the erratum |
| [`pciehp_ctrl.c:84`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L84) | err | "Slot(%s): Power fault" | a power fault after power on |

The debug sites with "SLOTCTRL" print the configuration offset of Slot Control first, so a reader can match them with a register dump of the port. One tracepoint fires on these paths, [`pcie_link_event`](https://elixir.bootlin.com/linux/v7.2/source/include/trace/events/pci.h#L81), from [`__pcie_update_link_speed()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L637) in the link check with reason 4, [`PCIE_HOTPLUG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L634), and it records the port, the speeds, the width, the flit mode and the Link Status bits. [`pciehp_hpc.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c) and [`pciehp_core.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c) fire no tracepoint of their own, so a command, its completion and the reads of Slot Status leave no trace event; [`pci_hp_event`](https://elixir.bootlin.com/linux/v7.2/source/include/trace/events/pci.h#L43) fires in the state machine's handler at the seam, when it reports a card or a link.

### Hand-offs and user-visible files expose the slot state

The command path crosses one hand-off between contexts, and the slot's state is visible through a few files and parameters. The completion hand-off is the wait queue of the controller, which the hard interrupt handler wakes and the writer sleeps on, as the swimlane drew. The command path queues no work item, starts no timer and uses no RCU callback or notifier chain; it runs in its caller's thread, which on the add and remove paths is the interrupt thread [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728), named here at the seam, and the poll loops of this page sleep in that thread with `msleep()`. Without an interrupt, pciehp runs a polling thread instead, chosen by [`pciehp_poll_mode`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L34), which [`pciehp_core.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c) declares as module parameters.

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

pciehp is built into the kernel with [`CONFIG_HOTPLUG_PCI_PCIE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L16) set, so the parameters are given at boot as `pciehp.pciehp_poll_mode=1` and `pciehp.pciehp_poll_time=N` and appear with mode 0644 under `/sys/module/pciehp/parameters/`. [`pcie_enable_notification()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L821), which the interrupt path runs at probe, builds the event enables of Slot Control from the same parameter, and the stage below folds its opening comment.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:821 */
static void pcie_enable_notification(struct controller *ctrl)
{
	... /* 13 lines, to :836 */
	/*
	 * Always enable link events: thus link-up and link-down shall
	 * always be treated as hotplug and unplug respectively. Enable
	 * presence detect only if Attention Button is not present.
	 */
	cmd = PCI_EXP_SLTCTL_DLLSCE;
	if (ATTN_BUTTN(ctrl))
		cmd |= PCI_EXP_SLTCTL_ABPE;
	else
		cmd |= PCI_EXP_SLTCTL_PDCE;
	if (!pciehp_poll_mode)
		cmd |= PCI_EXP_SLTCTL_HPIE;
	if (!pciehp_poll_mode && !NO_CMD_CMPL(ctrl))
		cmd |= PCI_EXP_SLTCTL_CCIE;

	mask = (PCI_EXP_SLTCTL_PDCE | PCI_EXP_SLTCTL_ABPE |
		PCI_EXP_SLTCTL_PFDE |
		PCI_EXP_SLTCTL_HPIE | PCI_EXP_SLTCTL_CCIE |
		PCI_EXP_SLTCTL_DLLSCE);

	pcie_write_cmd_nowait(ctrl, cmd, mask);
```

Polling mode leaves [`PCI_EXP_SLTCTL_HPIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L616) and [`PCI_EXP_SLTCTL_CCIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L615) out of the command, so the wait of the command path polls Command Completed, with its deadline at 2500 ms. A port for which [`NO_CMD_CMPL()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L161) holds gets no [`PCI_EXP_SLTCTL_CCIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L615) either, which matches the early return of its wait. The table lists the surfaces that expose the slot registers and their state.

| Surface | What it exposes | Where it comes from |
|---|---|---|
| `/sys/bus/pci/slots/<PSN>/power` | 1 or 0 from the Power Controller Control bit | [`get_power_status`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L118) |
| `/sys/bus/pci/slots/<PSN>/attention` | the Attention Indicator, or both indicator fields raw | [`pciehp_get_attention_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L365) or [`pciehp_get_raw_indicator_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L351) |
| `/sys/bus/pci/slots/<PSN>/latch` | the MRL Sensor State, on a slot with an MRL sensor | [`get_latch_status`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L129) |
| `/sys/bus/pci/slots/<PSN>/adapter` | occupancy from Presence Detect State or the link | [`get_adapter_status`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L140) |
| `pciehp.pciehp_poll_mode`, `pciehp.pciehp_poll_time` | polling in place of the interrupt, and its period in seconds | [`pciehp_poll_mode`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L34), [`pciehp_poll_time`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L35) |
| `/sys/kernel/debug/dynamic_debug/control` | the [`ctrl_dbg()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L35) sites of the table above | [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) |
| `/sys/kernel/tracing/events/pci/pcie_link_event` | the link recorded by the link check | [`pcie_link_event`](https://elixir.bootlin.com/linux/v7.2/source/include/trace/events/pci.h#L81) |

pciehp creates no debugfs file and no procfs entry, and no fault injection point covers the slot registers, so a register's value outside these files comes from a configuration read of the port by user space.
