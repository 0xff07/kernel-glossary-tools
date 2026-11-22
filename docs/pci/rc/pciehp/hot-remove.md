# Native hotplug removal

> CAUTION: AI-GENERATED CONTENT
>
> STRICTLY DO NOT SUBMIT THIS UPSTREAM UNLESS YOU ARE AN EXPERT INTIMATELY FAMILIAR WITH THIS SUBSYSTEM.

A PCIe slot with native hotplug lets a card leave a running machine, when a user asks for its release or when the card is pulled without warning. Before slot power is cut, every function on the card has to lose its driver and its [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352), and a function already gone must not be touched again. The pciehp port service does this from the interrupt thread of the hotplug port, for a slot it represents by a [`struct controller`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L91). This page follows one removal from the slot event to slot power off, through the disconnect marking, the removal of each function, the locks around it and the indicators.

```text
    A hotplug port, the card in its slot, and where each removal step acts
    ──────────────────────────────────────────────────────────────────────

    ┌─────────────────────────────┐  pcie   ┌─────────────────────────────┐
    │ struct controller           ├────────▶│ struct pcie_device          │
    │ the slot: state,            │         │ portdrv's hotplug service   │
    │ pending_events, reset_lock  │         └──────────────┬──────────────┘
    └─────────────────────────────┘                        │ port
                                                           ▼
    ┌───────────────────────────────────────────────────────────────────────┐
    │ struct pci_dev, the hotplug port: a Root Port or a Downstream Port    │
    │   Slot Status   PDC or DLLSC set ......... (1) the removal is reported│
    │   Slot Control  PCC off, then PIC off .... (5) power and light go off │
    └───────────────────────────────────┬───────────────────────────────────┘
                                        │ subordinate
    ════════════════════════════════════╪════════════ slot ═══════════════════
                                        ▼
    ┌───────────────────────────────────────────────────────────────────────┐
    │ the card: every function on the port's secondary bus and below it     │
    │   (2) surprise removal only: each marked pci_channel_io_perm_failure  │
    │   (3) each driver unbound and each object removed, deepest first      │
    │   (4) safe removal only: Command register quiesced, function by       │
    │       function on the secondary bus                                   │
    └───────────────────────────────────────────────────────────────────────┘

    (1) to (5) run in that order on the port's interrupt thread; the double line is the slot.
```

## SUMMARY

A native hotplug slot belongs to one Downstream Port, and pciehp keeps one [`struct controller`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L91) per slot, reached from the port's hotplug service. The table settles which kernel object stands for each term of the specification, and the rest of the page uses these names.

| Specification term | Kernel object | How code reaches it |
|---|---|---|
| Hot-Plug Slot | [`struct controller`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L91), one per slot, embedding the hotplug core's [`struct hotplug_slot`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L57) in [`hotplug_slot`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L113) | the IRQ thread's argument, or the hotplug core's slot |
| Downstream Port with a slot, a Root Port or a Switch Downstream Port | the port's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352), called the hotplug port here | [`port`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L61) of the hotplug service |
| Hot-plug service of that port | [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59), portdrv's service instance for the port | [`pcie`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L92) |
| Functions of the card in the slot | [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) objects on the port's secondary bus and below it | [`devices`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L706) of the port's [`subordinate`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L355) bus |
| Surprise removal and orderly removal | [`SURPRISE_REMOVAL`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L32) and [`SAFE_REMOVAL`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L31), passed down as a `bool` | chosen by the IRQ thread from the event it handles |

A surprise removal starts from Presence Detect Changed or Data Link Layer State Changed in [`PCI_EXP_SLTSTA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L633), and an orderly one from a [`DISABLE_SLOT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L153) request. The port's IRQ thread routes either under the read side of [`reset_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114). [`remove_board()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L112) removes every function below the port under [`pci_rescan_remove_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L3510) and only then turns slot power and the Power Indicator off through [`PCI_EXP_SLTCTL`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L610). A surprise removal first marks each function [`pci_channel_io_perm_failure`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L216), and an orderly removal quiesces each function's Command register after removing it.

## SPECIFICATIONS

The slot registers and the event rules the removal relies on are defined by the PCI Express Base Specification, which the pciehp sources cite by revision and section without section titles. The removal sequence itself, with the functions removed before power is cut, is cited without a section.

- PCIe r4.0, sec 6.7.3.2, cited by [`pciehp.h:58-60`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L58) for spacing Slot Control writes one second apart when no Command Completed event arrives.
- PCIe r4.0, sec 6.7.3.4, cited by [`pciehp_hpc.c:630-632`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L630) for slot interrupts arriving only in D3hot or shallower and only when enabled in the Slot Control register.
- PCIe Base Spec r5.0 sec 6.7.3.4, cited by [`pciehp_hpc.c:689-691`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L689) for a port in MSI mode sending a new interrupt only after all event bits are clear.
- The specification without a section, cited by commit [2326e2b99969](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=2326e2b99969e69fedc92de80d80b2d2f92fd942) ("pciehp: block new requests from the device before power off") for disabling Bus Master, SERR# and INTx before slot power is turned off.

## COVERAGE

### The removal path (drivers/pci/hotplug/)

- [`'\<remove_board\>':'drivers/pci/hotplug/pciehp_ctrl.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L112): removes the functions below the port, then powers the slot off and turns the Power Indicator off.
- [`'\<pciehp_unconfigure_device\>':'drivers/pci/hotplug/pciehp_pci.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_pci.c#L95): marks a surprise-removed subtree disconnected, then stops and removes each function on the secondary bus under the rescan-remove mutex.
- [`'\<set_slot_off\>':'drivers/pci/hotplug/pciehp_ctrl.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L34): powers the slot off after a failed add and lights the Attention Indicator.
- [`'controller.reset_lock'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114): the semaphore whose read side the IRQ thread holds while it acts on slot events and whose write side a slot reset holds.

### Disconnecting and removing functions (drivers/pci/)

- [`'\<pci_walk_bus\>':'drivers/pci/bus.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/bus.c#L461): calls a callback on every function of a bus and of the buses below it.
- [`'\<pci_dev_set_disconnected\>':'drivers/pci/pci.h'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L759): the callback that sets a function's error state to permanent failure.
- [`'\<pci_lock_rescan_remove\>':'drivers/pci/probe.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L3512): takes the mutex that serializes rescans and removals.
- [`'\<pci_unlock_rescan_remove\>':'drivers/pci/probe.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L3518): releases that mutex.
- [`'\<pci_stop_and_remove_bus_device\>':'drivers/pci/remove.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/remove.c#L125): stops a function and everything below it, then removes them.

### Hotplug events and the ignore flag

- [`'PCI_HOTPLUG_LINK_DOWN'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci.h#L44): the event value the hotplug tracepoint records for a link that went down.
- [`'PCI_HOTPLUG_CARD_NOT_PRESENT'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci.h#L46): the event value it records for a card that left the slot.
- [`'\<pci_ignore_hotplug\>':'drivers/pci/pci.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L6339): sets [`ignore_hotplug`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L424) on a function and on the bridge above it, so that port drops the slot events.

## DOCUMENTATION

- [`Documentation/PCI/pciebus-howto.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/PCI/pciebus-howto.rst): the PCIe port bus driver and its services, among them the native hotplug service whose IRQ thread runs the removal.
- [`Documentation/PCI/pci.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/PCI/pci.rst): the remove hook of a driver, which the core calls for each function it removes, and the reference-counted lookup functions that stay safe across a removal.
- [`Documentation/ABI/testing/sysfs-bus-pci`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/ABI/testing/sysfs-bus-pci): the slot directories under /sys/bus/pci/slots/ that the hotplug core creates.
- [`Documentation/admin-guide/dynamic-debug-howto.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/admin-guide/dynamic-debug-howto.rst): how to enable the debug messages of a file, which turns on the pciehp debug lines this page lists.

## OTHER SOURCES

### Added by Claude Opus 5.5

- [PCI: pciehp: Fix AB-BA deadlock between reset_lock and device_lock (commit f5eff5591b8f)](https://lore.kernel.org/r/fef2b2e9edf245c049a8c5b94743c0f74ff5008a.1681191902.git.lukas@wunner.de)
- [PCI: pciehp: Use down_read/write_nested(reset_lock) to fix lockdep errors (commit 085a9f43433f)](https://lore.kernel.org/r/20211217141709.379663-1-hdegoede@redhat.com)
- [PCI: pciehp: Ignore Link State Changes after powering off a slot (commit 3943af9d01e9)](https://bugzilla.kernel.org/show_bug.cgi?id=203237)
- [PCI/bwctrl: Re-add BW notification portdrv as PCIe BW controller (commit 665745f27487)](https://lore.kernel.org/r/20241018144755.7875-7-ilpo.jarvinen@linux.intel.com)
- [PCI: Add pci_ignore_hotplug() to ignore hotplug events for a device (commit b440bde74f04)](https://bugzilla.kernel.org/show_bug.cgi?id=77261)
- [PCI: Propagate the "ignore hotplug" setting to parent (commit 0824965140ff)](https://bugzilla.kernel.org/show_bug.cgi?id=61891)
- [PCI: trace: Add generic RAS tracepoint for hotplug event (commit 9e541b3cee70)](https://patch.msgid.link/20251210132907.58799-2-xueshuai@linux.alibaba.com)

## REGISTERS

The removal reads and writes five registers. The slot registers and the Link Status register belong to the PCIe capability of the hotplug port, and the Command register belongs to the header of each function on the card. Each drawing names the macros that define the fields, and the paragraph above it says what the fields decide on the removal path.

The Slot Capabilities register, [`PCI_EXP_SLTCAP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L597), says which slot hardware exists, and [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) caches it in [`slot_cap`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L95). [`POWER_CTRL()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L157) tests Power Controller Present and decides whether the removal writes the power command and waits a second. [`PWR_LED()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L160) and [`ATTN_LED()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L159) test the indicator bits and decide whether [`pciehp_set_indicators()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L513) writes an indicator at all.

```text
    Slot Capabilities register, offset 0x14 of the PCIe capability
    ──────────────────────────────────────────────────────────────

    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x14  │   Physical Slot Number  │N│E│ s │  SPLV (14:7)  │H│S│p│a│M│P│B│
          │         (31:19)         │ │ │   │               │ │ │ │ │ │ │ │
          └─────────────────────────┴─┴─┴───┴───────────────┴─┴─┴─┴─┴─┴─┴─┘

    P = PCI_EXP_SLTCAP_PCP (Power Controller Present, tested by POWER_CTRL())
    p = PCI_EXP_SLTCAP_PIP (Power Indicator Present, tested by PWR_LED())
    a = PCI_EXP_SLTCAP_AIP (Attention Indicator Present, tested by ATTN_LED())
    B = PCI_EXP_SLTCAP_ABP (Attention Button Present, tested by ATTN_BUTTN())
    M = PCI_EXP_SLTCAP_MRLSP, S = PCI_EXP_SLTCAP_HPS, H = PCI_EXP_SLTCAP_HPC, E = PCI_EXP_SLTCAP_EIP,
    N = PCI_EXP_SLTCAP_NCCS, s = PCI_EXP_SLTCAP_SPLS (16:15), SPLV = PCI_EXP_SLTCAP_SPLV,
    Physical Slot Number = PCI_EXP_SLTCAP_PSN; unread on the removal path
    the register is cached in controller.slot_cap, with PIP and AIP masked out for a port
    whose hotplug_user_indicators is set
```

The Slot Control register, [`PCI_EXP_SLTCTL`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L610), carries the commands. The removal writes Power Controller Control, [`PCI_EXP_SLTCTL_PCC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L626), to [`PCI_EXP_SLTCTL_PWR_OFF`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L628) and Power Indicator Control, [`PCI_EXP_SLTCTL_PIC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L622), to [`PCI_EXP_SLTCTL_PWR_IND_OFF`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L625). A failed add also writes Attention Indicator Control, [`PCI_EXP_SLTCTL_AIC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L617), to [`PCI_EXP_SLTCTL_ATTN_IND_ON`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L619). The hard handler reads Hot-Plug Interrupt Enable, [`PCI_EXP_SLTCTL_HPIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L616), from the cached copy in [`slot_ctrl`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L98) before it touches the port.

```text
    Slot Control register, offset 0x18 of the PCIe capability
    ─────────────────────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x18  │·│i│l│d│E│P│PIC│AIC│h│c│p│m│f│a│
          └─┴─┴─┴─┴─┴─┴───┴───┴─┴─┴─┴─┴─┴─┘

    P   = PCI_EXP_SLTCTL_PCC (Power Controller Control, bit 10): PCI_EXP_SLTCTL_PWR_ON (0),
          PCI_EXP_SLTCTL_PWR_OFF (0x0400), the value the power-off writes
    PIC = PCI_EXP_SLTCTL_PIC (Power Indicator Control, 9:8): PWR_IND_ON (0x0100),
          PWR_IND_BLINK (0x0200), PWR_IND_OFF (0x0300)
    AIC = PCI_EXP_SLTCTL_AIC (Attention Indicator Control, 7:6): ATTN_IND_ON (0x0040),
          ATTN_IND_BLINK (0x0080), ATTN_IND_OFF (0x00c0)
    h   = PCI_EXP_SLTCTL_HPIE (Hot-Plug Interrupt Enable), tested by the hard handler
    a = ABPE, f = PFDE, m = MRLSCE, p = PDCE, c = CCIE, d = DLLSCE: event enables, unchanged here
    E = PCI_EXP_SLTCTL_EIC, l = PCI_EXP_SLTCTL_ASPL_DISABLE, i = PCI_EXP_SLTCTL_IBPD_DISABLE
    · = bit 15, which pci_regs.h does not name; the last value written is kept in controller.slot_ctrl
```

The Slot Status register, [`PCI_EXP_SLTSTA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L633), reports the events. Presence Detect Changed, [`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637), and Data Link Layer State Changed, [`PCI_EXP_SLTSTA_DLLSC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L642), start a surprise removal, and Command Completed, [`PCI_EXP_SLTSTA_CC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L638), ends the wait after each command. The hard handler clears the event bits it saw by writing them back and saves them in [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104).

```text
    Slot Status register, offset 0x1a of the PCIe capability
    ────────────────────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x1a  │   unnamed   │D│e│p│m│C│P│M│F│A│
          └─────────────┴─┴─┴─┴─┴─┴─┴─┴─┴─┘

    D = PCI_EXP_SLTSTA_DLLSC (Data Link Layer State Changed): the link went up or down
    P = PCI_EXP_SLTSTA_PDC (Presence Detect Changed): a card arrived or left
    C = PCI_EXP_SLTSTA_CC (Command Completed): the last Slot Control command took effect
    A = PCI_EXP_SLTSTA_ABP (Attention Button Pressed), F = PCI_EXP_SLTSTA_PFD (Power Fault Detected)
    M = PCI_EXP_SLTSTA_MRLSC, m = PCI_EXP_SLTSTA_MRLSS, p = PCI_EXP_SLTSTA_PDS (Presence Detect
    State), e = PCI_EXP_SLTSTA_EIS; uppercase bits are events, cleared by writing 1
    bits 15:9 have no macro in pci_regs.h
```

The Link Status register of the port, [`PCI_EXP_LNKSTA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L577), carries two bits the removal meets. The last step of a removal clears Link Bandwidth Management Status, [`PCI_EXP_LNKSTA_LBMS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L594), so the next card's link starts without the old one's record. Data Link Layer Link Active, [`PCI_EXP_LNKSTA_DLLLA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L593), is one of the two bits that the kerneldoc of [`reset_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114) names as flapping during a slot reset.

```text
    Link Status register, offset 0x12 of the PCIe capability
    ────────────────────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x12  │A│B│D│C│T│·│    nlw    │  cls  │
          │ │ │ │ │ │ │   (9:4)   │ (3:0) │
          └─┴─┴─┴─┴─┴─┴───────────┴───────┘

    B = PCI_EXP_LNKSTA_LBMS (Link Bandwidth Management Status), cleared by writing 1
    D = PCI_EXP_LNKSTA_DLLLA (Data Link Layer Link Active), the bit reset_lock keeps from flapping readers
    A = PCI_EXP_LNKSTA_LABS, C = PCI_EXP_LNKSTA_SLC, T = PCI_EXP_LNKSTA_LT,
    nlw = PCI_EXP_LNKSTA_NLW, cls = PCI_EXP_LNKSTA_CLS; unread on the removal path
    · = bit 10, which pci_regs.h does not name
```

The Command register, [`PCI_COMMAND`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L40), belongs to each function on the card. An orderly removal clears [`PCI_COMMAND_MASTER`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L43) and [`PCI_COMMAND_SERR`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L49) and sets [`PCI_COMMAND_INTX_DISABLE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L51), so a function still in the slot issues no more requests and raises no more interrupts before its power goes.

```text
    Command register, offset 0x04 of every configuration header
    ───────────────────────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x04  │ unnamed │X│F│S│T│P│V│W│C│B│M│I│
          └─────────┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┘

    B = PCI_COMMAND_MASTER (bus mastering), cleared on a safe removal
    S = PCI_COMMAND_SERR (SERR# reporting), cleared on a safe removal
    X = PCI_COMMAND_INTX_DISABLE (INTx emulation disable), set on a safe removal
    I = PCI_COMMAND_IO, M = PCI_COMMAND_MEMORY, C = PCI_COMMAND_SPECIAL, W = PCI_COMMAND_INVALIDATE,
    V = PCI_COMMAND_VGA_PALETTE, P = PCI_COMMAND_PARITY, T = PCI_COMMAND_WAIT,
    F = PCI_COMMAND_FAST_BACK; the removal path writes them back unchanged
    bits 15:11 have no macro in pci_regs.h
```

## DETAILS

The subsections follow one removal in the order it runs. They start at the slot event the hard handler saves and the request a user or the Attention Button makes, which the IRQ thread routes into [`POWEROFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L137). They then follow [`remove_board()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L112) through the disconnect marking, the removal of each function under the rescan-remove mutex, the Command register quiesce, slot power and the indicators. The last ones cover the slot's final state, the write side of [`reset_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114), the [`ignore_hotplug`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L424) flag that keeps a removal from starting, and the traces the path leaves.

### Kconfig assumptions

The page documents an x86-64 kernel configured from the x86_64 defconfig at v7.2, with native PCIe hotplug, the PCIe port services and dynamic debug enabled on top of it. The table lists every option the prose names, the value the page assumes and what the option decides on the removal path.

| option | assumed value | what it decides here |
|---|---|---|
| [`CONFIG_HOTPLUG_PCI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/Kconfig#L6) | y | builds the hotplug core, its slot directories and the power file of each slot |
| [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5) | y | builds the port services, pciehp among them, and the LBMS clearing at the end of a removal |
| [`CONFIG_HOTPLUG_PCI_PCIE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L16) | y | builds pciehp into the kernel, so its parameters are set on the kernel command line |
| [`CONFIG_PM_SLEEP`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L140) | y | builds the resume check that marks a card replaced during sleep disconnected |
| [`CONFIG_PCI_DOE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L142) | unset | turns the mailbox cancellation of the disconnect marking into an empty stub |
| [`CONFIG_HOTPLUG_PCI_ACPI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/Kconfig#L55) | unset | leaves out the ACPI hotplug driver, the other reader of the ignore flag |
| [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) | y | makes the pciehp debug lines dynamic-debug sites |
| [`CONFIG_PCI_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L70) | unset | leaves those sites off until a reader enables them |

The table indexes the prose. Each option's effect is stated again where it applies in the subsections below, so a reader who skips this subsection still meets every assumption.

### The hard handler saves slot events for the IRQ thread

A card leaves a slot in one of two ways the hotplug port can see: its presence detect changes, or the link to it goes down. The port reports either one as an event bit in its Slot Status register, [`PCI_EXP_SLTSTA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L633), and raises an interrupt. The hard interrupt handler of pciehp runs where it cannot sleep, so it only records the event for the IRQ thread, which runs the removal. Both handlers work on one object per slot.

That object is [`struct controller`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L91), which [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) allocates when the hotplug service of a port probes. The table names the groups its comments label and what a removal uses each group for.

| comment group | members | what a removal uses them for |
|---|---|---|
| none | [`pcie`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L92), [`dsn`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L93) | the way to the hotplug port, and the serial number a resume compares to detect a replaced card |
| capabilities and quirks | [`slot_cap`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L95), [`inband_presence_disabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L96) | which slot hardware exists: power controller, indicators, button |
| control register access | [`slot_ctrl`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L98), [`ctrl_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L99), [`cmd_started`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L100), [`cmd_busy`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L101), [`queue`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L102) | the last Slot Control value, the mutex that serializes commands, and the wait for each command to complete |
| event handling | [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104), [`notification_enabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L105), [`power_fault_detected`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L106), [`poll_thread`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L107) | the word where the hard handler leaves events for the IRQ thread |
| state machine | [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109), [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110), [`button_work`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L111) | the slot's state, its mutex and the five-second work an Attention Button press schedules |
| hotplug core interface | [`hotplug_slot`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L113), [`reset_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114), [`depth`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L115), [`ist_running`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L116), [`request_result`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L117), [`requester`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L118) | the core's slot object, the semaphore that keeps a slot reset out, and the handshake of a sysfs request |

Read [`struct controller`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L91) from the last lines of its kerneldoc, which state that one controller stands for one slot, through its groups in declaration order.

```c
/* drivers/pci/hotplug/pciehp.h:88 */
 * PCIe hotplug has a 1:1 relationship between controller and slot, hence
 * unlike other drivers, the two aren't represented by separate structures.
 */
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

The comment that opens the last group labels only [`hotplug_slot`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L113), and the members after it belong to the reset and to the sysfs request, which later subsections read. [`pcie`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L92) points at the port's hotplug service, whose [`port`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L61) is the hotplug port. The figure follows the pointers from the controller to the functions a removal tears down.

```text
    The pointers that lead from a slot's controller to the functions on its card
    ────────────────────────────────────────────────────────────────────────────

    struct controller                  struct pcie_device
    ┌───────────────────────────┐      ┌───────────────────────────┐
    │ pcie ─────────────────────┼─────▶│ port ─────────────────────┼──┐
    │ slot_cap   PCP, AIP, PIP  │      │ irq    the port's vector  │  │
    │ slot_ctrl  last command   │      └───────────────────────────┘  │
    │ pending_events            │                                     │
    │ state, state_lock         │      struct pci_dev, hotplug port   ▼
    │ hotplug_slot (embedded)   │      ┌──────────────────────────────────┐
    │ reset_lock, depth         │      │ subordinate ─────────────────────┼──┐
    │ request_result, requester │      │ ignore_hotplug                   │  │
    └───────────────────────────┘      └──────────────────────────────────┘  │
                                                                             │
                                       struct pci_bus, the secondary bus     ▼
                                       ┌──────────────────────────────────────┐
                                       │ devices ── 01:00.0 ── 01:00.1 ── ... │
                                       │ self: the hotplug port               │
                                       └──────────────────────────────────────┘

    pending_events, state and reset_lock belong to the slot; error_state, priv_flags
    and bus_list belong to each function on devices and below.
```

Events reach [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104) together with requests that are no Slot Status bits. The comment above the two request flags, [`DISABLE_SLOT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L153) and [`RERUN_ISR`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L154), says how both kinds share one word:

```c
/* drivers/pci/hotplug/pciehp.h:140 */
/**
 * DOC: Flags to request an action from the IRQ thread
 *
 * These are stored together with events read from the Slot Status register,
 * hence must be greater than its 16-bit width.
 *
 * %DISABLE_SLOT: Disable the slot in response to a user request via sysfs or
 *	an Attention Button press after the 5 second delay
 * %RERUN_ISR: Used by the IRQ handler to inform the IRQ thread that the
 *	hotplug port was inaccessible when the interrupt occurred, requiring
 *	that the IRQ handler is rerun by the IRQ thread after it has made the
 *	hotplug port accessible by runtime resuming its parents to D0
 */
#define DISABLE_SLOT		(1 << 16)
#define RERUN_ISR		(1 << 17)
```

[`DISABLE_SLOT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L153) and [`RERUN_ISR`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L154) use bits 16 and 17 because the Slot Status register is 16 bits wide, so one atomic word carries the events and the requests together. The drawing shows which bits of the word a removal can find set.

```text
    controller.pending_events: Slot Status events below bit 16, requests above them
    ───────────────────────────────────────────────────────────────────────────────

    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    word  │           unused          │R│X│    unused   │L│ unused│P│·│F│A│
          └───────────────────────────┴─┴─┴─────────────┴─┴───────┴─┴─┴─┴─┘

    A = PCI_EXP_SLTSTA_ABP (Attention Button Pressed, saved by the hard handler)
    F = PCI_EXP_SLTSTA_PFD (Power Fault Detected, saved by the hard handler)
    P = PCI_EXP_SLTSTA_PDC (Presence Detect Changed, saved by the hard handler or requested)
    L = PCI_EXP_SLTSTA_DLLSC (Data Link Layer State Changed, saved by the hard handler or requested)
    X = DISABLE_SLOT (1 << 16, a safe removal requested through sysfs or the button)
    R = RERUN_ISR (1 << 17, the port was inaccessible when the interrupt arrived)
    · = bit 2, PCI_EXP_SLTSTA_MRLSC in Slot Status, which the hard handler does not save
    Command Completed (bit 4) is consumed by the hard handler itself; nothing in pciehp
    sets the bits marked unused
```

The hard handler, [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623), fills the event bits. Read its first stage, which decides whether the interrupt is the port's and reads Slot Status; the folded lines keep the port's parent awake.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:623 */
static irqreturn_t pciehp_isr(int irq, void *dev_id)
{
	struct controller *ctrl = (struct controller *)dev_id;
	struct pci_dev *pdev = ctrl_dev(ctrl);
	struct device *parent = pdev->dev.parent;
	u16 status, events = 0;

	/*
	 * Interrupts only occur in D3hot or shallower and only if enabled
	 * in the Slot Control register (PCIe r4.0, sec 6.7.3.4).
	 */
	if (pdev->current_state == PCI_D3cold ||
	    (!(ctrl->slot_ctrl & PCI_EXP_SLTCTL_HPIE) && !pciehp_poll_mode))
		return IRQ_NONE;
... /* 16 lines, to :653 */
read_status:
	pcie_capability_read_word(pdev, PCI_EXP_SLTSTA, &status);
	if (PCI_POSSIBLE_ERROR(status)) {
		ctrl_info(ctrl, "%s: no response from device\n", __func__);
		if (parent)
			pm_runtime_put(parent);
		return IRQ_NONE;
	}

	/*
	 * Slot Status contains plain status bits as well as event
	 * notification bits; right now we only want the event bits.
	 */
	status &= PCI_EXP_SLTSTA_ABP | PCI_EXP_SLTSTA_PFD |
		  PCI_EXP_SLTSTA_PDC | PCI_EXP_SLTSTA_CC |
		  PCI_EXP_SLTSTA_DLLSC;
```

The handler ignores the interrupt when the port is in D3cold or when Hot-Plug Interrupt Enable, [`PCI_EXP_SLTCTL_HPIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L616), is clear in the cached [`slot_ctrl`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L98), as the comment citing the specification allows. A Slot Status read of all ones means the port did not answer, and the mask at [`pciehp_hpc.c:666-668`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L666) keeps the event bits of the value read. Read the end of [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623), which clears the events in the port and decides whether to wake the thread; the folded lines handle a power fault.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:623 */
static irqreturn_t pciehp_isr(int irq, void *dev_id)
{
	struct controller *ctrl = (struct controller *)dev_id;
	struct pci_dev *pdev = ctrl_dev(ctrl);
	... /* 59 lines, to :686 */
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

	ctrl_dbg(ctrl, "pending interrupts %#06x from Slot Status\n", events);
	if (parent)
		pm_runtime_put(parent);

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

	if (pdev->ignore_hotplug) {
		ctrl_dbg(ctrl, "ignoring hotplug event %#06x\n", events);
		return IRQ_HANDLED;
	}

	/* Save pending events for consumption by IRQ thread. */
	atomic_or(events, &ctrl->pending_events);
	return IRQ_WAKE_THREAD;
}
```

The write at [`pciehp_hpc.c:687`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L687) writes the bits the handler saw back to the port to clear them. Command Completed is consumed here, by clearing [`cmd_busy`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L101) and waking [`queue`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L102), because the thread may be the one waiting for it. Every other event is ORed into [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104), and IRQ_WAKE_THREAD hands the interrupt to the thread, unless the port's [`ignore_hotplug`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L424) is set, a case a later subsection returns to.

The hard handler thus leaves the port's events in one word and wakes one thread, and everything a removal does from here on runs on that thread.

### A user or the Attention Button requests an orderly removal

An orderly removal starts with a person, who writes 0 to the slot's power file or presses the slot's Attention Button. Neither path removes anything itself. Each ORs [`DISABLE_SLOT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L153) into [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104) and wakes the IRQ thread, so an orderly removal runs on the same thread as a surprise one.

The power file belongs to the hotplug core, built with [`CONFIG_HOTPLUG_PCI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/Kconfig#L6), which creates a directory per slot under /sys/bus/pci/slots/. Its store method, [`power_write_file()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L67), turns a written 0 into a call of the slot's [`disable_slot`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L40) method. Read its stage up to that call.

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
```

A value of 0 reaches [`disable_slot`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L40) at [`pci_hotplug_core.c:81-82`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L81). pciehp fills that method when it registers the slot, in [`init_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L51):

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
```

[`pciehp_sysfs_disable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L432) is therefore what a write of 0 runs, and [`pciehp_reset_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L939) is the slot's reset method, which a later subsection reads. Read the disable method for the states that accept the request and for the wait that follows it.

```c
/* drivers/pci/hotplug/pciehp_ctrl.c:432 */
int pciehp_sysfs_disable_slot(struct hotplug_slot *hotplug_slot)
{
	struct controller *ctrl = to_ctrl(hotplug_slot);

	mutex_lock(&ctrl->state_lock);
	switch (ctrl->state) {
	case BLINKINGOFF_STATE:
	case ON_STATE:
		mutex_unlock(&ctrl->state_lock);
		pciehp_request(ctrl, DISABLE_SLOT);
		wait_event(ctrl->requester,
			   !atomic_read(&ctrl->pending_events) &&
			   !ctrl->ist_running);
		return ctrl->request_result;
	case POWEROFF_STATE:
		ctrl_info(ctrl, "Slot(%s): Already in powering off state\n",
			  slot_name(ctrl));
		break;
	case BLINKINGON_STATE:
	case OFF_STATE:
	case POWERON_STATE:
		ctrl_info(ctrl, "Slot(%s): Already disabled\n",
			  slot_name(ctrl));
		break;
	default:
		ctrl_err(ctrl, "Slot(%s): Invalid state %#x\n",
			 slot_name(ctrl), ctrl->state);
		break;
	}
	mutex_unlock(&ctrl->state_lock);

	return -ENODEV;
}
```

A slot in [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) or [`BLINKINGOFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L135) accepts the request. The method drops [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110), submits [`DISABLE_SLOT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L153) and sleeps on [`requester`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L118) until [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104) is empty and [`ist_running`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L116) is clear, then returns [`request_result`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L117). Every other state logs why and returns -ENODEV. The submission is [`pciehp_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L141), and the button's delayed work, [`pciehp_queue_pushbutton_work()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L148), submits the same flag; read the two together.

```c
/* drivers/pci/hotplug/pciehp_ctrl.c:141 */
void pciehp_request(struct controller *ctrl, int action)
{
	atomic_or(action, &ctrl->pending_events);
	if (!pciehp_poll_mode)
		irq_wake_thread(ctrl->pcie->irq, ctrl);
}

void pciehp_queue_pushbutton_work(struct work_struct *work)
{
	struct controller *ctrl = container_of(work, struct controller,
					       button_work.work);

	mutex_lock(&ctrl->state_lock);
	switch (ctrl->state) {
	case BLINKINGOFF_STATE:
		pciehp_request(ctrl, DISABLE_SLOT);
		break;
	case BLINKINGON_STATE:
		pciehp_request(ctrl, PCI_EXP_SLTSTA_PDC);
		break;
	default:
		break;
	}
	mutex_unlock(&ctrl->state_lock);
}
```

[`pciehp_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L141) ORs the action into the word and wakes the thread with irq_wake_thread(), unless [`pciehp_poll_mode`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L34) is set and the poll thread finds the word on its next pass. The button work requests [`DISABLE_SLOT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L153) only while the slot is still in [`BLINKINGOFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L135). The press itself arrives as Attention Button Pressed, [`PCI_EXP_SLTSTA_ABP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L634), which the IRQ thread passes to [`pciehp_handle_button_press()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L167); read its stage that starts the five seconds and its stage that cancels them on a second press.

```c
/* drivers/pci/hotplug/pciehp_ctrl.c:167 */
void pciehp_handle_button_press(struct controller *ctrl)
{
	mutex_lock(&ctrl->state_lock);
	switch (ctrl->state) {
	case OFF_STATE:
	case ON_STATE:
		if (ctrl->state == ON_STATE) {
			ctrl->state = BLINKINGOFF_STATE;
			ctrl_info(ctrl, "Slot(%s): Button press: will power off in 5 sec\n",
				  slot_name(ctrl));
		} else {
			ctrl->state = BLINKINGON_STATE;
			ctrl_info(ctrl, "Slot(%s): Button press: will power on in 5 sec\n",
				  slot_name(ctrl));
		}
		/* blink power indicator and turn off attention */
		pciehp_set_indicators(ctrl, PCI_EXP_SLTCTL_PWR_IND_BLINK,
				      PCI_EXP_SLTCTL_ATTN_IND_OFF);
		schedule_delayed_work(&ctrl->button_work, 5 * HZ);
		break;
		... /* 8 lines, to :195 */
		if (ctrl->state == BLINKINGOFF_STATE) {
			ctrl->state = ON_STATE;
			pciehp_set_indicators(ctrl, PCI_EXP_SLTCTL_PWR_IND_ON,
					      PCI_EXP_SLTCTL_ATTN_IND_OFF);
			ctrl_info(ctrl, "Slot(%s): Button press: canceling request to power off\n",
				  slot_name(ctrl));
		} else {
			ctrl->state = OFF_STATE;
			pciehp_set_indicators(ctrl, PCI_EXP_SLTCTL_PWR_IND_OFF,
					      PCI_EXP_SLTCTL_ATTN_IND_OFF);
			ctrl_info(ctrl, "Slot(%s): Button press: canceling request to power on\n",
				  slot_name(ctrl));
		}
		break;
```

A press in [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) moves the slot to [`BLINKINGOFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L135), sets the Power Indicator blinking and the Attention Indicator off, and schedules [`button_work`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L111) after `5 * HZ` jiffies. A second press inside those five seconds cancels the work, returns the slot to [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) and lights the Power Indicator again. The figure shows a sysfs request handed to the thread and back.

```text
    A safe removal requested through sysfs, handed to the IRQ thread and back
    ─────────────────────────────────────────────────────────────────────────

    writer of the slot's power file                       IRQ thread of the hotplug port
     ┌─────────────────────────┐                           ┌─────────────────────────┐
     │ slot in ON_STATE        │                           │ idle                    │
     └────────────┬────────────┘                           └────────────┬────────────┘
                  │  ORs DISABLE_SLOT into pending_events, wakes thread │
                  ├────────────────────────────────────────────────────▶│ ist_running = true
                  │ sleeps on requester                                 │ takes pending_events, leaving 0
                  │                                                     │ POWEROFF_STATE
                  │                                                     │ devices removed, slot powered off
                  │                                                     │ request_result = the result
                  │                                                     │ OFF_STATE
                  │                                                     │ ist_running = false
                  │  requester woken                                    │
                  │◀────────────────────────────────────────────────────┤
                  │ pending_events 0 and the thread idle: returns 0     │
                  ▼ time                                                ▼ time

    The 5-second button work ORs the same DISABLE_SLOT and wakes the same thread, without waiting.
```

The writer's wait ends when the thread clears [`ist_running`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L116) and wakes [`requester`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L118) at the end of its run, which the next subsection shows. The button work submits without waiting, so its result shows only in the slot's state and in the log.

### The IRQ thread routes removals under reset_lock's read side

The IRQ thread, [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728), is where a removal runs, because removing functions unbinds drivers and takes sleeping locks. It takes the whole event word at once, handles the button and a power fault, drops the link changes it was told to expect, and then routes what is left. The routing runs under the read side of [`reset_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114), so a slot reset waits until the handlers return.

Read the stage of [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728) that takes the word, the stage that routes it, and the end of the run. The folded lines rerun the hard handler when the port was asleep, and handle the button, a power fault and the link changes to ignore.

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
	... /* 9 lines, to :746 */
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

	ret = IRQ_HANDLED;
out:
	pci_config_pm_runtime_put(pdev);
	ctrl->ist_running = false;
	wake_up(&ctrl->requester);
	return ret;
}
```

The atomic_xchg() at [`pciehp_hpc.c:747`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L747) takes [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104) and leaves it 0, so events that arrive during the removal wait in the word for the thread's next run. [`DISABLE_SLOT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L153) is tested before the two Slot Status events, as the comment at [`pciehp_hpc.c:781-784`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L781) requires, and either handler runs between down_read_nested() and up_read() on [`reset_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114). [`depth`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L115), the number of hotplug ports above this one, is passed as the lock subclass, which the subsection on slot resets explains.

The end of the run clears [`ist_running`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L116) and wakes [`requester`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L118), which releases a sysfs writer whose request is done. The lines folded at [`pciehp_hpc.c:764-779`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L764) drop link changes that the kernel caused itself, as their comment says; they are the link-change suppression mechanism, which this page does not follow.

From here on a removal runs on the IRQ thread with the read side of [`reset_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114) held, in one of the two handlers.

### Both kinds of removal set POWEROFF_STATE first

The slot's state machine records whether the slot is on, off or between the two, in [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109) under [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110). Both handlers move the slot to [`POWEROFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L137) before the shared disable path runs, and they differ only in the boolean they pass down. The six values of [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109), [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) through [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138), are defined in pciehp.h with their meanings:

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

A removal leaves [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) or [`BLINKINGOFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L135), passes [`POWEROFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L137) while the functions are removed, and ends in [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133). The figure shows the transitions a removal takes and the events that drive them.

```text
    The slot states a removal moves through, and what moves it
    ──────────────────────────────────────────────────────────

                Attention Button pressed
          ┌────────────────────────────────┐
          │                                ▼
    ┌─────┴──────┐  pressed again   ┌───────────────────┐
    │  ON_STATE  │◀─────────────────┤ BLINKINGOFF_STATE │
    └─────┬──────┘  within 5 s      └─────────┬─────────┘
          │                                   │ DISABLE_SLOT after 5 s or
          │ DLLSC or PDC: surprise            │ from sysfs: safe;
          │ DISABLE_SLOT from sysfs: safe     │ DLLSC or PDC: surprise
          ▼                                   ▼
    ┌────────────────────────────────────────────────────────┐
    │ POWEROFF_STATE: devices removed, slot powered off      │
    └───────────────────────────┬────────────────────────────┘
                                │ the disable path returns, whatever its result
                                ▼
                         ┌─────────────┐  card present or link up  ┌───────────────┐
                         │  OFF_STATE  ├──────────────────────────▶│ POWERON_STATE │
                         └─────────────┘  at the presence re-check └───────────────┘

    Every arrow into POWEROFF_STATE is taken under state_lock; POWERON_STATE starts the add path.
```

The boolean that tells the two kinds apart is spelled [`SAFE_REMOVAL`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L31) or [`SURPRISE_REMOVAL`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L32), defined at the top of pciehp_ctrl.c. True means the card is still in the slot, as the kerneldoc of the function that receives it says.

```c
/* drivers/pci/hotplug/pciehp_ctrl.c:31 */
#define SAFE_REMOVAL	 true
#define SURPRISE_REMOVAL false
```

[`pciehp_handle_disable_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L217) handles [`DISABLE_SLOT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L153). Read it for the cancellation of pending button work and for the [`SAFE_REMOVAL`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L31) it passes on.

```c
/* drivers/pci/hotplug/pciehp_ctrl.c:217 */
void pciehp_handle_disable_request(struct controller *ctrl)
{
	mutex_lock(&ctrl->state_lock);
	switch (ctrl->state) {
	case BLINKINGON_STATE:
	case BLINKINGOFF_STATE:
		cancel_delayed_work(&ctrl->button_work);
		break;
	}
	ctrl->state = POWEROFF_STATE;
	mutex_unlock(&ctrl->state_lock);

	ctrl->request_result = pciehp_disable_slot(ctrl, SAFE_REMOVAL);
}
```

The handler cancels [`button_work`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L111) when the slot was blinking, sets [`POWEROFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L137) under [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110) and stores the result of [`pciehp_disable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L378) in [`request_result`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L117), where a waiting sysfs writer reads it. [`pciehp_handle_presence_or_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L232) handles the two Slot Status events. Read its first stage, which tears the slot down whenever it was on.

```c
/* drivers/pci/hotplug/pciehp_ctrl.c:232 */
void pciehp_handle_presence_or_link_change(struct controller *ctrl, u32 events)
{
	int present, link_active;

	/*
	 * If the slot is on and presence or link has changed, turn it off.
	 * Even if it's occupied again, we cannot assume the card is the same.
	 */
	mutex_lock(&ctrl->state_lock);
	switch (ctrl->state) {
	case BLINKINGOFF_STATE:
		cancel_delayed_work(&ctrl->button_work);
		fallthrough;
	case ON_STATE:
		ctrl->state = POWEROFF_STATE;
		mutex_unlock(&ctrl->state_lock);
		if (events & PCI_EXP_SLTSTA_DLLSC) {
			ctrl_info(ctrl, "Slot(%s): Link Down\n",
				  slot_name(ctrl));
			trace_pci_hp_event(pci_name(ctrl->pcie->port),
					   slot_name(ctrl),
					   PCI_HOTPLUG_LINK_DOWN);
		}
		if (events & PCI_EXP_SLTSTA_PDC) {
			ctrl_info(ctrl, "Slot(%s): Card not present\n",
				  slot_name(ctrl));
			trace_pci_hp_event(pci_name(ctrl->pcie->port),
					   slot_name(ctrl),
					   PCI_HOTPLUG_CARD_NOT_PRESENT);
		}
		pciehp_disable_slot(ctrl, SURPRISE_REMOVAL);
		break;
	default:
		mutex_unlock(&ctrl->state_lock);
		break;
	}
```

A slot in [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138), or in [`BLINKINGOFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L135) with its button work cancelled, goes to [`POWEROFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L137) whatever the card did. The comment at [`pciehp_ctrl.c:236-238`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L236) gives the reason: even if the slot is occupied again, the kernel cannot assume the card is the same. Before the disable path runs, the handler logs each event. It records Data Link Layer State Changed as [`PCI_HOTPLUG_LINK_DOWN`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci.h#L44) and Presence Detect Changed as [`PCI_HOTPLUG_CARD_NOT_PRESENT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci.h#L46), two values of [`enum pci_hotplug_event`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci.h#L42) in the UAPI header:

```c
/* include/uapi/linux/pci.h:42 */
enum pci_hotplug_event {
	PCI_HOTPLUG_LINK_UP,
	PCI_HOTPLUG_LINK_DOWN,
	PCI_HOTPLUG_CARD_PRESENT,
	PCI_HOTPLUG_CARD_NOT_PRESENT,
};
```

The enum numbers the four events the hotplug tracepoint can record, and the tracepoint maps each to a string, which the closing subsections show. The second stage of the handler re-checks the slot after the disable path returns, and a later subsection reads it.

Both handlers have now set [`POWEROFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L137) and called [`pciehp_disable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L378), one with [`SAFE_REMOVAL`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L31) and the other with [`SURPRISE_REMOVAL`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L32).

### The disable path wakes the port and checks slot power

The two handlers share one disable path, which wraps the removal in a runtime-PM reference on the hotplug port and removes nothing from a slot whose power is already off. Whether the slot has power to check depends on its capabilities, which [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) cached in [`slot_cap`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L95) and which pciehp.h tests through [`ATTN_BUTTN()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L156), [`POWER_CTRL()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L157) and their neighbours:

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

[`POWER_CTRL()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L157) is nonzero when the slot has a power controller, and [`PWR_LED()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L160) and [`ATTN_LED()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L159) are nonzero when it has the two indicators. A slot without any of them still has its functions removed. [`pciehp_disable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L378) and its inner [`__pciehp_disable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L361) follow each other in pciehp_ctrl.c; read them together for the order of the power check, the removal and the final state.

```c
/* drivers/pci/hotplug/pciehp_ctrl.c:361 */
static int __pciehp_disable_slot(struct controller *ctrl, bool safe_removal)
{
	u8 getstatus = 0;

	if (POWER_CTRL(ctrl)) {
		pciehp_get_power_status(ctrl, &getstatus);
		if (!getstatus) {
			ctrl_info(ctrl, "Slot(%s): Already disabled\n",
				  slot_name(ctrl));
			return -EINVAL;
		}
	}

	remove_board(ctrl, safe_removal);
	return 0;
}

static int pciehp_disable_slot(struct controller *ctrl, bool safe_removal)
{
	int ret;

	pm_runtime_get_sync(&ctrl->pcie->port->dev);
	ret = __pciehp_disable_slot(ctrl, safe_removal);
	pm_runtime_put(&ctrl->pcie->port->dev);

	mutex_lock(&ctrl->state_lock);
	ctrl->state = OFF_STATE;
	mutex_unlock(&ctrl->state_lock);

	return ret;
}
```

The inner function returns -EINVAL with the message "Already disabled" when the slot has a power controller whose power reads as off, and otherwise calls [`remove_board()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L112) at [`pciehp_ctrl.c:374`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L374). The outer function takes a runtime-PM reference that resumes the port around the inner one and then sets [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) whatever the result, so the slot leaves [`POWEROFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L137) on every return. The power check reads Power Controller Control back from the port in [`pciehp_get_power_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L395):

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

A [`PCI_EXP_SLTCTL_PCC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L626) bit of 1, [`PCI_EXP_SLTCTL_PWR_OFF`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L628), reads as off and a bit of 0, [`PCI_EXP_SLTCTL_PWR_ON`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L627), as on, and the debug line at [`pciehp_hpc.c:401-402`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L401) prints the Slot Control value it read.

The slot is now known to have power, or to have no power controller, and [`remove_board()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L112) runs with the boolean its handler chose.

### remove_board removes the functions before it cuts power

[`remove_board()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L112) is where the card leaves the kernel, and its order is the point: the functions go first, while the slot still has power, and slot power and the Power Indicator go after them. In the v7.2 tree, pciehp_ctrl.c calls this pciehp version only from [`__pciehp_disable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L361), shown above. Read it whole, with the kerneldoc that names its boolean.

```c
/* drivers/pci/hotplug/pciehp_ctrl.c:107 */
/**
 * remove_board - Turn off slot and Power Indicator
 * @ctrl: PCIe hotplug controller where board is being removed
 * @safe_removal: whether the board is safely removed (versus surprise removed)
 */
static void remove_board(struct controller *ctrl, bool safe_removal)
{
	pciehp_unconfigure_device(ctrl, safe_removal);

	if (POWER_CTRL(ctrl)) {
		pciehp_power_off_slot(ctrl);

		/*
		 * After turning power off, we must wait for at least 1 second
		 * before taking any action that relies on power having been
		 * removed from the slot/adapter.
		 */
		msleep(1000);

		/* Ignore link or presence changes caused by power off */
		atomic_and(~(PCI_EXP_SLTSTA_DLLSC | PCI_EXP_SLTSTA_PDC),
			   &ctrl->pending_events);
	}

	pciehp_set_indicators(ctrl, PCI_EXP_SLTCTL_PWR_IND_OFF,
			      INDICATOR_NOOP);

	/* Don't carry LBMS indications across */
	pcie_reset_lbms(ctrl->pcie->port);
}
```

[`pciehp_unconfigure_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_pci.c#L95) at [`pciehp_ctrl.c:114`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L114) removes every function below the port, receiving the parameter `safe_removal` of [`remove_board()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L112) as its own parameter `presence`. With a power controller, [`pciehp_power_off_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L559) cuts power, msleep(1000) waits the second the comment requires, and atomic_and() drops from [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104) the link and presence changes the power-off caused. [`pciehp_set_indicators()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L513) then turns the Power Indicator off, and [`pcie_reset_lbms()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/bwctrl.c#L242) clears the link's bandwidth record. The figure shows that order on one slot's time line.

```text
    The order of a removal on one slot: functions first, then power, then light
    ───────────────────────────────────────────────────────────────────────────

                                         functions    PCC = off    1 s later,     PIC = off
                                          removed      written   events dropped    written
                                             ┆            ┆             ┆             ┆
    functions on the card   █████████████████┆            ┆             ┆             ┆
    slot power              ██████████████████████████████┆▒▒▒▒▒▒▒▒▒▒▒▒▒┆             ┆
    DLLSC and PDC saved                      ┆            ┆░░░░░░░░░░░░░┆             ┆
    Power Indicator on      ██████████████████████████████████████████████████████████┆
                            time ─────────────────────────────────────────────────────────────▶

    █ present, on or lit    ▒ the one-second wait after the power-off command
    ░ link and presence changes the power-off causes, which the hard handler may save
    the power steps need PCP in Slot Capabilities, the indicator step needs PIP
```

The functions are gone before the power-off command is written, and the Power Indicator goes dark only after the one-second wait and the dropped events. A slot without [`PCI_EXP_SLTCAP_PCP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L599) has no power controller, and its removal goes from the functions straight to the indicator.

So far, the slot is in [`POWEROFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L137), and the IRQ thread holds the read side of [`reset_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114). [`remove_board()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L112) is about to remove the card's functions, told by its boolean whether the card is still in the slot.

### A surprise removal marks every function below the port disconnected

When a card leaves without warning, its functions no longer answer, yet their drivers still run until the removal unbinds them, and a driver's remove callback may touch the hardware. pciehp therefore marks every function below the port as permanently failed before any driver is unbound, so code that tests the mark can skip the dead hardware. [`pciehp_unconfigure_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_pci.c#L95) does the marking first and the removal after it, in three stages that the table outlines.

| piece | lines | stage |
|---|---|---|
| ❶ | pciehp_pci.c:95-106 | names the secondary bus and, on a surprise removal, marks every function below the port disconnected |
| ❷ | pciehp_pci.c:107-126 | takes the rescan-remove mutex and stops and removes each function with the reset lock released |
| ❸ | pciehp_pci.c:127-141 | quiesces the Command register of a function still in the slot, drops the reference and releases the mutex |

Piece ❶ of [`pciehp_unconfigure_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_pci.c#L95), with its kerneldoc, finds the secondary bus and marks it on a surprise removal.

```c
/* drivers/pci/hotplug/pciehp_pci.c:84 */
/**
 * pciehp_unconfigure_device() - remove PCI devices below a hotplug bridge
 * @ctrl: PCIe hotplug controller
 * @presence: whether the card is still present in the slot;
 *	true for safe removal via sysfs or an Attention Button press,
 *	false for surprise removal
 *
 * Unbind PCI devices below a hotplug bridge from their drivers and remove
 * them from the system.  Safely removed devices are quiesced.  Surprise
 * removed devices are marked as such to prevent further accesses.
 */
void pciehp_unconfigure_device(struct controller *ctrl, bool presence)
{
	struct pci_dev *dev, *temp;
	struct pci_bus *parent = ctrl->pcie->port->subordinate;
	u16 command;

	ctrl_dbg(ctrl, "%s: domain:bus:dev = %04x:%02x:00\n",
		 __func__, pci_domain_nr(parent), parent->number);

	if (!presence)
		pci_walk_bus(parent, pci_dev_set_disconnected, NULL);

```

The secondary bus is the port's [`subordinate`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L355), held in the local `parent`, and the debug line names it by domain and bus number. When the parameter `presence` is false, the surprise case, [`pci_walk_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/bus.c#L461) calls [`pci_dev_set_disconnected()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L759) on every function of that bus and of the buses below it, before the mutex of the next line. [`pci_walk_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/bus.c#L461) is the PCI core's traversal of a subtree; read its entry point for the lock it holds and the callback rule its kerneldoc states.

```c
/* drivers/pci/bus.c:448 */
/**
 *  pci_walk_bus - walk devices on/under bus, calling callback.
 *  @top: bus whose devices should be walked
 *  @cb: callback to be called for each device found
 *  @userdata: arbitrary pointer to be passed to callback
 *
 *  Walk the given bus, including any bridged devices
 *  on buses under this bus.  Call the provided callback
 *  on each device found.
 *
 *  We check the return of @cb each time. If it returns anything
 *  other than 0, we break out.
 */
void pci_walk_bus(struct pci_bus *top, int (*cb)(struct pci_dev *, void *), void *userdata)
{
	down_read(&pci_bus_sem);
	__pci_walk_bus(top, cb, userdata);
	up_read(&pci_bus_sem);
}
```

The entry point holds [`pci_bus_sem`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/search.c#L17) for reading, so no function joins or leaves a bus list during the traversal, and a nonzero return from the callback ends it. The recursion is [`__pci_walk_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/bus.c#L408), which visits a function and then descends into the bus behind it:

```c
/* drivers/pci/bus.c:408 */
static int __pci_walk_bus(struct pci_bus *top, int (*cb)(struct pci_dev *, void *),
			  void *userdata)
{
	struct pci_dev *dev;
	int ret = 0;

	list_for_each_entry(dev, &top->devices, bus_list) {
		ret = cb(dev, userdata);
		if (ret)
			break;
		if (dev->subordinate) {
			ret = __pci_walk_bus(dev->subordinate, cb, userdata);
			if (ret)
				break;
		}
	}
	return ret;
}
```

Each function is visited before the functions behind it, and the traversal stops only on a nonzero return, which [`pci_dev_set_disconnected()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L759) never gives. The port itself is not visited, because the traversal starts at the port's secondary bus. [`pci_dev_set_disconnected()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L759) sets the error state through [`pci_dev_set_io_state()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L737), which drivers/pci/pci.h defines just above it; read both:

```c
/* drivers/pci/pci.h:726 */
/**
 * pci_dev_set_io_state - Set the new error state if possible.
 *
 * @dev: PCI device to set new error_state
 * @new: the state we want dev to be in
 *
 * If the device is experiencing perm_failure, it has to remain in that state.
 * Any other transition is allowed.
 *
 * Returns true if state has been changed to the requested state.
 */
static inline bool pci_dev_set_io_state(struct pci_dev *dev,
					pci_channel_state_t new)
{
	pci_channel_state_t old;

	switch (new) {
	case pci_channel_io_perm_failure:
		xchg(&dev->error_state, pci_channel_io_perm_failure);
		return true;
	case pci_channel_io_frozen:
		old = cmpxchg(&dev->error_state, pci_channel_io_normal,
			      pci_channel_io_frozen);
		return old != pci_channel_io_perm_failure;
	case pci_channel_io_normal:
		old = cmpxchg(&dev->error_state, pci_channel_io_frozen,
			      pci_channel_io_normal);
		return old != pci_channel_io_perm_failure;
	default:
		return false;
	}
}

static inline int pci_dev_set_disconnected(struct pci_dev *dev, void *unused)
{
	pci_dev_set_io_state(dev, pci_channel_io_perm_failure);
	pci_doe_disconnected(dev);

	return 0;
}
```

For [`pci_channel_io_perm_failure`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L216), [`pci_dev_set_io_state()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L737) stores the state with xchg() whatever the old state was. Its comment says a function in that state has to remain in it, and the two cmpxchg() arms enforce that for the other states, which error recovery requests. After writing [`error_state`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L445), the callback cancels the work of the function's DOE mailboxes through [`pci_doe_disconnected()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L686), whose two forms drivers/pci/pci.h selects by [`CONFIG_PCI_DOE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L142):

```c
/* drivers/pci/pci.h:679 */
#ifdef CONFIG_PCI_DOE
void pci_doe_init(struct pci_dev *pdev);
void pci_doe_destroy(struct pci_dev *pdev);
void pci_doe_disconnected(struct pci_dev *pdev);
#else
static inline void pci_doe_init(struct pci_dev *pdev) { }
static inline void pci_doe_destroy(struct pci_dev *pdev) { }
static inline void pci_doe_disconnected(struct pci_dev *pdev) { }
#endif
```

With [`CONFIG_PCI_DOE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L142) unset, as the x86_64 defconfig leaves it, the call compiles to the empty stub. With the option set, it cancels the pending tasks of each mailbox the function has. The figure shows which functions the marking reaches, and in what order, for a card that carries a switch.

```text
    What a surprise removal marks disconnected: the subtree below the port, in visit order
    ──────────────────────────────────────────────────────────────────────────────────────

    ┌───────────────────────────────────┐
    │ 00:1c.0  the hotplug port         │  not visited, stays usable
    └─────────────────┬─────────────────┘
    ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄│┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄ the walk starts at the port's subordinate bus
                      ▼ bus 01
    ┌───────────────────────────────────┐
    │ [1] 01:00.0  Switch Upstream Port │
    └─────────────────┬─────────────────┘
                      │ bus 02
          ┌───────────┴──────────────────────────────┐
          ▼                                          ▼
    ┌───────────────────────────────────┐   ┌───────────────────────────────────┐
    │ [2] 02:00.0  Downstream Port      │   │ [4] 02:01.0  Downstream Port      │
    └─────────────────┬─────────────────┘   └─────────────────┬─────────────────┘
                      ▼ bus 03                                ▼ bus 04
    ┌───────────────────────────────────┐   ┌───────────────────────────────────┐
    │ [3] 03:00.0  Endpoint             │   │ [5] 04:00.0  Endpoint             │
    └───────────────────────────────────┘   └───────────────────────────────────┘

    [n] the visit order: a function, then everything on the bus behind it, then the next function
    every function below the dashed line leaves with error_state = pci_channel_io_perm_failure
```

Every function below the dashed line ends with [`error_state`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L445) equal to [`pci_channel_io_perm_failure`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L216), and the port above it keeps answering. An orderly removal skips the marking, because its functions are still in the slot and piece ❸ quiesces them. The same marking runs at resume for a card swapped while the system slept, in [`pciehp_resume_noirq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L288), which [`CONFIG_PM_SLEEP`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L140) builds:

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

After the marking at [`pciehp_core.c:308-309`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L308), the requested Presence Detect Changed moves the slot from [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) to [`POWEROFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L137), and [`remove_board()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L112) runs with [`SURPRISE_REMOVAL`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L32). The comment gives the purpose: the old card's driver is kept from accessing the new device.

After piece ❶, every function of a surprise-removed card carries the permanent failure state, and none has been unbound yet.

### Drivers test the disconnected state while they unbind

The mark helps only where code tests it. The PCI core tests it before it touches a function, and a class driver can test it in its remove callback, which runs while the removal unbinds the driver. The test is [`pci_dev_is_disconnected()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2702), an inline of include/linux/pci.h:

```c
/* include/linux/pci.h:2702 */
static inline bool pci_dev_is_disconnected(const struct pci_dev *dev)
{
	/*
	 * error_state is set in pci_dev_set_io_state() using xchg/cmpxchg()
	 * and read w/o common lock. READ_ONCE() ensures compiler cannot cache
	 * the value (e.g. inside the loop in pci_dev_wait()).
	 */
	return READ_ONCE(dev->error_state) == pci_channel_io_perm_failure;
}
```

The test reads [`error_state`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L445) with READ_ONCE() and no lock, which its comment justifies by the atomic writes of [`pci_dev_set_io_state()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L737). [`pci_device_is_present()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L6327) builds on it and answers false for a marked function without a configuration read:

```c
/* drivers/pci/pci.c:6327 */
bool pci_device_is_present(struct pci_dev *pdev)
{
	u32 v;

	/* Check PF if pdev is a VF, since VF Vendor/Device IDs are 0xffff */
	pdev = pci_physfn(pdev);
	if (pci_dev_is_disconnected(pdev))
		return false;
	return pci_bus_read_dev_vendor_id(pdev->bus, pdev->devfn, &v, 0);
}
EXPORT_SYMBOL_GPL(pci_device_is_present);
```

A function without the mark is asked for its Vendor ID instead, which only a function still in the slot answers. The NVMe driver's remove callback, [`nvme_remove()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/nvme/host/pci.c#L3886), uses the answer to decide whether it may still talk to its controller:

```c
/* drivers/nvme/host/pci.c:3886 */
static void nvme_remove(struct pci_dev *pdev)
{
	struct nvme_dev *dev = pci_get_drvdata(pdev);

	nvme_change_ctrl_state(&dev->ctrl, NVME_CTRL_DELETING);
	pci_set_drvdata(pdev, NULL);

	if (!pci_device_is_present(pdev)) {
		nvme_change_ctrl_state(&dev->ctrl, NVME_CTRL_DEAD);
		nvme_dev_disable(dev, true);
	}

	flush_work(&dev->ctrl.reset_work);
	nvme_stop_ctrl(&dev->ctrl);
	nvme_remove_namespaces(&dev->ctrl);
	nvme_dev_disable(dev, true);
	nvme_free_host_mem(dev);
	nvme_dev_remove_admin(dev);
	nvme_dbbuf_dma_free(dev);
	nvme_free_queues(dev, 0);
	mempool_destroy(dev->dmavec_mempool);
	nvme_release_descriptor_pools(dev);
	nvme_dev_unmap(dev);
	nvme_uninit_ctrl(&dev->ctrl);
}
```

When the function is gone, [`nvme_remove()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/nvme/host/pci.c#L3886) moves its controller to `NVME_CTRL_DEAD` and disables it before the rest of the teardown. The marking of piece ❶ is what lets [`pci_device_is_present()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L6327) give that answer on a surprise removal without touching the bus.

A surprise removal thus tells the drivers before it unbinds them, and piece ❷ takes each function out of the kernel.

### The rescan-remove mutex brackets the removal of every function

Removing functions changes the bus lists that a rescan also changes, and the PCI core serializes the two with one global mutex. pciehp takes it after the marking and holds it across the removal of every function on the secondary bus. The bracket is [`pci_lock_rescan_remove()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L3512) and [`pci_unlock_rescan_remove()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L3518), defined in drivers/pci/probe.c beside [`pci_rescan_remove_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L3510), the mutex they wrap:

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

[`pci_rescan_remove_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L3510) is a plain mutex, and its comment asks that the rescan functions and the device removal routines run under it. Both helpers are exported to GPL modules, so drivers outside the PCI core can take the same bracket. Piece ❷ of [`pciehp_unconfigure_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_pci.c#L95) takes the mutex and removes each function of the secondary bus, starting from the end of its list.

```c
/* drivers/pci/hotplug/pciehp_pci.c:107 */
	pci_lock_rescan_remove();

	/*
	 * Stopping an SR-IOV PF device removes all the associated VFs,
	 * which will update the bus->devices list and confuse the
	 * iterator.  Therefore, iterate in reverse so we remove the VFs
	 * first, then the PF.  We do the same in pci_stop_bus_device().
	 */
	list_for_each_entry_safe_reverse(dev, temp, &parent->devices,
					 bus_list) {
		pci_dev_get(dev);

		/*
		 * Release reset_lock during driver unbinding
		 * to avoid AB-BA deadlock with device_lock.
		 */
		up_read(&ctrl->reset_lock);
		pci_stop_and_remove_bus_device(dev);
		down_read_nested(&ctrl->reset_lock, ctrl->depth);

```

The loop runs over [`devices`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L706) of the secondary bus in reverse with list_for_each_entry_safe_reverse(), and the comment gives the reason: stopping one function can delete other entries of the same list. pci_dev_get() at [`pciehp_pci.c:117`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_pci.c#L117) keeps the object valid after its removal, for piece ❸. Around [`pci_stop_and_remove_bus_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/remove.c#L125) the thread releases the read side of [`reset_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114) and retakes it afterwards, because unbinding takes the function's device_lock and a slot reset takes the two locks in the other order.

commit [f5eff5591b8f](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=f5eff5591b8f9c5effd25c92c758a127765f74c1) ("PCI: pciehp: Fix AB-BA deadlock between reset_lock and device_lock") split the locked region this way. According to its message, a reset path that held device_lock and a removal that held reset_lock while unbinding had deadlocked. The figure shows the locks held through the removal of two functions.

```text
    The locks held around a removal, function by function
    ─────────────────────────────────────────────────────

                                  disconnect    function 1                  function 2
                                  walk       stop, remove  Command       stop, remove  Command

    reset_lock, read side       ├─────────────┤            ├──────────────┤            ├──────────────┤
    device_lock, unbinding                     ├────┤                      ├────┤
    pci_bus_sem                   ├────────┤         ├───┤                       ├───┤
    pci_rescan_remove_lock                   ├──────────────────────────────────────────────────────┤
    reference on the function                 ├───────────────────────┤  ├────────────────────────┤
                                time ────────────────────────────────────────────────────────────────▶

    The IRQ thread enters holding the read side of reset_lock and drops it only around the stop
    and remove of each function. pci_bus_sem is held for reading by the disconnect walk of a
    surprise removal and for writing while a removed function is unlinked from its bus.
    Command is the quiesce of a safe removal, written after the function was stopped and removed.
```

The read side of [`reset_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114) opens and closes inside the bracket, while [`pci_rescan_remove_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L3510) stays held from before the first function to after the last. A slot reset that asks for the write side can therefore run while a function is being unbound, which a later subsection takes up.

### The PCI core stops a subtree before it removes it

A function on the secondary bus may be a bridge with more buses and functions behind it, as a card with a switch is. The PCI core removes such a subtree in two passes, so every driver below is unbound before any object goes away. [`pci_stop_and_remove_bus_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/remove.c#L125) is the entry point, and its kerneldoc describes both passes:

```c
/* drivers/pci/remove.c:113 */
/**
 * pci_stop_and_remove_bus_device - remove a PCI device and any children
 * @dev: the device to remove
 *
 * Remove a PCI device from the device lists, informing the drivers
 * that the device has been removed.  We also remove any subordinate
 * buses and children in a depth-first manner.
 *
 * For each device we remove, delete the device structure from the
 * device lists, remove the /proc entry, and notify userspace
 * (/sbin/hotplug).
 */
void pci_stop_and_remove_bus_device(struct pci_dev *dev)
{
	lockdep_assert_held(&pci_rescan_remove_lock);
	pci_stop_bus_device(dev);
	pci_remove_bus_device(dev);
}
EXPORT_SYMBOL(pci_stop_and_remove_bus_device);
```

The lockdep assertion states the requirement that callers hold [`pci_rescan_remove_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L3510), which piece ❷ meets. The stop pass is [`pci_stop_bus_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/remove.c#L76) and the remove pass [`pci_remove_bus_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/remove.c#L96); read them as they follow each other in remove.c.

```c
/* drivers/pci/remove.c:76 */
static void pci_stop_bus_device(struct pci_dev *dev)
{
	struct pci_bus *bus = dev->subordinate;
	struct pci_dev *child, *tmp;

	/*
	 * Stopping an SR-IOV PF device removes all the associated VFs,
	 * which will update the bus->devices list and confuse the
	 * iterator.  Therefore, iterate in reverse so we remove the VFs
	 * first, then the PF.
	 */
	if (bus) {
		list_for_each_entry_safe_reverse(child, tmp,
						 &bus->devices, bus_list)
			pci_stop_bus_device(child);
	}

	pci_stop_dev(dev);
}

static void pci_remove_bus_device(struct pci_dev *dev)
{
	struct pci_bus *bus = dev->subordinate;
	struct pci_dev *child, *tmp;

	if (bus) {
		list_for_each_entry_safe(child, tmp,
					 &bus->devices, bus_list)
			pci_remove_bus_device(child);

		pci_remove_bus(bus);
		dev->subordinate = NULL;
	}

	pci_destroy_dev(dev);
}
```

The stop pass recurses into a bridge's [`subordinate`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L355) bus from the end of its [`devices`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L706) list and stops each function after the functions below it. The remove pass recurses in list order, removes each bus after the functions on it, and destroys a bridge after its bus. The two steps per function, [`pci_stop_dev()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/remove.c#L20) and [`pci_destroy_dev()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/remove.c#L32), open remove.c:

```c
/* drivers/pci/remove.c:20 */
static void pci_stop_dev(struct pci_dev *dev)
{
	pci_pme_active(dev, false);

	if (!pci_dev_test_and_clear_added(dev))
		return;

	device_release_driver(&dev->dev);
	pci_proc_detach_device(dev);
	of_pci_remove_node(dev);
}

static void pci_destroy_dev(struct pci_dev *dev)
{
	if (pci_dev_test_and_set_removed(dev))
		return;

	pci_doe_sysfs_teardown(dev);
	pci_npem_remove(dev);

	/*
	 * While device is in D0 drop the device from TSM link operations
	 * including unbind and disconnect (IDE + SPDM teardown).
	 */
	pci_tsm_destroy(dev);

	device_del(&dev->dev);

	down_write(&pci_bus_sem);
	list_del(&dev->bus_list);
	up_write(&pci_bus_sem);

	pci_doe_destroy(dev);
	pci_ide_destroy(dev);
	pcie_aspm_exit_link_state(dev);
	pci_bridge_d3_update(dev);
	pci_free_resources(dev);
	put_device(&dev->dev);
}
```

[`pci_stop_dev()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/remove.c#L20) unbinds the driver with device_release_driver(), which runs the driver's remove callback, and removes the /proc entry, but only for the caller that clears [`PCI_DEV_ADDED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L768). [`pci_destroy_dev()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/remove.c#L32) lets one caller through by setting [`PCI_DEV_REMOVED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L771) and tears down the optional per-function services. It then unregisters the embedded device, unlinks the function from its bus under [`pci_bus_sem`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/search.c#L17), and releases its resources before put_device() drops the scan's reference. Both bits belong to [`priv_flags`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L585), whose bit numbers drivers/pci/pci.h defines:

```c
/* drivers/pci/pci.h:767 */
/* pci_dev priv_flags */
#define PCI_DEV_ADDED 0
#define PCI_DPC_RECOVERED 1
#define PCI_DPC_RECOVERING 2
#define PCI_DEV_REMOVED 3
#define PCI_LINK_CHANGED 4
#define PCI_LINK_CHANGING 5
#define PCI_LINK_LBMS_SEEN	6
#define PCI_DEV_ALLOW_BINDING 7
```

The removal tests [`PCI_DEV_ADDED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L768) and [`PCI_DEV_REMOVED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L771) through [`pci_dev_test_and_clear_added()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L784) and [`pci_dev_test_and_set_removed()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L794), defined a few lines below with the plain test between them:

```c
/* drivers/pci/pci.h:784 */
static inline bool pci_dev_test_and_clear_added(struct pci_dev *dev)
{
	return test_and_clear_bit(PCI_DEV_ADDED, &dev->priv_flags);
}

static inline bool pci_dev_is_added(const struct pci_dev *dev)
{
	return test_bit(PCI_DEV_ADDED, &dev->priv_flags);
}

static inline bool pci_dev_test_and_set_removed(struct pci_dev *dev)
{
	return test_and_set_bit(PCI_DEV_REMOVED, &dev->priv_flags);
}
```

test_and_clear_bit() and test_and_set_bit() return the old value, so of two racing removals of one function only the first unbinds it and only the first destroys it. [`pci_dev_is_added()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L789) is the plain test that other paths use. The figure shows one subtree before and after the two passes.

```text
    The secondary bus before and after its one top-level function is stopped and removed
    ────────────────────────────────────────────────────────────────────────────────────

    before      [s n] the order of the stop pass, [r n] the order of the remove pass
    bus 01, the port's secondary bus
      devices ──▶ 01:00.0 [s5 r5]
                    │ subordinate: bus 02
                    ├──▶ 02:00.0 [s4 r2] ── subordinate: bus 03 ──▶ 03:00.0 [s3 r1]
                    └──▶ 02:01.0 [s2 r4] ── subordinate: bus 04 ──▶ 04:00.0 [s1 r3]

    after
    bus 01, the port's secondary bus
      devices ──▶ (empty)
                    · buses 02, 03 and 04: unregistered and off their parents' lists
                    · functions 01:00.0 to 04:00.0: unbound, unregistered, off devices,
                      resources released, the scan's reference dropped

    The stop pass goes deepest first from the end of each devices list; the remove pass goes
    deepest first in list order and removes each bus after the functions on it.
```

Bus 01 stays, because it is the port's secondary bus and belongs to the port, while the buses behind the card's bridges go with them. The strip follows one removed function's own fields through the same steps.

```text
    One removed function's struct pci_dev, field by field through the removal
    ─────────────────────────────────────────────────────────────────────────

                     enumerated       disconnect walk     stop pass         remove pass
                     and added        (surprise only)
    error_state      io_normal ──────── ① perm_failure ─────────────────────────────────────▶
    PCI_DEV_ADDED    set ───────────────────────────────── ② cleared ───────────────────────▶
    PCI_DEV_REMOVED  clear ──────────────────────────────────────────────── ③ set ──────────▶
    bus_list         on devices ─────────────────────────────────────────── ④ unlinked ─────▶

    error_state and the two priv_flags bits are words of the function; bus_list links it into
    its bus's devices list.  A safe removal skips ①, so error_state stays io_normal.

    ① pci_dev_set_io_state drivers/pci/pci.h:744  xchg() stores the permanent failure state
    ② pci_stop_dev drivers/pci/remove.c:24  pci_dev_test_and_clear_added() clears the bit once
    ③ pci_destroy_dev :34  pci_dev_test_and_set_removed() sets the bit once
    ④ pci_destroy_dev :49  list_del() unlinks the function from its bus
```

At ① [`pci_dev_set_io_state()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L737) stores [`pci_channel_io_perm_failure`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L216) in [`error_state`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L445), on a surprise removal only. At ② [`pci_stop_dev()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/remove.c#L20) clears [`PCI_DEV_ADDED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L768) through [`pci_dev_test_and_clear_added()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L784) before it unbinds the driver. At ③ [`pci_destroy_dev()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/remove.c#L32) sets [`PCI_DEV_REMOVED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L771) through [`pci_dev_test_and_set_removed()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L794). At ④ the same function unlinks [`bus_list`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L353) from the bus with list_del(). The writers the page does not show set the starting values when a function is added, which is why they stay out of this page. [`pci_setup_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2016) in probe.c writes [`pci_channel_io_normal`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L210), [`pci_alloc_dev()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2500) and [`pci_device_add()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2726) in probe.c initialize and link [`bus_list`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L353), and [`pci_dev_assign_added()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L777) in drivers/pci/pci.h sets [`PCI_DEV_ADDED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L768) for [`pci_bus_add_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/bus.c#L345). Error recovery writes the frozen and normal states through the other arms of the same helper, and outside x86 architecture error-recovery code writes the field directly; none of them runs on this path.

### An orderly removal silences each function after removing it

An orderly removal leaves the card in the slot and powered until the power-off command, so its functions could still issue requests after their drivers are gone. commit [2326e2b99969](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=2326e2b99969e69fedc92de80d80b2d2f92fd942) ("pciehp: block new requests from the device before power off") added a quiesce for that window, citing the specification. Piece ❸ of [`pciehp_unconfigure_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_pci.c#L95) performs it after each function's removal and closes the bracket.

```c
/* drivers/pci/hotplug/pciehp_pci.c:127 */
		/*
		 * Ensure that no new Requests will be generated from
		 * the device.
		 */
		if (presence) {
			pci_read_config_word(dev, PCI_COMMAND, &command);
			command &= ~(PCI_COMMAND_MASTER | PCI_COMMAND_SERR);
			command |= PCI_COMMAND_INTX_DISABLE;
			pci_write_config_word(dev, PCI_COMMAND, command);
		}
		pci_dev_put(dev);
	}

	pci_unlock_rescan_remove();
}
```

For a card still in the slot, with the parameter `presence` true, the loop reads the function's Command register, [`PCI_COMMAND`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L40). It clears [`PCI_COMMAND_MASTER`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L43) and [`PCI_COMMAND_SERR`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L49), sets [`PCI_COMMAND_INTX_DISABLE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L51) and writes the value back, which the comment says keeps the function from generating new requests. The write goes to a function whose object was already removed, which the reference from piece ❷ keeps valid until pci_dev_put() at [`pciehp_pci.c:137`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_pci.c#L137). A surprise removal skips the register, and after the last function [`pci_unlock_rescan_remove()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L3518) releases the mutex.

So far, every function below the port is unbound, unlisted and released, and the rescan-remove mutex is free again. The functions of a surprise-removed card are marked permanently failed, those of a card still in the slot are quiesced, and slot power is still on.

### Slot power goes off after the functions are gone

With the functions gone, nothing below the port depends on slot power, and [`remove_board()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L112) turns it off when the slot has a power controller. The power-off is one Slot Control command, and like every command it waits for the previous one and for its own completion. [`pciehp_power_off_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L559) issues it:

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

The command writes [`PCI_EXP_SLTCTL_PWR_OFF`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L628) under the mask [`PCI_EXP_SLTCTL_PCC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L626), so only Power Controller Control changes, and the debug line reports the register's offset and the command. [`pcie_write_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L213) is the waiting form of the command writer; read it with its kerneldoc.

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
```

[`pcie_do_write_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L157) does the work. Read its stage that waits, merges the command into the register and writes it, and its stage that waits for completion. The folded lines clear the busy flag early on ports whose Command Completed reporting is unreliable, a quirk this page does not follow.

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
	... /* 12 lines, to :196 */
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

Under [`ctrl_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L99), the writer waits for any command still in progress, reads Slot Control, replaces the masked bits and writes the result, recording it in [`slot_ctrl`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L98) and the time in [`cmd_started`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L100). A port that answers with all ones is logged as "no response from device" and gets no write. With the parameter `wait` true, the writer then waits again, until the hard handler sees Command Completed and clears [`cmd_busy`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L101), as the first subsection showed.

The power-off can itself cause events, since a card without power drops its link and may stop reporting presence. [`remove_board()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L112) deals with them after its wait; read those lines again.

```c
/* drivers/pci/hotplug/pciehp_ctrl.c:112 */
static void remove_board(struct controller *ctrl, bool safe_removal)
{
		... /* 10 lines, to :124 */
		msleep(1000);

		/* Ignore link or presence changes caused by power off */
		atomic_and(~(PCI_EXP_SLTSTA_DLLSC | PCI_EXP_SLTSTA_PDC),
			   &ctrl->pending_events);
```

After msleep(1000), atomic_and() clears [`PCI_EXP_SLTSTA_DLLSC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L642) and [`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637) from [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104), where the hard handler may have saved them during the wait. commit [3943af9d01e9](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=3943af9d01e94330d0cfac6fccdbc829aad50c92) ("PCI: pciehp: Ignore Link State Changes after powering off a slot") added the clearing; according to its message, the link change of a safe removal otherwise re-enabled the device. The figure shows the command, its completion and the dropped events across the three parties.

```text
    Slot power goes off: the command, its completion, and the events the power-off causes
    ─────────────────────────────────────────────────────────────────────────────────────

    IRQ thread, removal path                  hotplug port                    hard handler
                │                                   │                               │
                │ Slot Control read, PCC set        │                               │
                ├──────────────────────────────────▶│                               │
                │ cmd_busy = 1, waits on queue      │ slot power off                │
                │                                   │ Command Completed,            │
                │                                   │ then DLLSC or PDC             │
                │                                   ├──────────────────────────────▶│
                │                                   │                               │ CC: cmd_busy = 0, wakes queue
                │                                   │                               │ saves DLLSC, PDC to pending_events
                │◀───────────────────────────────── │ ──────────────────────────────┤
                │ woken; sleeps one second          │                               │
                │ DLLSC, PDC cleared from pending   │                               │
                │ Slot Control PIC = off, no wait   │                               │
                ├──────────────────────────────────▶│                               │
                │                                   │ Power Indicator off           │
                ▼                                   ▼                               ▼

    Time runs down. The arrow from the hard handler passes the port's line without touching it.
    Without PCP in Slot Capabilities the slot has no power controller, and only the last write runs.
```

Command Completed reaches the thread through [`queue`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L102) while it waits, and the link and presence changes reach only [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104), which the thread clears of them before its next run. A card removed in order stays in the slot without power until a request turns the slot on again.

### The indicators report the removal on the slot

The indicators tell a person at the machine what the slot is doing, so a removal ends by turning the Power Indicator off, and a failed add lights the Attention Indicator. Both go through one helper, which leaves an indicator unchanged when its argument is [`INDICATOR_NOOP`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L181), defined beside the helper's prototype:

```c
/* drivers/pci/hotplug/pciehp.h:181 */
#define INDICATOR_NOOP -1	/* Leave indicator unchanged */
void pciehp_set_indicators(struct controller *ctrl, int pwr, int attn);
```

[`pciehp_set_indicators()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L513) builds one Slot Control command for the indicators the slot has and writes it without waiting for completion. Read it whole for the two tests and the empty command.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:513 */
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

Each indicator is written only when [`PWR_LED()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L160) or [`ATTN_LED()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L159) says the slot has it and its argument is a value, and a command with no bits issues no write at all. [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) removes both capabilities from [`slot_cap`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L95) for a port whose [`hotplug_user_indicators`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L425) is set, which leaves that port's indicators to user space. A failed add uses [`set_slot_off()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L34), defined at the top of pciehp_ctrl.c, which powers the slot off like a removal but lights the Attention Indicator:

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

[`set_slot_off()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L34) repeats the power-off and the one-second wait of [`remove_board()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L112) but removes no functions and drops no events, because it runs while a card is being added. In the v7.2 tree its one caller is [`board_added()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L62) of pciehp_ctrl.c, on the error exit; read the start of the add and that exit, with the checks between them folded.

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

	... /* 21 lines, to :98 */
	pciehp_set_indicators(ctrl, PCI_EXP_SLTCTL_PWR_IND_ON,
			      PCI_EXP_SLTCTL_ATTN_IND_OFF);
	return 0;

err_exit:
	set_slot_off(ctrl);
	return retval;
}
```

The add sets the Power Indicator blinking after powering the slot, and a check that fails in the folded lines jumps to `err_exit`, where [`set_slot_off()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L34) turns it off and the Attention Indicator on. The figure puts the indicator values of each removal beside those of a failed add.

```text
    What the slot's two indicators show through each removal, and through a failed add
    ──────────────────────────────────────────────────────────────────────────────────

                                          at the start       in between       at the end
    button press, no second press  Power  on ────────────▶ blinking ────────▶ off
                                   Attn   as it was ─────▶ off ─────────────▶ off
    button press, pressed again    Power  on ────────────▶ blinking ────────▶ on
    within the 5 s                 Attn   as it was ─────▶ off ─────────────▶ off
    sysfs request or surprise      Power  on ─────────────────────────────────▶ off
                                   Attn   as it was ─────────────────────────▶ as it was
    an add that fails              Power  off ───────────▶ blinking ────────▶ off
                                   Attn   as it was ─────────────────────────▶ on

    Power is PIC and Attn is AIC in Slot Control. A slot without PIP or AIP in Slot Capabilities,
    or a port with hotplug_user_indicators set, gets no write for that indicator.
```

A removal turns the Power Indicator off and leaves the Attention Indicator as the last command left it, and the button sequence turns the Attention Indicator off at the press. A failed add is the one sequence here that ends with the Attention Indicator on, through [`set_slot_off()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L34).

### The port forgets the old link's bandwidth events

A port's link records bandwidth events in Link Bandwidth Management Status, [`PCI_EXP_LNKSTA_LBMS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L594), and the PCIe bandwidth controller keeps a sticky copy for a link retraining quirk. A new card in the slot brings a new link, so the last step of [`remove_board()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L112) clears both. [`pcie_reset_lbms()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/bwctrl.c#L242), which [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5) builds in the bandwidth controller, does it:

```c
/* drivers/pci/pcie/bwctrl.c:242 */
void pcie_reset_lbms(struct pci_dev *port)
{
	clear_bit(PCI_LINK_LBMS_SEEN, &port->priv_flags);
	pcie_capability_write_word(port, PCI_EXP_LNKSTA, PCI_EXP_LNKSTA_LBMS);
}
```

The function clears [`PCI_LINK_LBMS_SEEN`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L774) in the port's [`priv_flags`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L585) and writes [`PCI_EXP_LNKSTA_LBMS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L594) to Link Status, which clears the bit in the port. The flag's reader is [`pcie_lbms_seen()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/quirks.c#L40), which the link retraining quirk of quirks.c consults:

```c
/* drivers/pci/quirks.c:40 */
static bool pcie_lbms_seen(struct pci_dev *dev, u16 lnksta)
{
	if (test_bit(PCI_LINK_LBMS_SEEN, &dev->priv_flags))
		return true;

	return lnksta & PCI_EXP_LNKSTA_LBMS;
}
```

Either the sticky flag or the live bit makes [`pcie_lbms_seen()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/quirks.c#L40) true, so clearing both leaves no record of the old link to the quirk. The comment at [`pciehp_ctrl.c:134`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L134) says it in five words: "Don't carry LBMS indications across". With LBMS cleared, [`remove_board()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L112) returns, and the disable path sets the slot's state.

### The slot ends in OFF_STATE and is checked once more

The disable path ends in [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) on every return. A surprise removal can still end with a card in the slot, because the card was put back or because only its link went down. The handler of the Slot Status events therefore looks at the slot once more after the disable path returns. Read the second stage of [`pciehp_handle_presence_or_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L232).

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
```

Under [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110) the handler reads Presence Detect State, [`PCI_EXP_SLTSTA_PDS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L640), and Data Link Layer Link Active, [`PCI_EXP_LNKSTA_DLLLA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L593), through two accessors of the port. An empty slot with no link ends the handling, after a slot still blinking toward power-on is turned off and recorded with [`PCI_HOTPLUG_CARD_NOT_PRESENT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci.h#L46). A slot that is occupied, or whose link is up again, moves from [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) to [`POWERON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L136), and the call at [`pciehp_ctrl.c:309`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L309) starts the add path, which this page does not follow.

An orderly removal reaches the same end without this check, since [`pciehp_handle_disable_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L217) returns after the disable path. Its slot stays in [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) until a request or a new event turns it on, and the IRQ thread releases the read side of [`reset_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114) and finishes its run.

### A slot reset holds reset_lock's write side

A slot reset takes the link to the card down and up while the card stays in the slot, and pciehp implements it in [`pciehp_reset_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L939) as a Secondary Bus Reset of the port. Code that reads Data Link Layer Link Active or Presence Detect State during the reset would see them flap, and [`reset_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114) keeps such code out. The kerneldoc of [`struct controller`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L91) gives the purpose of [`reset_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114) and of [`depth`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L115) at [`pciehp.h:78-82`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L78):

```c
/* drivers/pci/hotplug/pciehp.h:78 */
 * @reset_lock: prevents access to the Data Link Layer Link Active bit in the
 *	Link Status register and to the Presence Detect State bit in the Slot
 *	Status register during a slot reset which may cause them to flap
 * @depth: Number of additional hotplug ports in the path to the root bus,
 *	used as lock subclass for @reset_lock
```

A removal holds the read side and a reset the write side, so neither runs inside the other. The subclass lets lockdep tell the semaphore of one port from that of a hotplug port above it. [`pcie_hotplug_depth()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L992) and the stage of [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) that follows it set up the semaphore with the controller:

```c
/* drivers/pci/hotplug/pciehp_hpc.c:992 */
static inline int pcie_hotplug_depth(struct pci_dev *dev)
{
	struct pci_bus *bus = dev->bus;
	int depth = 0;

	while (bus->parent) {
		bus = bus->parent;
		if (bus->self && bus->self->is_pciehp)
			depth++;
	}

	return depth;
}

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
	... /* 8 lines, to :1032 */
	ctrl->slot_cap = slot_cap;
	mutex_init(&ctrl->ctrl_lock);
	mutex_init(&ctrl->state_lock);
	init_rwsem(&ctrl->reset_lock);
	init_waitqueue_head(&ctrl->requester);
	init_waitqueue_head(&ctrl->queue);
	INIT_DELAYED_WORK(&ctrl->button_work, pciehp_queue_pushbutton_work);
	dbg_ctrl(ctrl);

	down_read(&pci_bus_sem);
	ctrl->state = list_empty(&subordinate->devices) ? OFF_STATE : ON_STATE;
	up_read(&pci_bus_sem);
```

[`depth`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L115) counts the hotplug ports above this one, and init_rwsem() at [`pciehp_hpc.c:1035`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1035) prepares the semaphore. The same stage sets [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109) from whether the secondary bus has functions, and masks the indicator capabilities for [`hotplug_user_indicators`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L425) as the previous subsection described. In the v7.2 tree the one function that takes the write side is [`pciehp_reset_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L939), which [`init_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L51) installed as the slot's [`reset_slot`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L47) method; read it with its comment.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:931 */
/*
 * pciehp has a 1:1 bus:slot relationship so we ultimately want a secondary
 * bus reset of the bridge, but at the same time we want to ensure that it is
 * not seen as a hot-unplug, followed by the hot-plug of the device. Thus,
 * disable link state notification and presence detection change notification
 * momentarily, if we see that they could interfere. Also, clear any spurious
 * events after.
 */
int pciehp_reset_slot(struct hotplug_slot *hotplug_slot, bool probe)
{
	struct controller *ctrl = to_ctrl(hotplug_slot);
	struct pci_dev *pdev = ctrl_dev(ctrl);
	int rc;

	if (probe)
		return 0;

	down_write_nested(&ctrl->reset_lock, ctrl->depth);

	pci_hp_ignore_link_change(pdev);

	rc = pci_bridge_secondary_bus_reset(ctrl->pcie->port);

	pci_hp_unignore_link_change(pdev);

	up_write(&ctrl->reset_lock);
	return rc;
}
```

The write side is held across the bus reset at [`pciehp_hpc.c:952`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L952), and the calls on either side of it mark the link change as one to ignore, which the IRQ thread's suppression test honours. A reset that arrives during a removal waits for the read side the IRQ thread holds. An IRQ thread that wakes during a reset waits at the routing until the write side is released. The read side has two more holders outside the removal, one in the link-change suppression code at [`pciehp_hpc.c:617-620`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L617) and [`pciehp_check_presence()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L167), which compares occupancy with the slot's state at probe and resume:

```c
/* drivers/pci/hotplug/pciehp_core.c:156 */
/**
 * pciehp_check_presence() - synthesize event if presence has changed
 * @ctrl: controller to check
 *
 * On probe and resume, an explicit presence check is necessary to bring up an
 * occupied slot or bring down an unoccupied slot.  This can't be triggered by
 * events in the Slot Status register, they may be stale and are therefore
 * cleared.  Secondly, sending an interrupt for "events that occur while
 * interrupt generation is disabled [when] interrupt generation is subsequently
 * enabled" is optional per PCIe r4.0, sec 6.7.3.4.
 */
static void pciehp_check_presence(struct controller *ctrl)
{
	int occupied;

	down_read_nested(&ctrl->reset_lock, ctrl->depth);
	mutex_lock(&ctrl->state_lock);

	occupied = pciehp_card_present_or_link_active(ctrl);
	if ((occupied > 0 && (ctrl->state == OFF_STATE ||
			  ctrl->state == BLINKINGON_STATE)) ||
	    (!occupied && (ctrl->state == ON_STATE ||
			   ctrl->state == BLINKINGOFF_STATE)))
		pciehp_request(ctrl, PCI_EXP_SLTSTA_PDC);

	mutex_unlock(&ctrl->state_lock);
	up_read(&ctrl->reset_lock);
}
```

Both readers only request an event, so a removal they trigger runs on the IRQ thread like any other. commit [5b3f7b7d062b](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=5b3f7b7d062bc839fe0744bdfd0cfd7e8d1c4cd9) ("PCI: pciehp: Avoid slot access during reset") introduced the semaphore, and commit [085a9f43433f](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=085a9f43433f30cbe8a1ade62d9d7827c3217f4d) ("PCI: pciehp: Use down_read/write_nested(reset_lock) to fix lockdep errors") gave it the depth subclass for nested ports. The figure shows a reset that arrives during a removal and takes the write side while a function is unbound.

```text
    A slot reset meets a removal in progress: who holds reset_lock, step by step
    ────────────────────────────────────────────────────────────────────────────

    IRQ thread, removing the card                   reset_lock held by  reset caller
        │                                                                   │
        │ read side taken                           IRQ thread, read        │ holds device_lock of
        │ devices being removed                                             │ a function below the
        │                                                                   │ port; asks for the
        │                                                                   │ write side and waits
        │ read side dropped                         nobody                  │
        ├──────────────────────────────────────────────────────────────────▶│
        │ unbinding asks for                        reset caller, write     │ write side taken
        │ device_lock and waits                                             │ link change ignored,
        │                                                                   │ bus reset run
        │                                           nobody                  │ write side dropped,
        │                                                                   │ then device_lock
        │◀──────────────────────────────────────────────────────────────────┤
        │ unbinding runs                                                    │
        │ read side retaken                         IRQ thread, read        │
        ▼                                                                   ▼

    Time runs down. Had the IRQ thread kept the read side through the unbinding, each side
    would wait for a lock the other holds.
```

The reset takes the write side in the window the removal opens around each unbinding, finishes and releases it, after which the unbinding gets device_lock and the removal retakes the read side. Before commit [f5eff5591b8f](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=f5eff5591b8f9c5effd25c92c758a127765f74c1) the IRQ thread kept the read side through the unbinding, and the two paths could wait on each other.

So far, the removal has run on the IRQ thread from the slot event to slot power off, and the slot is left in [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133). [`reset_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114) has kept a reset from seeing the slot halfway. What remains is the flag that keeps a removal from starting, and the ways to watch one.

### ignore_hotplug keeps a sleeping function's link change harmless

Some drivers power their function down to D3cold, [`PCI_D3cold`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L187), at runtime, which takes the function's link down as a removal would. The hotplug port above would then see Data Link Layer State Changed and remove a function that is only asleep. [`pci_ignore_hotplug()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L6339) lets such a driver tell the port to drop its slot events, by setting [`ignore_hotplug`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L424) on the function and on the bridge above it:

```c
/* drivers/pci/pci.c:6339 */
void pci_ignore_hotplug(struct pci_dev *dev)
{
	struct pci_dev *bridge = dev->bus->self;

	dev->ignore_hotplug = 1;
	/* Propagate the "ignore hotplug" setting to the parent bridge. */
	if (bridge)
		bridge->ignore_hotplug = 1;
}
EXPORT_SYMBOL_GPL(pci_ignore_hotplug);
```

The bridge is [`self`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L707) of the function's bus, the bridge function whose secondary bus holds the function, and the comment calls the second write a propagation. commit [0824965140ff](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=0824965140fff1bf640a987dc790d1594a8e0699) added it. In the v7.2 tree these two writes are the only ones to [`ignore_hotplug`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L424) and nothing clears it, so the flag stays set for the life of both objects.

At v7.2 four callers use [`pci_ignore_hotplug()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L6339), each the runtime-suspend callback of a GPU driver, which calls it before moving its function to D3cold. [the runtime-suspend callback of one of them](https://elixir.bootlin.com/linux/v7.2/source/drivers/gpu/drm/nouveau/nouveau_drm.c#L1146) shows that order:

```c
/* drivers/gpu/drm/nouveau/nouveau_drm.c:1146 */
static int
nouveau_pmops_runtime_suspend(struct device *dev)
{
	struct pci_dev *pdev = to_pci_dev(dev);
	struct nouveau_drm *drm = pci_get_drvdata(pdev);
	int ret;

	if (!nouveau_pmops_runtime()) {
		pm_runtime_forbid(dev);
		return -EBUSY;
	}

	nouveau_switcheroo_optimus_dsm();
	ret = nouveau_do_suspend(drm, true);
	pci_save_state(pdev);
	pci_disable_device(pdev);
	pci_ignore_hotplug(pdev);
	pci_set_power_state(pdev, PCI_D3cold);
	drm->dev->switch_power_state = DRM_SWITCH_POWER_DYNAMIC_OFF;
	return ret;
}
```

The callback saves the function's state, disables it and calls [`pci_ignore_hotplug()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L6339) before it sets [`PCI_D3cold`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L187), so the flag is set before the link goes down. The port reads the flag in its hard handler, in the lines the first subsection showed; read them again.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:623 */
static irqreturn_t pciehp_isr(int irq, void *dev_id)
{
	struct controller *ctrl = (struct controller *)dev_id;
	struct pci_dev *pdev = ctrl_dev(ctrl);
	... /* 91 lines, to :718 */
	if (pdev->ignore_hotplug) {
		ctrl_dbg(ctrl, "ignoring hotplug event %#06x\n", events);
		return IRQ_HANDLED;
	}

	/* Save pending events for consumption by IRQ thread. */
	atomic_or(events, &ctrl->pending_events);
	return IRQ_WAKE_THREAD;
```

The local `pdev` here is the hotplug port, so the flag that counts is the one [`pci_ignore_hotplug()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L6339) propagated to the port above the function. With it set, the handler returns after Command Completed without saving any event, so neither the link change of D3cold nor a real removal of that card starts a removal. The figure shows where the bit is set and which port's handler reads it.

```text
    Where ignore_hotplug is set, and which port's hard handler reads it
    ───────────────────────────────────────────────────────────────────

    ┌────────────────────────────────────────┐
    │ a port further up                      │  ignore_hotplug stays 0:
    │ struct pci_dev                         │  its slot events still start removals
    └───────────────────┬────────────────────┘
                        │ subordinate
    ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄│┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄ one level up from the function: as far as the bit reaches
                        ▼
    ┌────────────────────────────────────────┐
    │ the port above the function: bus->self │  ignore_hotplug = 1 (the propagated write)
    │ struct pci_dev, a hotplug port         │  its hard handler returns before saving
    └───────────────────┬────────────────────┘  any event but Command Completed
                        │ subordinate
                        ▼
    ┌────────────────────────────────────────┐
    │ the function going to D3cold           │  ignore_hotplug = 1 (the first write)
    │ struct pci_dev                         │  set by its driver's runtime suspend
    └────────────────────────────────────────┘

    Nothing in the tree clears the bit again, so both stay set until the objects are freed.
```

A hotplug port two levels above the function does not get the bit, so its events still start removals. The ACPI hotplug driver reads the flag too, at [`acpiphp_glue.c:581`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/acpiphp_glue.c#L581) and [`acpiphp_glue.c:657`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/acpiphp_glue.c#L657), but with [`CONFIG_HOTPLUG_PCI_ACPI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/Kconfig#L55) unset, as the x86_64 defconfig leaves it, pciehp is its one reader.

### The removal prints messages, fires a tracepoint and crosses hand-offs

A removal leaves traces in the trace buffer and in the kernel log, and it crosses several hand-offs between contexts. The table lists them by class, with the sites on the removal path.

| class | on the removal path | sites |
|---|---|---|
| tracepoints | `pci:pci_hp_event` with LINK_DOWN or CARD_NOT_PRESENT; pciehp and remove.c fire no other tracepoint, a driver's remove callback may fire its own, and `pci:pcie_link_event` belongs to link speed updates | [`pciehp_ctrl.c:251-253`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L251), [`pciehp_ctrl.c:258-260`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L258), [`pciehp_ctrl.c:281-283`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L281) |
| info and error lines | "Link Down", "Card not present", "Already disabled", the sysfs state lines, "no response from device" | [`pciehp_ctrl.c:249-250`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L249), [`pciehp_ctrl.c:256-257`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L256), [`pciehp_ctrl.c:368-369`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L368), [`pciehp_ctrl.c:447-448`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L447), [`pciehp_hpc.c:172`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L172) |
| debug lines | the secondary bus at the start of the removal, the Slot Control value read and the commands written, the pending interrupts, the ignored events, a card replaced during sleep | [`pciehp_pci.c:101-102`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_pci.c#L101), [`pciehp_hpc.c:401-402`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L401), [`pciehp_hpc.c:562-564`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L562), [`pciehp_hpc.c:529-530`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L529), [`pciehp_hpc.c:699`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L699), [`pciehp_hpc.c:719`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L719), [`pciehp_core.c:307`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L307) |
| hand-offs | hard handler to IRQ thread or the poll thread; the five-second button work; a sysfs writer waiting on requester; Command Completed waking queue; the port's runtime-PM reference; the driver core's notifier and remove uevent for each function | [`pciehp_hpc.c:724-725`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L724), [`pciehp_ctrl.c:185`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L185), [`pciehp_ctrl.c:442-444`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L442), [`pciehp_hpc.c:710`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L710), [`pciehp_ctrl.c:382`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L382), [`core.c:3934`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/core.c#L3934), [`core.c:3979`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/core.c#L3979) |
| surfaces | the slot's power file, the pciehp and pci_hotplug parameters, dynamic debug; no debugfs file and no fault injection | the next subsection |

The tracepoint is `pci:pci_hp_event`, defined in include/trace/events/pci.h with the port's name, the slot's name and the event. Its event strings come from [`PCI_HOTPLUG_EVENT`](https://elixir.bootlin.com/linux/v7.2/source/include/trace/events/pci.h#L11), a list of the four enumerators with the string each prints:

```c
/* include/trace/events/pci.h:11 */
#define PCI_HOTPLUG_EVENT						\
	EM(PCI_HOTPLUG_LINK_UP,			"LINK_UP")		\
	EM(PCI_HOTPLUG_LINK_DOWN,		"LINK_DOWN")		\
	EM(PCI_HOTPLUG_CARD_PRESENT,		"CARD_PRESENT")		\
	EMe(PCI_HOTPLUG_CARD_NOT_PRESENT,	"CARD_NOT_PRESENT")
```

LINK_DOWN and CARD_NOT_PRESENT are the strings of [`PCI_HOTPLUG_LINK_DOWN`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci.h#L44) and [`PCI_HOTPLUG_CARD_NOT_PRESENT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci.h#L46). The event itself is defined by [`pci_hp_event`](https://elixir.bootlin.com/linux/v7.2/source/include/trace/events/pci.h#L43), whose record keeps the two names as strings because, as its comment explains, each hotplug driver has its own controller structure:

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

A removal records one event per Slot Status bit it saw, LINK_DOWN before CARD_NOT_PRESENT, and records CARD_NOT_PRESENT again when its re-check turns off a slot that was blinking toward power-on. The log lines come from three macros of pciehp.h that prefix every message with the port's name, and the comment above them names the dynamic-debug switch:

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

[`ctrl_dbg()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L35) is a pci_dbg() of the port, so with [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) set each debug line in the table is a dynamic-debug site. `dyndbg="file pciehp* +p"` on the command line, or the same query written to /proc/dynamic_debug/control, turns them on. [`ctrl_info()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L39) and [`ctrl_err()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L37) print at the info and error levels. [`CONFIG_PCI_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L70), which this page assumes unset, would compile every file under drivers/pci/ with DEBUG defined, by the line [`drivers/pci/Makefile:50`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Makefile#L50):

```c
/* drivers/pci/Makefile:50 */
subdir-ccflags-$(CONFIG_PCI_DEBUG) := -DDEBUG
```

With the option unset, turning the debug lines on is the reader's step. The first hand-off is chosen when the port's interrupt is requested, in [`pciehp_request_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L58):

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
		ctrl_err(ctrl, "Cannot get irq %d for the hotplug controller\n",
			 irq);
	return retval;
}
```

Without [`pciehp_poll_mode`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L34), request_threaded_irq() pairs [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623) with [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728) on a shared interrupt named "pciehp". With it, a kernel thread named after the slot runs [`pciehp_poll()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L800), which calls both handlers itself:

```c
/* drivers/pci/hotplug/pciehp_hpc.c:800 */
static int pciehp_poll(void *data)
{
	struct controller *ctrl = data;

	schedule_timeout_idle(10 * HZ); /* start with 10 sec delay */

	while (!kthread_should_stop()) {
		/* poll for interrupt events or user requests */
		while (pciehp_isr(IRQ_NOTCONNECTED, ctrl) == IRQ_WAKE_THREAD ||
		       atomic_read(&ctrl->pending_events))
			pciehp_ist(IRQ_NOTCONNECTED, ctrl);

		if (pciehp_poll_time <= 0 || pciehp_poll_time > 60)
			pciehp_poll_time = 2; /* clamp to sane value */

		schedule_timeout_idle(pciehp_poll_time * HZ);
	}

	return 0;
}
```

The poll thread starts after 10 seconds and then checks every [`pciehp_poll_time`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L35) seconds, a value clamped to 2 when it is 0 or below or above 60. A removal in poll mode therefore starts up to that many seconds after the card leaves. The other hand-offs in the table are the button work, the sysfs wait and the Command Completed wake of earlier subsections, and the runtime-PM reference of [`pciehp_disable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L378). The driver core adds its notifier at [`core.c:3934`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/core.c#L3934) and its remove uevent at [`core.c:3979`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/core.c#L3979), which device_del() sends for each function [`pci_destroy_dev()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/remove.c#L32) unregisters.

### The power file and parameters steer and expose a removal

User space reaches a removal through the slot's power file and steers pciehp through two parameters. The parameters are module parameters of pciehp, which [`CONFIG_HOTPLUG_PCI_PCIE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L16) builds into the kernel, so they are set on the kernel command line as `pciehp.pciehp_poll_mode` and `pciehp.pciehp_poll_time`, and they are writable under /sys/module/pciehp/parameters/:

```c
/* drivers/pci/hotplug/pciehp_core.c:33 */
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

[`pciehp_poll_mode`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L34) replaces the interrupt with the poll thread of the previous subsection, and [`pciehp_poll_time`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L35) sets its period. The power file is the one [`power_write_file()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L67) stores to, under /sys/bus/pci/slots/ with the slot's name, and writing 0 to it starts an orderly removal. The hotplug core logs the written value at the debug level only when its own `debug` parameter is set:

```c
/* drivers/pci/hotplug/pci_hotplug_core.c:36 */
/* local variables */
static bool debug;
```

The parameter is `pci_hotplug.debug`, the module name of pci_hotplug_core.c, and [`pci_hotplug_core.c:578`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L578) declares it writable. No debugfs file and no fault-injection point covers the removal path of pciehp or of remove.c, and the state a reader can follow is the log, the `pci:pci_hp_event` trace and the slot's power file.
