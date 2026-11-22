# Link-change suppression in pciehp

> CAUTION: AI-GENERATED CONTENT
>
> STRICTLY DO NOT SUBMIT THIS UPSTREAM UNLESS YOU ARE AN EXPERT INTIMATELY FAMILIAR WITH THIS SUBSYSTEM.

A PCIe hotplug port treats a link that goes down as a device leaving its slot. pciehp, the native hotplug driver, then turns the slot off and removes the functions below it. Some link flaps are deliberate, a reset the kernel issues or Downstream Port Containment stopping an error, and the device is still there when the link returns. The kernel marks the port's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) while such a flap runs, or clears the event after it, so that pciehp's interrupt thread drops the link and presence events the flap raised. The page follows the three causes and the check that still turns the slot off when the link stays down or another device answers.

```text
    Three causes flap the link below a hotplug port, and each leaves a mark the IRQ thread reads
    ────────────────────────────────────────────────────────────────────────────────────────────

    ┌──────────────────────────────┐
    │ port above the hotplug port  │ ◀── cause 3: AER or DPC recovery resets this link,
    └──────────────┬───────────────┘     and a Hot Reset reaches the hotplug port below
                   │ link
    ┌──────────────┴─────────────────────────────────────────┐
    │ hotplug port: struct pci_dev and struct controller     │
    │                                                        │
    │ priv_flags     LINK_CHANGING    LINK_CHANGED           │ ◀── cause 1: a reset of the slot
    │                DPC_RECOVERING   DPC_RECOVERED          │ ◀── cause 2: DPC at this port
    │ Slot Status    DLLSC   PDC                             │ ◀── cause 3: the slot_reset hook clears DLLSC
    │                  │                                     │
    │                  ▼ copied by the hard IRQ handler      │
    │ pending_events ──────▶ IRQ thread: drops the events,   │
    │                        then checks the link and device │
    └──────────────┬─────────────────────────────────────────┘
                   │ link: Link Down, then Link Up
    ┌──────────────┴───────────────┐
    │ slot: the device below       │
    └──────────────────────────────┘
```

## SUMMARY

A hotplug port is two kernel objects, its [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) and the [`struct controller`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L91) that pciehp keeps for the port's single slot, and the table maps the specification's terms onto them. [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59) is portdrv's service instance, the object through which a port service such as pciehp reaches its port.

| PCIe term | kernel representation | role on this page |
|---|---|---|
| hotplug port and its slot | the port's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) and pciehp's [`struct controller`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L91) | carries the marks and the saved events |
| Link Down or Link Up | [`PCI_EXP_SLTSTA_DLLSC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L642) in Slot Status, saved in [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104) | dropped while a mark explains it |
| presence change | [`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637) in Slot Status | dropped unless [`inband_presence_disabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L96) is set |
| Secondary Bus Reset | [`PCI_BRIDGE_CTL_BUS_RESET`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L172) in Bridge Control | bracketed by [`PCI_LINK_CHANGING`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L773) and [`PCI_LINK_CHANGED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L772) |
| Downstream Port Containment | the DPC capability at [`dpc_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L537) | recorded in [`PCI_DPC_RECOVERING`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L770) and [`PCI_DPC_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L769) |
| port service | [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59), portdrv's service instance | the argument of [`pciehp_slot_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L915) |

The primary journey runs from Slot Status through [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104) to [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728), which drops the two link events while the slot is in [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) and a cause has left its mark. A check follows every drop, since [`pciehp_ignore_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L596) asks for the events again when the link is down or the device in the slot has changed.

## SPECIFICATIONS

No specification defines the suppression, which is a kernel synthesis read here from drivers/pci/hotplug/, drivers/pci/pcie/ and drivers/pci/pci.c. The entries below are the sections that the tree's comments and commit messages name for the registers and resets the mechanism reacts to.

- PCI Express Base Specification 5.0, section 6.6.1: Conventional Reset, quoted by commit [ea401499e943](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=ea401499e943c307e6d44af6c2b4e068643e7884) ("PCI: pciehp: Ignore Link Down/Up caused by error-induced Hot Reset") for the Hot Reset a switch sends to its Downstream Ports, and named without a title by [`pci.c:4717-4719`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4717) for the delays [`pci_bridge_wait_for_secondary_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4724) keeps.
- PCI Express Base Specification r5.0, section 6.7.3.4: Software Notification of Hot-Plug Events, quoted by commit [ea401499e943](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=ea401499e943c307e6d44af6c2b4e068643e7884) for the interrupt a port sends when an event bit and its enable bit are both set.
- PCIe r6.2, sec 6.7.3.1, named without a title by commit [2af781a9edc4](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=2af781a9edc4ef5f6684c0710cc3542d9be48b31) ("PCI: pciehp: Ignore Link Down/Up caused by Secondary Bus Reset") for the enable bits whose masking stops the interrupt and leaves the event latched.
- PCIe r5.0, sec. 6.2.10, named without a title by commit [a97396c6eb13](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=a97396c6eb13f65bea894dbe7739b2e883d40a3e) ("PCI: pciehp: Ignore Link Down/Up caused by DPC") for Downstream Port Containment.
- PCIe r5.0 sec 7.5.3.10, named without a title by commit [c3be50f7547c](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=c3be50f7547ccb533284b22f74baf37d3379843e) ("PCI: pciehp: Ignore Presence Detect Changed caused by DPC") for the In-Band PD Disable bit, and PCIe r5.0, appendix I implementation note, named by [`pciehp.h:53-55`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L53) for [`inband_presence_disabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L96).
- PCIe r6.2 sec 7.9.3, named by [`pciehp.h:49-51`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L49) for the Device Serial Number cached in [`dsn`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L93).
- PCIe r6.0 sec 6.7.6, named by [`dpc.c:367-369`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L367) for the errors that accompany an asynchronous removal.
- PCIe r6.0 sec 6.6.1 and sec 2.3.1, named by [`pci.c:69-81`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L69) for the 1 s within which a device is ready after a Conventional Reset and for its extension through Request Retry Status.
- PCI spec v3.0 7.6.4.2, named by [`pci.c:4832-4835`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4832) for the minimum Trst of the Secondary Bus Reset.

## COVERAGE

### The bracket around a deliberate link change

- [`'\<pci_hp_ignore_link_change\>':'drivers/pci/hotplug/pci_hotplug_core.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L510): opens a bracket on a hotplug port by setting [`PCI_LINK_CHANGING`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L773).
- [`'\<pci_hp_unignore_link_change\>':'drivers/pci/hotplug/pci_hotplug_core.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L523): closes the bracket, leaving [`PCI_LINK_CHANGED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L772) as its record, and wakes the waiters.
- [`'\<pci_hp_spurious_link_change\>':'drivers/pci/hotplug/pci_hotplug_core.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L552): waits for an open bracket to close and takes the record.
- [`'\<pci_hp_link_change_wq\>':'drivers/pci/hotplug/pci_hotplug_core.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L491): the wait queue the reader sleeps on while a bracket is open.
- [`'PCI_LINK_CHANGING'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L773): the bit of [`priv_flags`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L585) that says a bracket is open.
- [`'PCI_LINK_CHANGED'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L772): the bit of [`priv_flags`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L585) that says a bracket closed since the last reader.
- [`'\<pciehp_reset_slot\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L939): pciehp's slot reset method, which wraps the Secondary Bus Reset in the bracket.
- [`'\<pci_bridge_secondary_bus_reset\>':'drivers/pci/pci.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4854): the reset of a bridge's secondary bus that the bracket encloses.

### DPC's record of a recovery

- [`'PCI_DPC_RECOVERING'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L770): the bit of [`priv_flags`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L585) set while DPC recovers the link.
- [`'PCI_DPC_RECOVERED'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L769): the bit that records a successful recovery until pciehp takes it.
- [`'\<dpc_completed_waitqueue\>':'drivers/pci/pcie/dpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L78): the wait queue pciehp sleeps on while DPC is still working.
- [`'\<dpc_completed\>':'drivers/pci/pcie/dpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L81): the condition of that wait, true once the trigger and the recovery have ended.
- [`'\<pci_dpc_recovered\>':'drivers/pci/pcie/dpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L103): waits for containment to end and takes the record of its success.

### pciehp's drop, check and clear

- [`'\<pciehp_ignore_link_change\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L596): clears the dropped events and requests them again when the link or the device fails the check.
- [`'\<pciehp_check_link_active\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L235): reads Data Link Layer Link Active of the port's link.
- [`'\<pciehp_device_replaced\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L567): compares the identity of function 0 in the slot with the cached one.
- [`'\<pciehp_request\>':'drivers/pci/hotplug/pciehp_ctrl.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L141): puts events back into the controller and wakes the interrupt thread.
- [`'\<pciehp_slot_reset\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L915): clears the Link Down/Up that a Hot Reset from recovery above left in Slot Status.

## DOCUMENTATION

- [`Documentation/ABI/testing/sysfs-bus-pci`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/ABI/testing/sysfs-bus-pci): the reset_subordinate attribute of a bridge, which resets every device below it.
- [`Documentation/PCI/pci-error-recovery.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/PCI/pci-error-recovery.rst): the slot_reset callback of error recovery and the link reset of Downstream Port Containment.
- [`Documentation/trace/events-pci.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/trace/events-pci.rst): the pci_hp_event and pcie_link_event tracepoints and the hotplug events they report.

## OTHER SOURCES

### Added by Claude Opus 5.5

- [PCI: pciehp: Ignore Link Down/Up caused by DPC (commit a97396c6eb13)](https://lore.kernel.org/r/0be565d97438fe2a6d57354b3aa4e8626952a00b.1619857124.git.lukas@wunner.de)
- [PCI: pciehp: Ignore Link Down/Up caused by error-induced Hot Reset (commit ea401499e943)](https://lore.kernel.org/r/251f4edcc04c14f873ff1c967bc686169cd07d2d.1627638184.git.lukas@wunner.de)
- [PCI: pciehp: Ignore Link Down/Up caused by Secondary Bus Reset (commit 2af781a9edc4)](https://patch.msgid.link/d04deaf49d634a2edf42bf3c06ed81b4ca54d17b.1744298239.git.lukas@wunner.de)
- [PCI: pciehp: Ignore Presence Detect Changed caused by DPC (commit c3be50f7547c)](https://patch.msgid.link/fa264ff71952915c4e35a53c89eb0cde8455a5c5.1744298239.git.lukas@wunner.de)
- [PCI: pciehp: Ignore belated Presence Detect Changed caused by DPC (commit bbf10cd68683)](https://patch.msgid.link/d9c4286a16253af7e93eaf12e076e3ef3546367a.1750257164.git.lukas@wunner.de)
- [PCI: Make reset_subordinate hotplug safe (commit 8238cb69c01f)](https://patch.msgid.link/20260217160836.2709885-4-kbusch@meta.com)
- [PCI: Don't fallback to bus reset after failed slot reset (commit cfcbfe5cb116)](https://patch.msgid.link/20260421150644.3543733-1-kbusch@meta.com)

## REGISTERS

The paths of this page read and write four configuration registers of the hotplug port, and the drawings below give their fields with the macros that name them. The paragraph above each drawing says what its fields decide on these paths.

Slot Status, [`PCI_EXP_SLTSTA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L633), is where a hotplug port latches its slot events, and a 1 written to an event bit clears it. [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623) copies the event bits into [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104) and writes them back. [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728) drops [`PCI_EXP_SLTSTA_DLLSC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L642) and [`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637) when a cause explains them, and [`pciehp_slot_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L915) writes [`PCI_EXP_SLTSTA_DLLSC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L642) to clear the Link Down/Up a Hot Reset left.

```text
    Slot Status register, offset 0x1a of the PCIe capability
    ────────────────────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x1a  │      ·      │L│E│P│M│C│D│S│F│A│
          │    (15:9)   │ │ │ │ │ │ │ │ │ │
          └─────────────┴─┴─┴─┴─┴─┴─┴─┴─┴─┘

    L = PCI_EXP_SLTSTA_DLLSC (Data Link Layer State Changed: the Link Down/Up event, always among the dropped events)
    D = PCI_EXP_SLTSTA_PDC (Presence Detect Changed, dropped unless in-band presence detect is disabled)
    A = PCI_EXP_SLTSTA_ABP (Attention Button Pressed)   F = PCI_EXP_SLTSTA_PFD (Power Fault Detected)
    S = PCI_EXP_SLTSTA_MRLSC (MRL Sensor Changed)       C = PCI_EXP_SLTSTA_CC (Command Completed)
    M = PCI_EXP_SLTSTA_MRLSS (MRL Sensor State)         P = PCI_EXP_SLTSTA_PDS (Presence Detect State)
    E = PCI_EXP_SLTSTA_EIS (Electromechanical Interlock Status)
    · = bits 15:9, which pci_regs.h does not name; a 1 written to an event bit clears it
```

Link Status, [`PCI_EXP_LNKSTA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L577), of the hotplug port describes the link to its slot. [`pciehp_check_link_active()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L235) reads [`PCI_EXP_LNKSTA_DLLLA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L593) when it decides whether a dropped flap left the link down, and [`pci_bridge_wait_for_secondary_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4724) waits for the same bit after a reset of a port faster than 5 GT/s.

```text
    Link Status register, offset 0x12 of the PCIe capability
    ────────────────────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x12  │A│B│D│C│T│·│    nlw    │  cls  │
          │ │ │ │ │ │ │   (9:4)   │ (3:0) │
          └─┴─┴─┴─┴─┴─┴───────────┴───────┘

    D   = PCI_EXP_LNKSTA_DLLLA (Data Link Layer Link Active, the link state the re-checks read)
    B   = PCI_EXP_LNKSTA_LBMS (Link Bandwidth Management Status, which a reset sets as the link retrains)
    cls = PCI_EXP_LNKSTA_CLS (Current Link Speed)   nlw = PCI_EXP_LNKSTA_NLW (Negotiated Link Width)
    T   = PCI_EXP_LNKSTA_LT (Link Training)         C   = PCI_EXP_LNKSTA_SLC (Slot Clock Configuration)
    A   = PCI_EXP_LNKSTA_LABS (Link Autonomous Bandwidth Status)
    ·   = bit 10, which pci_regs.h does not name
```

Bridge Control, [`PCI_BRIDGE_CONTROL`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L166), belongs to the Type 1 header of every bridge function, a hotplug port included. [`pci_reset_secondary_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4824) sets [`PCI_BRIDGE_CTL_BUS_RESET`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L172) for 2 ms and clears it again, the Secondary Bus Reset that the bracket of [`pciehp_reset_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L939) encloses.

```text
    Bridge Control register, offset 0x3e of a Type 1 header
    ───────────────────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x3e  │       ·       │K│R│M│·│V│I│E│P│
          │     (15:8)    │ │ │ │ │ │ │ │ │
          └───────────────┴─┴─┴─┴─┴─┴─┴─┴─┘

    R = PCI_BRIDGE_CTL_BUS_RESET (0x40, Secondary Bus Reset: held at 1 for 2 ms by pci_reset_secondary_bus())
    P = PCI_BRIDGE_CTL_PARITY (0x01)    E = PCI_BRIDGE_CTL_SERR (0x02)     I = PCI_BRIDGE_CTL_ISA (0x04)
    V = PCI_BRIDGE_CTL_VGA (0x08)       M = PCI_BRIDGE_CTL_MASTER_ABORT (0x20)
    K = PCI_BRIDGE_CTL_FAST_BACK (0x80)
    · = bit 4 and bits 15:8, which pci_regs.h does not name; the reset keeps every other bit as read
```

DPC Status, [`PCI_EXP_DPC_STATUS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1096), is the register at offset 0x08 of the port's DPC extended capability, whose own offset [`dpc_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L537) holds. [`dpc_completed()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L81) reads [`PCI_EXP_DPC_STATUS_TRIGGER`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1097) to tell whether the port still contains, and [`dpc_reset_link()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L148) writes it to let the port leave containment once the link is down.

```text
    DPC Status register, offset 0x08 of the DPC extended capability
    ───────────────────────────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x08  │  ·  │   fep   │·│ext│B│I│rsn│T│
          │15:13│  (12:8) │ │6:5│ │ │2:1│ │
          └─────┴─────────┴─┴───┴─┴─┴───┴─┘

    T   = PCI_EXP_DPC_STATUS_TRIGGER (Trigger Status: 1 while the port contains, cleared by writing 1)
    B   = PCI_EXP_DPC_RP_BUSY (Root Port Busy, polled when the port has RP Extensions)
    I   = PCI_EXP_DPC_STATUS_INTERRUPT (Interrupt Status)
    rsn = PCI_EXP_DPC_STATUS_TRIGGER_RSN (Trigger Reason)  ext = PCI_EXP_DPC_STATUS_TRIGGER_RSN_EXT
    fep = PCI_EXP_DPC_RP_PIO_FEP (RP PIO First Error Pointer)
    ·   = bit 7 and bits 15:13, which pci_regs.h does not name
```

## DETAILS

DETAILS first shows how a link flap reaches the slot state machine as a removal and where the interrupt thread can still drop it. It then follows the first cause, a pair of [`priv_flags`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L585) bits that bracket a deliberate link change, through the thread's wait on them, the slot reset that sets them and the paths that reach it. DPC's own pair of bits and the wait in [`pci_dpc_recovered()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L103) come next, followed by what the thread does with the dropped events and the check that brings them back. The last subsections cover the Hot Reset that recovery above a port sends down, which [`pciehp_slot_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L915) absorbs, and the messages, hand-offs and files that expose the mechanism.

### Kconfig assumptions

The page documents x86-64 with ACPI, built from [`x86_64_defconfig`](https://elixir.bootlin.com/linux/v7.2/source/arch/x86/configs/x86_64_defconfig) resolved at commit [8d3ae59288f1](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=8d3ae59288f1e7d58d76558a6ee96d533bc5019f) with the PCIe port services and dynamic debug enabled on top of it. The defconfig sets [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5) and [`CONFIG_HOTPLUG_PCI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/Kconfig#L6) and leaves [`CONFIG_HOTPLUG_PCI_PCIE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L16), [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28), [`CONFIG_PCIE_DPC`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L121) and [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) unset, and the page assumes those four set.

| option | assumed value | what it decides here |
|---|---|---|
| [`CONFIG_HOTPLUG_PCI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/Kconfig#L6) | y | builds [`pci_hp_ignore_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L510) and [`pci_hp_unignore_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L523); unset, both are empty inlines |
| [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5) | y | builds portdrv, whose [`pcie_portdrv_slot_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L758) calls [`pciehp_slot_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L915) |
| [`CONFIG_HOTPLUG_PCI_PCIE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L16) | y | builds pciehp and compiles [`dpc_completed()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L81) and [`pci_dpc_recovered()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L103) into dpc.c |
| [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28) | y | builds [`aer_root_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1667), whose reset of a hotplug port takes the slot method |
| [`CONFIG_PCIE_DPC`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L121) | y | builds DPC recovery; unset, [`pci_dpc_recovered()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L103) is an inline returning false |
| [`CONFIG_PCIE_EDR`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L140) | unset | keeps firmware-owned DPC out of the wait in [`pci_dpc_recovered()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L103) |
| [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) | y | makes the [`pci_dbg()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2896) sites on these paths dynamic-debug callsites |
| [`CONFIG_PCI_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L70) | unset | would print the same sites unconditionally with `-DDEBUG` |

The table indexes the prose, and each option's effect is stated again where it applies in the subsections below.

### A link flap reads as a removal to the slot state machine

A hotplug port tells software about its slot through the Slot Status register, [`PCI_EXP_SLTSTA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L633), whose event bits latch until software writes them back. [`PCI_EXP_SLTSTA_DLLSC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L642) latches when the Data Link Layer Link Active state of the link below the port changes, which pciehp reports as Link Down or Link Up. [`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637) latches when Presence Detect State changes. pciehp keeps a [`struct controller`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L91) per hotplug port, and the event bits travel from the register into that object's [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104) word before anything is decided.

The hard interrupt handler [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623) makes that move. Read its stages for the register read, the mask that keeps the event bits, the write that clears them and the store into the word.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:623 */
static irqreturn_t pciehp_isr(int irq, void *dev_id)
{
	struct controller *ctrl = (struct controller *)dev_id;
	struct pci_dev *pdev = ctrl_dev(ctrl);
	struct device *parent = pdev->dev.parent;
	u16 status, events = 0;
... /* 24 lines, to :653 */
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
	... /* 17 lines, to :686 */
	if (status) {
		pcie_capability_write_word(pdev, PCI_EXP_SLTSTA, status);

	... /* 29 lines, to :718 */
	if (pdev->ignore_hotplug) {
		ctrl_dbg(ctrl, "ignoring hotplug event %#06x\n", events);
		return IRQ_HANDLED;
	}

	/* Save pending events for consumption by IRQ thread. */
	atomic_or(events, &ctrl->pending_events);
	return IRQ_WAKE_THREAD;
}
```

The handler keeps [`PCI_EXP_SLTSTA_DLLSC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L642) and [`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637) among the event bits, writes them back to clear them in the register, and ORs them into [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104) before it returns `IRQ_WAKE_THREAD`. From then on the event is held in the word, and Slot Status is free to latch the next one. The [`ignore_hotplug`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L424) test above the store discards a port's events wholesale, a separate mechanism that this page leaves out.

The interrupt thread hands link and presence events to [`pciehp_handle_presence_or_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L232), the entry of the slot state machine. Its first stage shows what a Link Down does to a slot that is on, the state [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) names.

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
```

A slot in [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) moves to [`POWEROFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L137), logs "Link Down" or "Card not present", fires the `pci:pci_hp_event` tracepoint and starts a surprise removal at [`pciehp_ctrl.c:262`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L262), which unbinds and removes the functions below the port. A reset of the link would therefore cost the device its driver, unless the event is dropped before this function runs. The figure draws the event's path and the one point where the interrupt thread can still drop it.

```text
    A Slot Status event reaches the slot state machine unless the IRQ thread drops it
    ─────────────────────────────────────────────────────────────────────────────────

    ┌─────────────┐  read, then   ┌────────────────┐  swapped    ┌────────────────┐
    │ Slot Status │  cleared by   │ pending_events │  for 0 by   │ events, a      │
    │ DLLSC  PDC  │ ────────────▶ │ DLLSC  PDC     │ ──────────▶ │ local of the   │
    └─────────────┘  the hard IRQ └────────────────┘  the IRQ    │ IRQ thread     │
                     handler                           thread    └───────┬────────┘
                                                                         │
                                      ┌──────────────────────────────────┴───────┐
                                      │ a known cause, and the slot in ON_STATE? │
                                      └───────┬──────────────────────────┬───────┘
                                          yes │                          │ no
                                              ▼                          ▼
                                  DLLSC and PDC taken out;     ON_STATE becomes POWEROFF_STATE,
                                  the slot stays on            the slot's devices are removed
```

The thread holds the events in a local between taking the word and calling the state machine, and the next subsection reads the test it makes there.

### The interrupt thread drops link events a known cause explains

Masking the enable bits, [`PCI_EXP_SLTCTL_PDCE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L614) and [`PCI_EXP_SLTCTL_DLLSCE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L630) of Slot Control, during a reset was the earlier answer, and the message of commit [2af781a9edc4](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=2af781a9edc4ef5f6684c0710cc3542d9be48b31) ("PCI: pciehp: Ignore Link Down/Up caused by Secondary Bus Reset") records why it failed. According to that message, masking stops interrupt generation while the events stay latched in Slot Status, and a handler run for another reason during the reset picks them up. The message adds that this became likely once bandwidth control began to share the hotplug interrupt in v6.13. The kernel now lets the interrupt thread decide, where it holds the events, whether a known cause explains them.

[`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728) is that thread, woken after the hard handler returns `IRQ_WAKE_THREAD` and called directly by the poll thread when [`pciehp_poll_mode`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L34) is set. Read its stages for the swap that takes the events, the test that drops link and presence events, and the dispatch after it.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:728 */
static irqreturn_t pciehp_ist(int irq, void *dev_id)
{
	struct controller *ctrl = (struct controller *)dev_id;
	struct pci_dev *pdev = ctrl_dev(ctrl);
	irqreturn_t ret;
	u32 events;
	... /* 12 lines, to :746 */
	synchronize_hardirq(irq);
	events = atomic_xchg(&ctrl->pending_events, 0);
	if (!events) {
		ret = IRQ_NONE;
		goto out;
	}
	... /* 12 lines, to :764 */
	/*
	 * Ignore Link Down/Up events caused by Downstream Port Containment
	 * if recovery succeeded, or caused by Secondary Bus Reset,
	 * suspend to D3cold, firmware update, FPGA reconfiguration, etc.
	 */
	if ((events & (PCI_EXP_SLTSTA_PDC | PCI_EXP_SLTSTA_DLLSC)) &&
	    (pci_dpc_recovered(pdev) || pci_hp_spurious_link_change(pdev)) &&
	    ctrl->state == ON_STATE) {
		u16 ignored_events = PCI_EXP_SLTSTA_DLLSC;

		if (!ctrl->inband_presence_disabled)
			ignored_events |= PCI_EXP_SLTSTA_PDC;

		events &= ~ignored_events;
		pciehp_ignore_link_change(ctrl, pdev, irq, ignored_events);
	}

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

The thread swaps [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104) for zero into its local events, so events that arrive later collect in the word while it works. The test at [`pciehp_hpc.c:769-771`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L769) has three parts, given in the table with what makes each true.

| part of the test | true when | where the answer comes from |
|---|---|---|
| a link or presence event | events holds [`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637) or [`PCI_EXP_SLTSTA_DLLSC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L642) | the copy made by [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623) |
| a known cause | [`pci_dpc_recovered()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L103) reports a recovered containment, or [`pci_hp_spurious_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L552) reports a bracket | bits of the port's [`priv_flags`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L585) |
| the slot is on | [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109) equals [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) | the slot state machine |

The two cause tests run in order, and the `||` calls [`pci_hp_spurious_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L552) when [`pci_dpc_recovered()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L103) has returned false. When the whole test holds, the dropped set is [`PCI_EXP_SLTSTA_DLLSC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L642), plus [`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637) unless [`inband_presence_disabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L96) is set. The thread removes that set from events and passes it to [`pciehp_ignore_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L596), so the dispatch below sees neither event and the slot stays on.

The message of commit [c3be50f7547c](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=c3be50f7547ccb533284b22f74baf37d3379843e) ("PCI: pciehp: Ignore Presence Detect Changed caused by DPC") gives the reason for the presence bit. A port that derives presence from the link reports a presence change with every flap. A port with in-band presence detect disabled reports one when a card really moves, and that event has to reach the state machine.

### Two priv_flags bits bracket a deliberate link change

A code path that is about to flap a link marks the hotplug port before it starts and unmarks it when it ends. The marks are bits of [`priv_flags`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L585) in the port's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352), a word of atomic bits that several mechanisms set and clear without a lock. The bit numbers are the macros listed at [`drivers/pci/pci.h:767-775`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L767). Read the list for the numbers of [`PCI_LINK_CHANGING`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L773) and [`PCI_LINK_CHANGED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L772), the bracket's pair, and of [`PCI_DPC_RECOVERING`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L770) and [`PCI_DPC_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L769), DPC's pair.

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

[`PCI_LINK_CHANGING`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L773), bit 5, says a bracket is open, and [`PCI_LINK_CHANGED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L772), bit 4, says one has closed since a reader last looked. DPC's pair, bits 1 and 2, follows the same pattern and a later subsection reads it. The figure places the eight bits these macros number at v7.2.

```text
    The bits of pci_dev.priv_flags, numbered as drivers/pci/pci.h defines them
    ──────────────────────────────────────────────────────────────────────────

    bit    7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┐
    word  │B│S│G│C│R│V│D│A│
          └─┴─┴─┴─┴─┴─┴─┴─┘

    A = PCI_DEV_ADDED (bit 0, the object is published)
    D = PCI_DPC_RECOVERED (bit 1, DPC recovery succeeded and no reader has taken the record)
    V = PCI_DPC_RECOVERING (bit 2, DPC recovery is running)
    R = PCI_DEV_REMOVED (bit 3, removal has started)
    C = PCI_LINK_CHANGED (bit 4, a bracket closed and no reader has taken the record)
    G = PCI_LINK_CHANGING (bit 5, a bracket is open)
    S = PCI_LINK_LBMS_SEEN (bit 6, a Link Bandwidth Management Status event was seen)
    B = PCI_DEV_ALLOW_BINDING (bit 7, drivers may bind)
    bits 8 and up of the unsigned long have no name in drivers/pci/pci.h
```

The bracket's functions are defined in [`pci_hotplug_core.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c) beside the wait queue [`pci_hp_link_change_wq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L491) they share. Read the queue and [`pci_hp_ignore_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L510), which opens a bracket, for the bit it sets and the barrier after it.

```c
/* drivers/pci/hotplug/pci_hotplug_core.c:491 */
static DECLARE_WAIT_QUEUE_HEAD(pci_hp_link_change_wq);

/**
 * pci_hp_ignore_link_change - begin code section causing spurious link changes
 * @pdev: PCI hotplug bridge
 *
 * Mark the beginning of a code section causing spurious link changes on the
 * Secondary Bus of @pdev, e.g. as a side effect of a Secondary Bus Reset,
 * D3cold transition, firmware update or FPGA reconfiguration.
 *
 * Hotplug drivers can thus check whether such a code section is executing
 * concurrently, await it with pci_hp_spurious_link_change() and ignore the
 * resulting link change events.
 *
 * Must be paired with pci_hp_unignore_link_change().  May be called both
 * from the PCI core and from Endpoint drivers.  May be called for bridges
 * which are not hotplug-capable, in which case it has no effect because
 * no hotplug driver is bound to the bridge.
 */
void pci_hp_ignore_link_change(struct pci_dev *pdev)
{
	set_bit(PCI_LINK_CHANGING, &pdev->priv_flags);
	smp_mb__after_atomic(); /* pairs with implied barrier of wait_event() */
}
```

[`pci_hp_ignore_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L510) sets [`PCI_LINK_CHANGING`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L773) and follows it with `smp_mb__after_atomic()`, a full barrier that its comment pairs with the barrier `wait_event()` implies. A reader woken by the flap therefore finds the bit set, since the bit is ordered before the reset that causes the flap. The kerneldoc names a Secondary Bus Reset, a D3cold transition, a firmware update and FPGA reconfiguration as causes. It allows callers in the PCI core and in endpoint drivers, while at v7.2 [`pciehp_reset_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L939) is the one caller in the tree.

The functions exist only with [`CONFIG_HOTPLUG_PCI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/Kconfig#L6) set. Read the declarations in include/linux/pci.h for what replaces them without it.

```c
/* include/linux/pci.h:1938 */
#ifdef CONFIG_HOTPLUG_PCI
void pci_hp_ignore_link_change(struct pci_dev *pdev);
void pci_hp_unignore_link_change(struct pci_dev *pdev);
#else
static inline void pci_hp_ignore_link_change(struct pci_dev *pdev) { }
static inline void pci_hp_unignore_link_change(struct pci_dev *pdev) { }
#endif
```

With [`CONFIG_HOTPLUG_PCI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/Kconfig#L6) unset both become empty inlines and a reset leaves no mark; the page assumes it set, as the x86-64 defconfig does. [`pci_hp_unignore_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L523) closes the bracket. Read it for the order of its steps.

```c
/* drivers/pci/hotplug/pci_hotplug_core.c:516 */
/**
 * pci_hp_unignore_link_change - end code section causing spurious link changes
 * @pdev: PCI hotplug bridge
 *
 * Mark the end of a code section causing spurious link changes on the
 * Secondary Bus of @pdev.  Must be paired with pci_hp_ignore_link_change().
 */
void pci_hp_unignore_link_change(struct pci_dev *pdev)
{
	set_bit(PCI_LINK_CHANGED, &pdev->priv_flags);
	mb(); /* ensure pci_hp_spurious_link_change() sees either bit set */
	clear_bit(PCI_LINK_CHANGING, &pdev->priv_flags);
	wake_up_all(&pci_hp_link_change_wq);
}
```

[`pci_hp_unignore_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L523) sets [`PCI_LINK_CHANGED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L772) before it clears [`PCI_LINK_CHANGING`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L773), with `mb()` between the two, and wakes the queue last. The comment gives the purpose of that order, that a reader sees either bit set. A reader that finds [`PCI_LINK_CHANGING`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L773) already clear therefore finds [`PCI_LINK_CHANGED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L772) set. The strip follows both bits of one port through a reset and the interrupt thread's check after it.

```text
    PCI_LINK_CHANGING and PCI_LINK_CHANGED of one hotplug port across a reset and the check after it
    ────────────────────────────────────────────────────────────────────────────────────────────────

    time ─────────────────────────────────────────────────────────────────────────────────────────────────▶

    event               bracket opens     link down, then up   bracket closes           IRQ thread reads
                              ▼                                   ▼     ▼                       ▼
                       ┌──────┬─────────────────────────────────────────┬──────────────────────────────────
    LINK_CHANGING      │ 0    │ 1                                       │ 0
                       └──────┴─────────────────────────────────────────┴──────────────────────────────────
                       ┌──────────────────────────────────────────┬─────────────────────────────┬──────────
    LINK_CHANGED       │ 0, or 1 left by an earlier bracket       │ 1                           │ 0
                       └──────────────────────────────────────────┴─────────────────────────────┴──────────
                              ①                                   ②     ③                       ④

    ① pci_hp_ignore_link_change    pci_hotplug_core.c:512  sets PCI_LINK_CHANGING before the reset starts
    ② pci_hp_unignore_link_change  :525                    sets PCI_LINK_CHANGED after the reset has ended
    ③ pci_hp_unignore_link_change  :527                    clears PCI_LINK_CHANGING, then wakes the waiters
    ④ pci_hp_spurious_link_change  :557                    clears PCI_LINK_CHANGED and returns its old value
```

① [`pci_hp_ignore_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L510) sets [`PCI_LINK_CHANGING`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L773) before the reset begins. ② [`pci_hp_unignore_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L523) sets [`PCI_LINK_CHANGED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L772) once the reset has returned. ③ `pci_hp_unignore_link_change()` then clears [`PCI_LINK_CHANGING`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L773) and wakes the waiters. ④ [`pci_hp_spurious_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L552) clears [`PCI_LINK_CHANGED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L772) and returns whether it was set.

Between ② and ③ both bits are set, and a reader in that interval waits, because it tests [`PCI_LINK_CHANGING`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L773) first. At v7.2 no function outside these three writes either bit, so the strip shows every writer of the two fields. The other bits of [`priv_flags`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L585) belong to publication, removal, DPC and bandwidth control, and the strip leaves them out because no path of the bracket writes them.

### The interrupt thread waits out the bracket before it decides

The reader of the bracket is [`pci_hp_spurious_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L552), which [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728) calls once it holds a link or presence event and [`pci_dpc_recovered()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L103) has returned false. It answers whether a bracket explains the event, and when a bracket is still open it waits for the close, so the thread decides after the reset has returned. Read it with its kerneldoc, which also states the limit of the answer.

```c
/* drivers/pci/hotplug/pci_hotplug_core.c:531 */
/**
 * pci_hp_spurious_link_change - check for spurious link changes
 * @pdev: PCI hotplug bridge
 *
 * Check whether a code section is executing concurrently which is causing
 * spurious link changes on the Secondary Bus of @pdev.  Await the end of the
 * code section if so.
 *
 * May be called by hotplug drivers to check whether a link change is spurious
 * and can be ignored.
 *
 * Because a genuine link change may have occurred in-between a spurious link
 * change and the invocation of this function, hotplug drivers should perform
 * sanity checks such as retrieving the current link state and bringing down
 * the slot if the link is down.
 *
 * Return: %true if such a code section has been executing concurrently,
 * otherwise %false.  Also return %true if such a code section has not been
 * executing concurrently, but at least once since the last invocation of this
 * function.
 */
bool pci_hp_spurious_link_change(struct pci_dev *pdev)
{
	wait_event(pci_hp_link_change_wq,
		   !test_bit(PCI_LINK_CHANGING, &pdev->priv_flags));

	return test_and_clear_bit(PCI_LINK_CHANGED, &pdev->priv_flags);
}
```

The function sleeps on [`pci_hp_link_change_wq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L491) until [`PCI_LINK_CHANGING`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L773) is clear, then clears [`PCI_LINK_CHANGED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L772) with `test_and_clear_bit()` and returns its old value. A true return means a bracket was open when the thread arrived, or opened and closed at some point since the previous call, as the kerneldoc states. The second reading allows a stale record. A reset whose flap raised no event leaves [`PCI_LINK_CHANGED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L772) set, and the next genuine link event on the port is taken for part of that reset.

The kerneldoc's answer to a stale record is a sanity check after the drop, which [`pciehp_ignore_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L596) makes. The figure gives the order of a reset in which the thread arrives inside the bracket, with the reset path, the link and the thread as the actors.

```text
    A reset and the IRQ thread meet at the two bits, the thread arriving inside the bracket
    ───────────────────────────────────────────────────────────────────────────────────────

    time ↓
    reset path                        ╎ link, Slot Status         ╎ pciehp IRQ thread
    ──────────────────────────────────┼───────────────────────────┼─────────────────────────────────────
    reset_lock taken for writing      ╎ link up                   ╎
    PCI_LINK_CHANGING set, then a     ╎                           ╎
    full barrier                      ╎                           ╎
    SBR bit set for 2 ms ─────────────▶ link down, DLLSC set      ╎
                                      ╎ hard IRQ copies DLLSC ────▶ woken with DLLSC; reads
                                      ╎                           ╎ PCI_LINK_CHANGING set and sleeps
                                      ╎                           ╎ on pci_hp_link_change_wq
    SBR bit cleared, wait for ────────▶ link up, DLLSC set again  ╎
    the link and the device           ╎                           ╎
    PCI_LINK_CHANGED set, mb(),       ╎                           ╎
    PCI_LINK_CHANGING cleared         ╎                           ╎
    waiters woken ────────────────────────────────────────────────▶ wakes, takes PCI_LINK_CHANGED;
                                      ╎                           ╎ drops DLLSC and PDC, then waits
                                      ╎                           ╎ for reset_lock
    reset_lock released ──────────────────────────────────────────▶ takes reset_lock, checks link
```

The order in the figure rests on the barrier after the set in [`pci_hp_ignore_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L510) and on the `mb()` in [`pci_hp_unignore_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L523), both shown in the previous subsection. The thread leaves [`pci_hp_spurious_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L552) after the bracket has closed, holding a true answer for a flap the bracket covered, and the next subsection shows the reset that opens the bracket.

### pciehp_reset_slot wraps the Secondary Bus Reset in the bracket

A Secondary Bus Reset is the reset a bridge applies to the link below it when [`PCI_BRIDGE_CTL_BUS_RESET`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L172) is set in its Bridge Control register. At a hotplug port it takes the link down and up by design. pciehp offers that reset to the PCI core as the slot's reset method, the [`reset_slot`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L47) member of [`struct hotplug_slot_ops`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L38), and its implementation opens and closes the bracket. [`init_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L51) installs the method when pciehp sets up the slot; read its first stage.

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

The assignment at [`pciehp_core.c:66`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L66) makes [`pciehp_reset_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L939) the reset method of the slot unconditionally, before any of the optional operations are chosen. The method takes a lock first, and the kerneldoc of [`struct controller`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L91) describes that lock, [`reset_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114), at [`pciehp.h:78-82`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L78).

```c
/* drivers/pci/hotplug/pciehp.h:78 */
 * @reset_lock: prevents access to the Data Link Layer Link Active bit in the
 *	Link Status register and to the Presence Detect State bit in the Slot
 *	Status register during a slot reset which may cause them to flap
 * @depth: Number of additional hotplug ports in the path to the root bus,
 *	used as lock subclass for @reset_lock
```

[`reset_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114) is a read-write semaphore that keeps readers of the two flapping status bits away while a reset runs. [`depth`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L115), the number of hotplug ports above this one, is the lockdep subclass that the holders on this page pass. A hotplug port below another one then does not look like a recursive lock. [`pciehp_reset_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L939) is the method; read it whole, with the comment above it.

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

A probe call returns 0 at once, which tells the core that the slot can be reset. A real call takes [`reset_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114) for writing, opens the bracket on the port with [`pci_hp_ignore_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L510), resets with [`pci_bridge_secondary_bus_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4854) on the same port, closes the bracket and releases the lock. The comment above the function still describes masking the notifications, which commit [2af781a9edc4](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=2af781a9edc4ef5f6684c0710cc3542d9be48b31) replaced with the bracket, so the lines below the comment are the current behavior.

[`pci_bridge_secondary_bus_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4854) is the PCI core's reset of a bridge's secondary bus, here the link between the hotplug port and its slot. Read it together with the two functions above it, which write the Bridge Control bit.

```c
/* drivers/pci/pci.c:4824 */
void pci_reset_secondary_bus(struct pci_dev *dev)
{
	u16 ctrl;

	pci_read_config_word(dev, PCI_BRIDGE_CONTROL, &ctrl);
	ctrl |= PCI_BRIDGE_CTL_BUS_RESET;
	pci_write_config_word(dev, PCI_BRIDGE_CONTROL, ctrl);

	/*
	 * PCI spec v3.0 7.6.4.2 requires minimum Trst of 1ms.  Double
	 * this to 2ms to ensure that we meet the minimum requirement.
	 */
	msleep(2);

	ctrl &= ~PCI_BRIDGE_CTL_BUS_RESET;
	pci_write_config_word(dev, PCI_BRIDGE_CONTROL, ctrl);
}

void __weak pcibios_reset_secondary_bus(struct pci_dev *dev)
{
	pci_reset_secondary_bus(dev);
}

/**
 * pci_bridge_secondary_bus_reset - Reset the secondary bus on a PCI bridge.
 * @dev: Bridge device
 *
 * Use the bridge control register to assert reset on the secondary bus.
 * Devices on the secondary bus are left in power-on state.
 */
int pci_bridge_secondary_bus_reset(struct pci_dev *dev)
{
	if (!dev->block_cfg_access)
		pci_warn_once(dev, "unlocked secondary bus reset via: %pS\n",
			      __builtin_return_address(0));
	pcibios_reset_secondary_bus(dev);

	return pci_bridge_wait_for_secondary_bus(dev, "bus reset");
}
EXPORT_SYMBOL_GPL(pci_bridge_secondary_bus_reset);
```

[`pci_reset_secondary_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4824) sets [`PCI_BRIDGE_CTL_BUS_RESET`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L172), sleeps 2 ms, twice the 1 ms minimum its comment cites, and clears the bit, keeping the other bits as it read them. [`pcibios_reset_secondary_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4842) is a weak hook that x86 does not override, so this generic write is the reset on x86. [`pci_bridge_secondary_bus_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4854) warns once when [`block_cfg_access`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L466) is clear, the sign of a caller that did not lock the bridge, and returns what [`pci_bridge_wait_for_secondary_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4724) reports.

[`pci_bridge_wait_for_secondary_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4724) makes the reset last until the link and the first device below answer again, which keeps the bracket open across the Link Up too. Read its first lines and its PCIe stage.

```c
/* drivers/pci/pci.c:4724 */
int pci_bridge_wait_for_secondary_bus(struct pci_dev *dev, char *reset_type)
{
	struct pci_dev *child __free(pci_dev_put) = NULL;
	int delay;

	if (pci_dev_is_disconnected(dev))
		return 0;
	... /* 53 lines, to :4784 */
	if (!pcie_downstream_port(dev))
		return 0;

	if (pcie_get_speed_cap(dev) <= PCIE_SPEED_5_0GT) {
		u16 status;

		pci_dbg(dev, "waiting %d ms for downstream link\n", delay);
		msleep(delay);

		if (!pci_dev_wait(child, reset_type, PCI_RESET_WAIT - delay))
			return 0;

		/*
		 * If the port supports active link reporting we now check
		 * whether the link is active and if not bail out early with
		 * the assumption that the device is not present anymore.
		 */
		if (!dev->link_active_reporting)
			return -ENOTTY;

		pcie_capability_read_word(dev, PCI_EXP_LNKSTA, &status);
		if (!(status & PCI_EXP_LNKSTA_DLLLA))
			return -ENOTTY;

		return pci_dev_wait(child, reset_type,
				    PCIE_RESET_READY_POLL_MS - PCI_RESET_WAIT);
	}

	pci_dbg(dev, "waiting %d ms for downstream link, after activation\n",
		delay);
	if (!pcie_wait_for_link_delay(dev, true, delay)) {
		/* Did not train, no need to wait any further */
		pci_info(dev, "Data Link Layer Link Active not set in %d msec\n", delay);
		return -ENOTTY;
	}

	return pci_dev_wait(child, reset_type,
			    PCIE_RESET_READY_POLL_MS - delay);
}
```

A port at 5 GT/s or less sleeps the delay and then polls the first device below for up to [`PCI_RESET_WAIT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L74) minus that delay, 1000 ms in all. A faster port first waits for the link to set [`PCI_EXP_LNKSTA_DLLLA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L593), at [`pci.c:4814`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4814), and then polls the device for up to [`PCIE_RESET_READY_POLL_MS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L82) minus the delay, 60000 ms in all. Both returns come after these waits, so the Link Up of a successful reset falls inside the bracket. The two limits are macros of [`pci.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c) whose comments give their source; read them.

```c
/* drivers/pci/pci.c:69 */
/*
 * Following exit from Conventional Reset, devices must be ready within 1 sec
 * (PCIe r6.0 sec 6.6.1).  A D3cold to D0 transition implies a Conventional
 * Reset (PCIe r6.0 sec 5.8).
 */
#define PCI_RESET_WAIT 1000 /* msec */

/*
 * Devices may extend the 1 sec period through Request Retry Status
 * completions (PCIe r6.0 sec 2.3.1).  The spec does not provide an upper
 * limit, but 60 sec ought to be enough for any device to become
 * responsive.
 */
#define PCIE_RESET_READY_POLL_MS 60000 /* msec */
```

[`PCI_RESET_WAIT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L74) is the 1 s within which a device must be ready after a Conventional Reset. [`PCIE_RESET_READY_POLL_MS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L82) is the 60 s the kernel allows a device that keeps answering with Request Retry Status. The figure stacks the intervals of [`pciehp_reset_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L939) and shows what the link and the interrupt thread see inside each.

```text
    What holds while pciehp_reset_slot resets the link below its port
    ─────────────────────────────────────────────────────────────────

    time ──────────────────────────────────────────────────────────────────────────────────────────────────────────▶
    reset_lock held for writing   ├────────────────────────────────────────────────────────────────────────┤
    PCI_LINK_CHANGING set           ├──────────────────────────────────────────────┤
    SBR bit set, 2 ms                 ├────────┤
    wait for link and device                   ├──────────────────────────────┤
                                      ╎        ╎                              ╎    ╎                       ╎
    Link Active (DLLLA)           1   ╎ 1, 0   ╎ 0, then 1 as the link trains ╎ 1  ╎ 1                     ╎ 1
    IRQ thread                        ╎ woken  ╎ sleeps on the wait queue     ╎    ╎ waits for reset_lock  ╎ re-check
```

The thread that meets the Link Down sleeps until the bracket closes and then waits for [`reset_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114), which is still held for writing, before its check reads the link.

So far, a reset through pciehp's slot method opens the bracket before the link goes down and closes it after the link and the device are back. The interrupt thread drops the flap after the close. What remains for this cause is how a reset request reaches the slot method.

### The hotplug core hands a slot reset to pciehp

The bracket covers a reset when the reset comes through the slot method, so the routes by which the PCI core resets a slot decide whether a flap is marked. [`pci_reset_hotplug_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4883) is the call through the method, and [`pci_dev_reset_slot_function()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4898), defined after it, uses it to reset a function by resetting its slot. Read both.

```c
/* drivers/pci/pci.c:4883 */
static int pci_reset_hotplug_slot(struct hotplug_slot *hotplug, bool probe)
{
	int rc = -ENOTTY;

	if (!hotplug || !try_module_get(hotplug->owner))
		return rc;

	if (hotplug->ops->reset_slot)
		rc = hotplug->ops->reset_slot(hotplug, probe);

	module_put(hotplug->owner);

	return rc;
}

static int pci_dev_reset_slot_function(struct pci_dev *dev, bool probe)
{
	if (dev->multifunction || dev->subordinate || !dev->slot ||
	    dev->dev_flags & PCI_DEV_FLAGS_NO_BUS_RESET)
		return -ENOTTY;

	return pci_reset_hotplug_slot(dev->slot->hotplug, probe);
}
```

[`pci_reset_hotplug_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4883) pins the slot driver's module and calls [`reset_slot`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L47), and it returns -ENOTTY for a slot with no hotplug driver or no method. [`pci_dev_reset_slot_function()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4898) accepts a function that has a slot, is not part of a multi-function device and has no bus below it, so that the slot reset touches that function alone. The function-level "bus" reset method calls it first, at [`pci.c:4955`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4955), before it falls back to a reset of the parent bus.

[`pci_slot_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L5519) resets a [`struct pci_slot`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L85) as a whole, the path that error recovery takes. Read it for the lock around the call.

```c
/* drivers/pci/pci.c:5519 */
static int pci_slot_reset(struct pci_slot *slot, bool probe)
{
	int rc;

	if (!slot || !pci_slot_resettable(slot))
		return -ENOTTY;

	if (!probe)
		pci_slot_lock(slot);

	might_sleep();

	rc = pci_reset_hotplug_slot(slot->hotplug, probe);

	if (!probe)
		pci_slot_unlock(slot);

	return rc;
}
```

A probe passes through without the slot lock and reaches [`pciehp_reset_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L939) with probe set, which returns 0. A real reset takes the slot lock and then calls [`pci_reset_hotplug_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4883). pciehp's bracket thus runs with the devices of the slot locked, and their state stays as the reset leaves it. [`pci_try_reset_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L5566) is the variant that saves and restores that state; read it.

```c
/* drivers/pci/pci.c:5566 */
static int pci_try_reset_slot(struct pci_slot *slot)
{
	int rc;

	rc = pci_slot_reset(slot, PCI_RESET_PROBE);
	if (rc)
		return rc;

	if (pci_slot_trylock(slot)) {
		pci_slot_save_and_disable_locked(slot);
		might_sleep();
		rc = pci_reset_hotplug_slot(slot->hotplug, PCI_RESET_DO_RESET);
		pci_slot_restore_locked(slot);
		pci_slot_unlock(slot);
	} else
		rc = -EAGAIN;

	return rc;
}
```

[`pci_try_reset_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L5566) probes first, then takes the slot lock with a trylock and returns -EAGAIN when another holder has it. Inside the lock it saves and disables the devices of the slot, calls [`pci_reset_hotplug_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4883) and restores them. The reset that pciehp brackets thus falls between a save and a restore of every device in the slot. Both variants end in the same call, and the next subsection shows the bus-level entries that choose between them and a plain bus reset.

### Bus-level resets choose the slot method when it is offered

A driver that needs its device reset together with everything on the same bus asks for a bus reset. The bracket covers that reset when the PCI core turns it into a slot reset. [`pci_reset_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L5714) is the exported entry for that request. Read it for the choice it makes.

```c
/* drivers/pci/pci.c:5707 */

/**
 * pci_reset_bus - Try to reset a PCI bus
 * @pdev: top level PCI device to reset via slot/bus
 *
 * Same as above except return -EAGAIN if the bus cannot be locked
 */
int pci_reset_bus(struct pci_dev *pdev)
{
	return (!pci_probe_reset_slot(pdev->slot)) ?
	    pci_try_reset_slot(pdev->slot) : pci_try_reset_bus(pdev->bus);
}
EXPORT_SYMBOL_GPL(pci_reset_bus);
```

[`pci_reset_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L5714) probes the slot of the device and takes [`pci_try_reset_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L5566) when the probe returns 0, which for a slot of pciehp it does. Otherwise it resets the whole bus with [`pci_try_reset_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L5613). Read that function with [`pci_bus_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L5586) above it, the two plain bus resets.

```c
/* drivers/pci/pci.c:5586 */
static int pci_bus_reset(struct pci_bus *bus, bool probe)
{
	int ret;

	if (!bus->self || !pci_bus_resettable(bus))
		return -ENOTTY;

	if (probe)
		return 0;

	pci_bus_lock(bus);

	might_sleep();

	ret = pci_bridge_secondary_bus_reset(bus->self);

	pci_bus_unlock(bus);

	return ret;
}

/**
 * pci_try_reset_bus - Try to reset a PCI bus
 * @bus: top level PCI bus to reset
 *
 * Same as above except return -EAGAIN if the bus cannot be locked
 */
static int pci_try_reset_bus(struct pci_bus *bus)
{
	int rc;

	rc = pci_bus_reset(bus, PCI_RESET_PROBE);
	if (rc)
		return rc;

	if (pci_bus_trylock(bus)) {
		pci_bus_save_and_disable_locked(bus);
		might_sleep();
		rc = pci_bridge_secondary_bus_reset(bus->self);
		pci_bus_restore_locked(bus);
		pci_bus_unlock(bus);
	} else
		rc = -EAGAIN;

	return rc;
}
```

Both functions call [`pci_bridge_secondary_bus_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4854) on the bridge above the bus directly, with the bus locked and no bracket around the call. A plain bus reset of a bus below a hotplug port therefore flaps the link with no mark on the port, and pciehp sees the flap as a removal. The kernel avoids that by choosing the slot method wherever a slot of the bus offers one, as the next subsection shows for a bridge's whole bus.

### reset_subordinate takes the slot method since v7.1

A reset of everything below a bridge is requested by the `reset_subordinate` attribute of the bridge in sysfs and by AER recovery at a port. Both reach [`pci_reset_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L5645), which commit [8238cb69c01f](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=8238cb69c01fe4dbb4e3be277fff3ed680ac0108) ("PCI: Make reset_subordinate hotplug safe") made try the slots of the bus first, so that a hotplug port's bus is reset through pciehp. Read it whole.

```c
/* drivers/pci/pci.c:5645 */
static int pci_reset_bridge(struct pci_dev *bridge, bool restore)
{
	struct pci_bus *bus = bridge->subordinate;
	struct pci_slot *slot;
	int ret = 0;

	if (!bus)
		return -ENOTTY;

	mutex_lock(&pci_slot_mutex);
	if (list_empty(&bus->slots))
		goto bus_reset;

	list_for_each_entry(slot, &bus->slots, list)
		if (pci_probe_reset_slot(slot))
			goto bus_reset;

	list_for_each_entry(slot, &bus->slots, list) {
		if (restore)
			ret = pci_try_reset_slot(slot);
		else
			ret = pci_slot_reset(slot, PCI_RESET_DO_RESET);

		if (ret)
			break;
	}

	mutex_unlock(&pci_slot_mutex);
	return ret;
bus_reset:
	mutex_unlock(&pci_slot_mutex);

	if (restore)
		return pci_try_reset_bus(bus);
	return pci_bus_reset(bridge->subordinate, PCI_RESET_DO_RESET);
}
```

[`pci_reset_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L5645) goes to the bus reset when the bus has no slot on its [`slots`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L708) list or when the probe of any slot fails. Otherwise it resets each slot in turn, with [`pci_try_reset_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L5566) when restore is true and with [`pci_slot_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L5519) when it is false, and it stops at the first failure. commit [cfcbfe5cb116](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=cfcbfe5cb11650d53f7cafd7adfd556690b77114) ("PCI: Don't fallback to bus reset after failed slot reset") removed the fall back to a bus reset after a failed slot reset; according to its message, that second reset would flap the link again with no bracket. The figure lays the choices out.

```text
    A reset of the bus below a bridge goes slot by slot when every slot can reset itself
    ────────────────────────────────────────────────────────────────────────────────────

    ┌───────────────────────────────────┐
    │ no slot on the bus's slots list?  ├─ yes ───────────────────────────┐
    └─────────────────┬─────────────────┘                                 │
                      │ no                                                │
    ┌─────────────────▼─────────────────┐                                 │
    │ a slot's reset probe fails?       ├─ yes ───────────────────────────┤
    └─────────────────┬─────────────────┘                                 │
                      │ no                                                ▼
    ┌─────────────────▼─────────────────┐               ┌─────────────────────────────────────┐
    │ reset the next slot through its   │◀─┐            │ Secondary Bus Reset of the bus,     │
    │ hotplug driver; with restore, the │  │            │ outside any bracket; with restore,  │
    │ slot is saved before and restored │  │            │ the bus is saved and restored       │
    │ after the reset                   │  │            └─────────────────────────────────────┘
    └─────────────────┬─────────────────┘  │
    ┌─────────────────▼─────────────────┐  │
    │ the reset failed, or no slot left?├──┘ no
    └─────────────────┬─────────────────┘
                      │ yes
                      ▼
      return the result: a failed slot reset is never followed by a bus reset
```

The two callers differ in the restore argument, and both are short. Read [`pci_bus_error_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L5686) and [`pci_try_reset_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L5691).

```c
/* drivers/pci/pci.c:5682 */
/**
 * pci_bus_error_reset - reset the bridge's subordinate bus
 * @bridge: The parent device that connects to the bus to reset
 */
int pci_bus_error_reset(struct pci_dev *bridge)
{
	return pci_reset_bridge(bridge, PCI_RESET_NO_RESTORE);
}

int pci_try_reset_bridge(struct pci_dev *bridge)
{
	return pci_reset_bridge(bridge, PCI_RESET_RESTORE);
}
```

Error recovery uses [`pci_bus_error_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L5686), without restore, and the sysfs attribute uses [`pci_try_reset_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L5691), with restore. The attribute is [`reset_subordinate_store()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-sysfs.c#L552) of [`pci-sysfs.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-sysfs.c), declared by the `DEVICE_ATTR_WO(reset_subordinate)` line after it; read both.

```c
/* drivers/pci/pci-sysfs.c:552 */
static ssize_t reset_subordinate_store(struct device *dev,
				struct device_attribute *attr,
				const char *buf, size_t count)
{
	struct pci_dev *pdev = to_pci_dev(dev);
	unsigned long val;

	if (!capable(CAP_SYS_ADMIN))
		return -EPERM;

	if (kstrtoul(buf, 0, &val) < 0)
		return -EINVAL;

	if (val) {
		int ret = pci_try_reset_bridge(pdev);

		if (ret)
			return ret;
	}

	return count;
}
static DEVICE_ATTR_WO(reset_subordinate);
```

A write of a nonzero value by a holder of `CAP_SYS_ADMIN` resets everything below the bridge through [`pci_try_reset_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L5691), and an error from the reset becomes the write's return value. The message of commit [8238cb69c01f](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=8238cb69c01fe4dbb4e3be277fff3ed680ac0108) shows the difference in the log, a "Slot(40): Link Down" before the change and a "Slot(40): Link Down/Up ignored" after it. The AER side is [`aer_root_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1667), the reset callback that AER recovery passes to the PCI core; read its stages.

```c
/* drivers/pci/pcie/aer.c:1667 */
static pci_ers_result_t aer_root_reset(struct pci_dev *dev)
{
	int type = pci_pcie_type(dev);
	struct pci_dev *root;
	int aer;
	struct pci_host_bridge *host = pci_find_host_bridge(dev->bus);
	u32 reg32;
	int rc;
	... /* 21 lines, to :1696 */
	if (type == PCI_EXP_TYPE_RC_EC || type == PCI_EXP_TYPE_RC_END) {
		rc = pcie_reset_flr(dev, PCI_RESET_DO_RESET);
		if (!rc)
			pci_info(dev, "has been reset\n");
		else
			pci_info(dev, "not reset (no FLR support: %d)\n", rc);
	} else {
		rc = pci_bus_error_reset(dev);
		pci_info(dev, "%s Port link has been reset (%d)\n",
			pci_is_root_bus(dev->bus) ? "Root" : "Downstream", rc);
	}
```

For a Root Port or Downstream Port, [`aer_root_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1667) calls [`pci_bus_error_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L5686) on the port and logs "%s Port link has been reset (%d)" with Root or Downstream and the result. When that port is a hotplug port, the reset is pciehp's bracketed slot reset, which needs [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28) for the AER service and [`CONFIG_HOTPLUG_PCI_PCIE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L16) for the slot method. Every reset route of this page that reaches [`pciehp_reset_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L939) thus brackets the flap at the hotplug port itself. The ports below a reset port see a Hot Reset with no bracket, which a later subsection takes up.

### DPC recovery records its progress in two bits

Downstream Port Containment is a port's hardware response to an uncorrectable error below it, which disables the link at the port so that no more traffic crosses it. The kernel sees it through the DPC capability at [`dpc_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L537) and its Trigger Status bit, [`PCI_EXP_DPC_STATUS_TRIGGER`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1097), which holds the link down until software clears it. At a hotplug port the disabled link is a Link Down. DPC therefore records its recovery in [`PCI_DPC_RECOVERING`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L770) and [`PCI_DPC_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L769) of the port's [`priv_flags`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L585), and pciehp reads the record and keeps the device that recovery gives back.

[`dpc_handler()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L363) is the DPC service's interrupt thread, run when the port reports that it triggered. Read it for the branch taken on a surprise removal and for the recovery call.

```c
/* drivers/pci/pcie/dpc.c:363 */
static irqreturn_t dpc_handler(int irq, void *context)
{
	struct pci_dev *pdev = context;

	/*
	 * According to PCIe r6.0 sec 6.7.6, errors are an expected side effect
	 * of async removal and should be ignored by software.
	 */
	if (dpc_is_surprise_removal(pdev)) {
		dpc_handle_surprise_removal(pdev);
		return IRQ_HANDLED;
	}

	pci_dev_get(pdev);
	dpc_process_error(pdev);

	/* We configure DPC so it only triggers on ERR_FATAL */
	pcie_do_recovery(pdev, pci_channel_io_frozen, dpc_reset_link);

	pci_dev_put(pdev);
	return IRQ_HANDLED;
}
```

A surprise removal goes to [`dpc_handle_surprise_removal()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L328) and returns. Any other trigger is logged and then recovered by [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210), with [`dpc_reset_link()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L148) as the reset of the port's link. [`dpc_reset_link()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L148) is the recovery that writes the two bits; read it whole.

```c
/* drivers/pci/pcie/dpc.c:148 */
pci_ers_result_t dpc_reset_link(struct pci_dev *pdev)
{
	pci_ers_result_t ret;
	u16 cap;

	set_bit(PCI_DPC_RECOVERING, &pdev->priv_flags);

	/*
	 * DPC disables the Link automatically in hardware, so it has
	 * already been reset by the time we get here.
	 */
	cap = pdev->dpc_cap;

	/*
	 * Wait until the Link is inactive, then clear DPC Trigger Status
	 * to allow the Port to leave DPC.
	 */
	if (!pcie_wait_for_link(pdev, false))
		pci_info(pdev, "Data Link Layer Link Active not cleared in 1000 msec\n");

	if (pdev->dpc_rp_extensions && dpc_wait_rp_inactive(pdev)) {
		clear_bit(PCI_DPC_RECOVERED, &pdev->priv_flags);
		ret = PCI_ERS_RESULT_DISCONNECT;
		goto out;
	}

	pci_write_config_word(pdev, cap + PCI_EXP_DPC_STATUS,
			      PCI_EXP_DPC_STATUS_TRIGGER);

	if (pci_bridge_wait_for_secondary_bus(pdev, "DPC")) {
		clear_bit(PCI_DPC_RECOVERED, &pdev->priv_flags);
		ret = PCI_ERS_RESULT_DISCONNECT;
	} else {
		set_bit(PCI_DPC_RECOVERED, &pdev->priv_flags);
		ret = PCI_ERS_RESULT_RECOVERED;
	}
out:
	clear_bit(PCI_DPC_RECOVERING, &pdev->priv_flags);
	wake_up_all(&dpc_completed_waitqueue);
	return ret;
}
```

[`dpc_reset_link()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L148) sets [`PCI_DPC_RECOVERING`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L770) first and waits for the link to go down, logging "Data Link Layer Link Active not cleared in 1000 msec" when it does not. A Root Port with the RP extensions, [`dpc_rp_extensions`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L538) set, then waits for Root Port Busy to clear. The function clears the trigger with a write of [`PCI_EXP_DPC_STATUS_TRIGGER`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1097) and waits for the secondary bus with [`pci_bridge_wait_for_secondary_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4724). A ready bus sets [`PCI_DPC_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L769), either failure clears it, and the code at the out label clears [`PCI_DPC_RECOVERING`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L770) and wakes [`dpc_completed_waitqueue`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L78) on every path.

A surprise removal ends containment without a recovery, and [`dpc_handle_surprise_removal()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L328) makes sure pciehp does not read it as one. Read it with [`dpc_is_surprise_removal()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L349) after it.

```c
/* drivers/pci/pcie/dpc.c:328 */
static void dpc_handle_surprise_removal(struct pci_dev *pdev)
{
	if (!pcie_wait_for_link(pdev, false)) {
		pci_info(pdev, "Data Link Layer Link Active not cleared in 1000 msec\n");
		goto out;
	}

	if (pdev->dpc_rp_extensions && dpc_wait_rp_inactive(pdev))
		goto out;

	pci_aer_raw_clear_status(pdev);
	pci_clear_surpdn_errors(pdev);

	pci_write_config_word(pdev, pdev->dpc_cap + PCI_EXP_DPC_STATUS,
			      PCI_EXP_DPC_STATUS_TRIGGER);

out:
	clear_bit(PCI_DPC_RECOVERED, &pdev->priv_flags);
	wake_up_all(&dpc_completed_waitqueue);
}

static bool dpc_is_surprise_removal(struct pci_dev *pdev)
{
	u16 status;

	if (!pdev->is_hotplug_bridge)
		return false;

	if (pci_read_config_word(pdev, pdev->aer_cap + PCI_ERR_UNCOR_STATUS,
				 &status))
		return false;

	return status & PCI_ERR_UNC_SURPDN;
}
```

[`dpc_is_surprise_removal()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L349) answers true for a hotplug bridge, [`is_hotplug_bridge`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L483) set, whose AER Uncorrectable Error Status holds [`PCI_ERR_UNC_SURPDN`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L775), the Surprise Down error. [`dpc_handle_surprise_removal()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L328) then clears [`PCI_DPC_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L769) and wakes the queue without touching [`PCI_DPC_RECOVERING`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L770), so a pciehp thread waiting on DPC wakes to an empty record and handles the removal. The figure gives every move of the two bits at one DPC port, pciehp's read included.

```text
    The PCI_DPC_RECOVERING and PCI_DPC_RECOVERED pair of one DPC port
    ─────────────────────────────────────────────────────────────────

    ┌────────────────────┐        ➊ containment starts        ┌──────────────────────────────────┐
    │ no record          │ ──────────────────────────────────▶│ recovering                       │
    │ RECOVERING 0       │                                    │ RECOVERING 1                     │
    │ RECOVERED  0       │ ◀───────────────────────────────── │ RECOVERED  0 after ➋ or ➌,       │
    └────────────────────┘    ➎ recovery ends after ➋ or ➌    │ RECOVERED  1 after ➍             │
         ▲    ▲                                               └─────────┬────────────────────────┘
         │    │                                                         │                   ▲
         │    │                                                         │ ➎ ends after ➍    │ ➊ contained again
         │    │                                                         │                   │
         │    │                                                         ▼                   │
         │    │  ➏ surprise removal ends containment          ┌─────────────────────────────┴────┐
         │    └───────────────────────────────────────────────┤ recovered                        │
         └────────────────────────────────────────────────────┤ RECOVERING 0                     │
            ➐ pciehp takes the record and reads true          │ RECOVERED  1                     │
                                                              └──────────────────────────────────┘

    ➊ dpc_reset_link              dpc.c:153  sets PCI_DPC_RECOVERING as recovery of the link starts
    ➋ dpc_reset_link              :169       clears PCI_DPC_RECOVERED when the Root Port stays busy
    ➌ dpc_reset_link              :178       clears PCI_DPC_RECOVERED when the secondary bus stays unready
    ➍ dpc_reset_link              :181       sets PCI_DPC_RECOVERED when the secondary bus came back
    ➎ dpc_reset_link              :185       clears PCI_DPC_RECOVERING on every exit of the recovery
    ➏ dpc_handle_surprise_removal :345       clears PCI_DPC_RECOVERED after a surprise removal
    ➐ pci_dpc_recovered           :126       clears PCI_DPC_RECOVERED and returns its old value to pciehp
```

➊ [`dpc_reset_link()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L148) sets [`PCI_DPC_RECOVERING`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L770) as recovery starts. ➋ `dpc_reset_link()` clears [`PCI_DPC_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L769) when the Root Port stays busy. ➌ `dpc_reset_link()` clears it as well when the secondary bus does not come back. ➍ `dpc_reset_link()` sets [`PCI_DPC_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L769) when the secondary bus is ready. ➎ `dpc_reset_link()` clears [`PCI_DPC_RECOVERING`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L770) on its way out, leaving the pair recovered or empty by the outcome. ➏ [`dpc_handle_surprise_removal()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L328) clears [`PCI_DPC_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L769) after a surprise removal. ➐ [`pci_dpc_recovered()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L103) clears [`PCI_DPC_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L769) and returns its old value, true from the recovered state and false from the empty one.

At v7.2 these seven sites are every write of the two bits, so the figure leaves out no writer. A second containment before pciehp reads the record moves the pair from recovered back to recovering, and [`dpc_completed()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L81), which tests [`PCI_DPC_RECOVERING`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L770) without writing it, is the reader the next subsection shows.

### pci_dpc_recovered waits until containment has ended

pciehp's side of DPC is [`pci_dpc_recovered()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L103), which [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728) calls first in its test. It asks whether a containment at this port ended in a recovery. When containment is still running it waits, because the DPC and pciehp threads are woken by the same flap and either can run first. The message of commit [a97396c6eb13](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=a97396c6eb13f65bea894dbe7739b2e883d40a3e) ("PCI: pciehp: Ignore Link Down/Up caused by DPC") describes the two threads as racing against each other. [`dpc_completed()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L81) is the condition of the wait, defined below the queue it sleeps on; read both, with the [`CONFIG_HOTPLUG_PCI_PCIE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L16) guard that opens around the part of dpc.c that pciehp uses.

```c
/* drivers/pci/pcie/dpc.c:78 */
static DECLARE_WAIT_QUEUE_HEAD(dpc_completed_waitqueue);

#ifdef CONFIG_HOTPLUG_PCI_PCIE
static bool dpc_completed(struct pci_dev *pdev)
{
	u16 status;

	pci_read_config_word(pdev, pdev->dpc_cap + PCI_EXP_DPC_STATUS, &status);
	if ((!PCI_POSSIBLE_ERROR(status)) && (status & PCI_EXP_DPC_STATUS_TRIGGER))
		return false;

	if (test_bit(PCI_DPC_RECOVERING, &pdev->priv_flags))
		return false;

	return true;
}
```

[`dpc_completed()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L81) reads DPC Status and answers false while a readable value holds [`PCI_EXP_DPC_STATUS_TRIGGER`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1097), then false while [`PCI_DPC_RECOVERING`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L770) is set, and true otherwise. A read that fails counts as completed, so a port that has gone away does not keep the thread asleep. [`pci_dpc_recovered()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L103) puts this condition behind two early returns and a bounded wait; read it whole.

```c
/* drivers/pci/pcie/dpc.c:95 */
/**
 * pci_dpc_recovered - whether DPC triggered and has recovered successfully
 * @pdev: PCI device
 *
 * Return true if DPC was triggered for @pdev and has recovered successfully.
 * Wait for recovery if it hasn't completed yet.  Called from the PCIe hotplug
 * driver to recognize and ignore Link Down/Up events caused by DPC.
 */
bool pci_dpc_recovered(struct pci_dev *pdev)
{
	struct pci_host_bridge *host;

	if (!pdev->dpc_cap)
		return false;

	/*
	 * Synchronization between hotplug and DPC is not supported
	 * if DPC is owned by firmware and EDR is not enabled.
	 */
	host = pci_find_host_bridge(pdev->bus);
	if (!host->native_dpc && !IS_ENABLED(CONFIG_PCIE_EDR))
		return false;

	/*
	 * Need a timeout in case DPC never completes due to failure of
	 * dpc_wait_rp_inactive().  The spec doesn't mandate a time limit,
	 * but reports indicate that DPC completes within 4 seconds.
	 */
	wait_event_timeout(dpc_completed_waitqueue, dpc_completed(pdev),
			   msecs_to_jiffies(4000));

	return test_and_clear_bit(PCI_DPC_RECOVERED, &pdev->priv_flags);
}
#endif /* CONFIG_HOTPLUG_PCI_PCIE */
```

A port without the DPC capability, [`dpc_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L537) zero, answers false at once. So does a port whose host bridge left DPC to firmware, [`native_dpc`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L658) clear, unless [`CONFIG_PCIE_EDR`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L140) is set. The page assumes that option unset, so pciehp handles a firmware-owned containment as a removal. The wait lasts at most 4000 ms, a limit the comment takes from reports. The message of commit [a97396c6eb13](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=a97396c6eb13f65bea894dbe7739b2e883d40a3e) mentions a containment that took a little over 3 s on one platform.

The function returns the old value of [`PCI_DPC_RECOVERED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L769) and clears it, so a recovery excuses the first pass of the thread that reads it and no later pass. With [`CONFIG_PCIE_DPC`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L121) unset, drivers/pci/pci.h declares an inline in its place; read the declarations.

```c
/* drivers/pci/pci.h:882 */
#ifdef CONFIG_PCIE_DPC
void pci_save_dpc_state(struct pci_dev *dev);
void pci_restore_dpc_state(struct pci_dev *dev);
void pci_dpc_init(struct pci_dev *pdev);
void dpc_process_error(struct pci_dev *pdev);
pci_ers_result_t dpc_reset_link(struct pci_dev *pdev);
bool pci_dpc_recovered(struct pci_dev *pdev);
unsigned int dpc_tlp_log_len(struct pci_dev *dev);
#else
static inline void pci_save_dpc_state(struct pci_dev *dev) { }
static inline void pci_restore_dpc_state(struct pci_dev *dev) { }
static inline void pci_dpc_init(struct pci_dev *pdev) { }
static inline bool pci_dpc_recovered(struct pci_dev *pdev) { return false; }
#endif
```

Without DPC the inline returns false and the test moves on to [`pci_hp_spurious_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L552). With it, the figure shows the order of the two threads when pciehp's arrives first.

```text
    The pciehp IRQ thread waits on DPC recovery when it arrives first
    ─────────────────────────────────────────────────────────────────

    time ↓
    DPC port hardware             ╎ DPC IRQ thread                ╎ pciehp IRQ thread
    ──────────────────────────────┼───────────────────────────────┼─────────────────────────────────
    error: DPC triggers, the      ╎                               ╎
    link goes down, Trigger       ╎                               ╎
    Status 1, DLLSC set           ╎ DPC IRQ thread woken          ╎ woken with DLLSC
                                  ╎ RECOVERING set                ╎ RECOVERING set or Trigger
                                  ╎ waits for the link to         ╎ Status 1: sleeps on
                                  ╎ go down                       ╎ dpc_completed_waitqueue,
    Trigger Status cleared        ╎ writes Trigger Status         ╎ at most 4 s
    link trains, DLLSC set        ╎ waits for the secondary       ╎
                                  ╎ bus                           ╎
                                  ╎ RECOVERED set,                ╎
                                  ╎ RECOVERING cleared,           ╎
                                  ╎ waiters woken ────────────────▶ wakes: Trigger Status 0,
                                  ╎                               ╎ RECOVERING 0; takes
                                  ╎                               ╎ RECOVERED, drops the events

    when DPC finishes first, the pciehp IRQ thread finds both conditions already true,
    does not sleep, and takes the RECOVERED bit that the DPC IRQ thread left set
```

So far, a containment at the hotplug port and a reset through its slot method both leave a record on the port's [`priv_flags`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L585). The interrupt thread waits for each to end before it drops [`PCI_EXP_SLTSTA_DLLSC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L642) and [`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637). The dropped events still have to be cleared from the controller, which the next subsection shows.

### Dropping the events clears what collected during the wait

Once a cause has explained the events, [`pciehp_ignore_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L596) removes them from the controller and logs the decision. The thread may have slept in either cause test for up to 4000 ms or for the length of a reset. In that time the hard handler went on ORing new events, the Link Up among them, into [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104). Read [`pciehp_ignore_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L596) whole.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:596 */
static void pciehp_ignore_link_change(struct controller *ctrl,
				      struct pci_dev *pdev, int irq,
				      u16 ignored_events)
{
	/*
	 * Ignore link changes which occurred while waiting for DPC recovery.
	 * Could be several if DPC triggered multiple times consecutively.
	 * Also ignore link changes caused by Secondary Bus Reset, etc.
	 */
	synchronize_hardirq(irq);
	atomic_and(~ignored_events, &ctrl->pending_events);
	if (pciehp_poll_mode)
		pcie_capability_write_word(pdev, PCI_EXP_SLTSTA,
					   ignored_events);
	ctrl_info(ctrl, "Slot(%s): Link Down/Up ignored\n", slot_name(ctrl));

	/*
	 * If the link is unexpectedly down after successful recovery,
	 * the corresponding link change may have been ignored above.
	 * Synthesize it to ensure that it is acted on.
	 */
	down_read_nested(&ctrl->reset_lock, ctrl->depth);
	if (!pciehp_check_link_active(ctrl) || pciehp_device_replaced(ctrl))
		pciehp_request(ctrl, ignored_events);
	up_read(&ctrl->reset_lock);
}
```

`synchronize_hardirq()` waits for a hard handler running on the interrupt to finish, so its last store is in the word before `atomic_and()` clears the ignored bits there. With [`pciehp_poll_mode`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L34) set no interrupt copied the events of the wait, which are still latched in Slot Status, and the function writes them back to clear them in the register. The decision is logged at the info level as "Slot(%s): Link Down/Up ignored".

The clear works on the word, which commit [bbf10cd68683](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=bbf10cd686835d5a4b8566dc73a3b00b4cd7932a) ("PCI: pciehp: Ignore belated Presence Detect Changed caused by DPC") made the rule for the presence bit. According to its message, the set to clear used to come from the thread's local events. A Presence Detect Changed that arrived after the first Link Down then stayed in the word and brought the slot down later. The figure shows the word before and after the clear, and after the request that the next subsection explains.

```text
    The controller's pending_events before and after the IRQ thread drops a flap
    ────────────────────────────────────────────────────────────────────────────

                                DISABLE_SLOT    DLLSC      PDC       PFD       ABP
                                   bit 16       bit 8     bit 3     bit 1     bit 0
                              ┌──────────────┬─────────┬─────────┬─────────┬─────────┐
    before: set while the     │      x       │    1    │    1    │    x    │    x    │
    thread waited             └──────────────┴─────────┴─────────┴─────────┴─────────┘

              atomic_and(~ignored_events) clears the two event bits, keeps the others
              │
              ▼
                              ┌──────────────┬─────────┬─────────┬─────────┬─────────┐
    after the clear           │      x       │    0    │    0    │    x    │    x    │
                              └──────────────┴─────────┴─────────┴─────────┴─────────┘

              pciehp_request(ignored_events) when the link is down or the device changed
              │
              ▼
                              ┌──────────────┬─────────┬─────────┬─────────┬─────────┐
    after a request           │      x       │    1    │    1    │    x    │    x    │
                              └──────────────┴─────────┴─────────┴─────────┴─────────┘

    x = whatever the bit held; PDC takes part only while in-band presence detect is not disabled
```

The clear leaves the bits of other events, a pending [`DISABLE_SLOT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L153) among them, as they were. After it the controller holds no trace of the flap except the log line, and the second half of the function decides whether to bring the events back.

### A link still down or a new device brings the events back

Dropping a flap assumes that the link came back and that the device behind it is the one that left. The second half of [`pciehp_ignore_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L596) tests both under [`reset_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114) taken for reading, and when either test fails it asks for the dropped events again. Read those lines again.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:596 */
static void pciehp_ignore_link_change(struct controller *ctrl,
				      struct pci_dev *pdev, int irq,
				      u16 ignored_events)
{
	... /* 12 lines, to :612 */
	/*
	 * If the link is unexpectedly down after successful recovery,
	 * the corresponding link change may have been ignored above.
	 * Synthesize it to ensure that it is acted on.
	 */
	down_read_nested(&ctrl->reset_lock, ctrl->depth);
	if (!pciehp_check_link_active(ctrl) || pciehp_device_replaced(ctrl))
		pciehp_request(ctrl, ignored_events);
	up_read(&ctrl->reset_lock);
}
```

The read lock waits for a reset that still holds [`reset_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114) for writing, so the tests run after [`pciehp_reset_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L939) has finished. A link that is not active, or a device that was replaced, sends the ignored set to [`pciehp_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L141). The comment names the case this guards, a link that is down after a recovery that succeeded. [`pciehp_check_link_active()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L235) is the link test; read it with its kerneldoc.

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

[`pciehp_check_link_active()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L235) reads Link Status and returns 1 when [`PCI_EXP_LNKSTA_DLLLA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L593) is set, 0 when it is clear and -ENODEV when the port does not answer. The caller's negation makes a request for 0 alone, since -ENODEV negates to false, so a port that has gone away is left to the paths that handle its removal. With [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) set, the debug line prints the Link Status value at each test.

[`pciehp_device_replaced()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L567) is the device test. Read it whole for the identity it compares.

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

The test looks up function 0 of the bus below the port and answers replaced when there is none. It also answers replaced when a configuration read fails. Differing Vendor and Device IDs, Revision ID and Class Code or, for a type 0 header, Subsystem IDs answer replaced as well, measured against the values cached in that function's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352). A Device Serial Number that differs from [`dsn`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L93) answers replaced too, and a port that is itself disconnected answers not replaced, since nothing can be read through it. The figure sets the two sides of the comparison against each other.

```text
    pciehp_device_replaced compares what function 0 answers now with what the kernel cached
    ───────────────────────────────────────────────────────────────────────────────────────

    read now from function 0 below the port                  cached when the device was added
    ┌─────────────────────────────────────────────────┐      ┌────────────────────────────────────────────┐
    │ Vendor ID, Device ID      (PCI_VENDOR_ID)       │      │ pci_dev.vendor, pci_dev.device             │
    │ Revision ID, Class Code   (PCI_CLASS_REVISION)  │      │ pci_dev.revision, pci_dev.class            │
    │ Subsystem IDs, type 0 header only               │      │ pci_dev.subsystem_vendor, subsystem_device │
    │ Device Serial Number      (pci_get_dsn())       │      │ controller.dsn                             │
    └───────────────────────┬─────────────────────────┘      └──────────────────────┬─────────────────────┘
                            └─────────────────────────▶ equal?  ◀───────────────────┘
                                                           │
                                                           ▼
            a difference, a failed read or no function 0 at devfn 0: replaced, true
            every value equal, or the port itself disconnected: not replaced, false
```

A device that matches on every value passes as the same device, and the drop stands. When a test fails, [`pciehp_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L141) puts the dropped events back; read it.

```c
/* drivers/pci/hotplug/pciehp_ctrl.c:141 */
void pciehp_request(struct controller *ctrl, int action)
{
	atomic_or(action, &ctrl->pending_events);
	if (!pciehp_poll_mode)
		irq_wake_thread(ctrl->pcie->irq, ctrl);
}
```

[`pciehp_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L141) ORs the action into [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104) and wakes the interrupt thread with `irq_wake_thread()` unless [`pciehp_poll_mode`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L34) is set. The thread runs again and meets the gate with both records already taken, since [`pci_dpc_recovered()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L103) and [`pci_hp_spurious_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L552) cleared them. The test fails, and the events reach the slot state machine as a removal or a replacement.

### Recovery above a port calls the slot_reset hook of the ports below

Error recovery at a port resets the link below that port through [`aer_root_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1667) or [`dpc_reset_link()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L148), and a switch that receives the reset passes a Hot Reset on to its Downstream Ports. The message of commit [ea401499e943](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=ea401499e943c307e6d44af6c2b4e068643e7884) ("PCI: pciehp: Ignore Link Down/Up caused by error-induced Hot Reset") quotes the specification for that rule and reports the result, a Link Down at a hotplug port below the switch with no mark on that port. [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) is the PCI core's recovery sequence, and after its reset it calls the slot_reset handlers of the drivers below the port. Read its first lines and the stages around the reset.

```c
/* drivers/pci/pcie/err.c:210 */
pci_ers_result_t pcie_do_recovery(struct pci_dev *dev,
		pci_channel_state_t state,
		pci_ers_result_t (*reset_subordinates)(struct pci_dev *pdev))
{
	int type = pci_pcie_type(dev);
	struct pci_dev *bridge;
	pci_ers_result_t status = PCI_ERS_RESULT_CAN_RECOVER;
	struct pci_host_bridge *host = pci_find_host_bridge(dev->bus);
	... /* 32 lines, to :250 */
	if (status == PCI_ERS_RESULT_NEED_RESET ||
	    state == pci_channel_io_frozen) {
		if (reset_subordinates(bridge) != PCI_ERS_RESULT_RECOVERED) {
			pci_warn(bridge, "subordinate device reset failed\n");
			goto failed;
		}
	}

	if (status == PCI_ERS_RESULT_NEED_RESET) {
		/*
		 * TODO: Should call platform-specific
		 * functions to reset slot before calling
		 * drivers' slot_reset callbacks?
		 */
		status = PCI_ERS_RESULT_RECOVERED;
		pci_dbg(bridge, "broadcast slot_reset message\n");
		pci_walk_bridge(bridge, report_slot_reset, &status);
	}
```

The reset callback runs on the bridge, and when the result called for a reset the sequence then visits the devices below with [`report_slot_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L148) through [`pci_walk_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L200). [`pci_walk_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L200) sets the boundary of that visit; read it.

```c
/* drivers/pci/pcie/err.c:187 */
/**
 * pci_walk_bridge - walk bridges potentially AER affected
 * @bridge:	bridge which may be a Port, an RCEC, or an RCiEP
 * @cb:		callback to be called for each device found
 * @userdata:	arbitrary pointer to be passed to callback
 *
 * If the device provided is a bridge, walk the subordinate bus, including
 * any bridged devices on buses under this bus.  Call the provided callback
 * on each device found.
 *
 * If the device provided has no subordinate bus, e.g., an RCEC or RCiEP,
 * call the callback on the device itself.
 */
static void pci_walk_bridge(struct pci_dev *bridge,
			    int (*cb)(struct pci_dev *, void *),
			    void *userdata)
{
	if (bridge->subordinate)
		pci_walk_bus(bridge->subordinate, cb, userdata);
	else
		cb(bridge, userdata);
}
```

A bridge with a bus below it is visited through every device of that bus and of the buses under it, the bridge itself excluded. A hotplug port below the recovered port is therefore called, and the recovered port is not. [`report_slot_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L148) calls the bound driver's handler; read it.

```c
/* drivers/pci/pcie/err.c:148 */
static int report_slot_reset(struct pci_dev *dev, void *data)
{
	struct pci_driver *pdrv;
	pci_ers_result_t vote, *result = data;
	const struct pci_error_handlers *err_handler;

	device_lock(&dev->dev);
	pdrv = dev->driver;
	if (!pci_dev_set_io_state(dev, pci_channel_io_normal) ||
	    !pdrv || !pdrv->err_handler || !pdrv->err_handler->slot_reset)
		goto out;

	err_handler = pdrv->err_handler;
	vote = err_handler->slot_reset(dev);
	*result = merge_result(*result, vote);
out:
	device_unlock(&dev->dev);
	return 0;
}
```

The handler belongs to the driver bound to the device, and a PCIe port bound to portdrv has [`pcie_portdrv_slot_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L758) there. Read it for the order of the services and the restore of the port.

```c
/* drivers/pci/pcie/portdrv.c:758 */
static pci_ers_result_t pcie_portdrv_slot_reset(struct pci_dev *dev)
{
	size_t off = offsetof(struct pcie_port_service_driver, slot_reset);
	device_for_each_child(&dev->dev, &off, pcie_port_device_iter);

	pci_restore_state(dev);
	return PCI_ERS_RESULT_RECOVERED;
}
```

The services of the port are children of its device, and the offset of [`slot_reset`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L88) tells [`pcie_port_device_iter()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L385) which callback to call. The restore of the port's saved registers, at [`portdrv.c:763`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L763), runs after the services. Read the iterator for how it reaches each service.

```c
/* drivers/pci/pcie/portdrv.c:385 */
static int pcie_port_device_iter(struct device *dev, void *data)
{
	struct pcie_port_service_driver *service_driver;
	size_t offset = *(size_t *)data;
	pcie_callback_t cb;

	if ((dev->bus == &pcie_port_bus_type) && dev->driver) {
		service_driver = to_service_driver(dev->driver);
		cb = *(pcie_callback_t *)((void *)service_driver + offset);
		if (cb)
			return cb(to_pcie_device(dev));
	}
	return 0;
}
```

[`pcie_port_device_iter()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L385) calls the callback of each child that is bound to a port service driver and has the callback set. pciehp sets it in [`hpdriver_portdrv`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L353), its [`struct pcie_port_service_driver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L78); read the definition.

```c
/* drivers/pci/hotplug/pciehp_core.c:353 */
static struct pcie_port_service_driver hpdriver_portdrv = {
	.name		= "pciehp",
	.port_type	= PCIE_ANY_PORT,
	.service	= PCIE_PORT_SERVICE_HP,

	.probe		= pciehp_probe,
	.remove		= pciehp_remove,

#ifdef	CONFIG_PM
#ifdef	CONFIG_PM_SLEEP
	.suspend	= pciehp_suspend,
	.resume_noirq	= pciehp_resume_noirq,
	.resume		= pciehp_resume,
#endif
	.runtime_suspend = pciehp_runtime_suspend,
	.runtime_resume	= pciehp_runtime_resume,
#endif	/* PM */

	.slot_reset	= pciehp_slot_reset,
};
```

At v7.2 [`pciehp_slot_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L915) is the one slot_reset callback that a port service driver sets, so the broadcast reaches pciehp and no other service of the port. The figure places the reset, the Hot Reset and the visit on one tree.

```text
    Recovery at a port above reaches the hotplug ports below it as a Hot Reset and a callback
    ─────────────────────────────────────────────────────────────────────────────────────────

                ┌────────────────────────────┐
    tier 1      │ Root Port: error contained │  ◀── recovery resets this link through
                │ or reported here           │      its reset_subordinates callback
                └─────────────┬──────────────┘
                              │ link reset
    ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ──┼─ ─ ─ ─ ─ ─ ─ ─  below the line: the walk calls each bound driver's slot_reset
                              │
                    ┌─────────┴──────────┐
    tier 2          │ switch Upstream    │  a Hot Reset received here goes on to
                    │ Port               │  every Downstream Port of the switch
                    └─────────┬──────────┘
                              │
                       ┌──────┴───────────────────────────┐
                       │                                  │
             ┌─────────┴──────────┐             ┌─────────┴──────────┐
    tier 3   │ Downstream Port,   │             │ Downstream Port,   │
             │ pciehp, slot on    │             │ no hotplug service │
             └─────────┬──────────┘             └─────────┬──────────┘
                       │ link flaps                       │ link flaps
             ┌─────────┴──────────┐             ┌─────────┴──────────┐
    tier 4   │ device in the slot │             │ device             │
             └────────────────────┘             └────────────────────┘
             pciehp_slot_reset clears DLLSC     no slot_reset callback, so
             before the port is restored, and   nothing is cleared
             asks for DLLSC again if the link stays down
```

The hotplug port below a recovered port thus hears of the reset through a callback after the flap, and the next subsection shows what it does then.

### pciehp_slot_reset clears the event a Hot Reset leaves

The callback runs after the link below the hotplug port has flapped, too late for a bracket, so [`pciehp_slot_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L915) removes the event from the register before the port's registers are restored. Read it with its kerneldoc.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:905 */
/**
 * pciehp_slot_reset() - ignore link event caused by error-induced hot reset
 * @dev: PCI Express port service device
 *
 * Called from pcie_portdrv_slot_reset() after AER or DPC initiated a reset
 * further up in the hierarchy to recover from an error.  The reset was
 * propagated down to this hotplug port.  Ignore the resulting link flap.
 * If the link failed to retrain successfully, synthesize the ignored event.
 * Surprise removal during reset is detected through Presence Detect Changed.
 */
int pciehp_slot_reset(struct pcie_device *dev)
{
	struct controller *ctrl = get_service_data(dev);

	if (ctrl->state != ON_STATE)
		return 0;

	pcie_capability_write_word(dev->port, PCI_EXP_SLTSTA,
				   PCI_EXP_SLTSTA_DLLSC);

	if (!pciehp_check_link_active(ctrl))
		pciehp_request(ctrl, PCI_EXP_SLTSTA_DLLSC);

	return 0;
}
```

A slot that is not in [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) returns at once. For a slot that is on, writing [`PCI_EXP_SLTSTA_DLLSC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L642) to Slot Status clears the latched Link Down/Up. A link that has not come back, [`pciehp_check_link_active()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L235) returning 0, gets a [`PCI_EXP_SLTSTA_DLLSC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L642) put back through [`pciehp_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L141). [`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637) stays latched, so a surprise removal during recovery still reaches the state machine, as the kerneldoc says.

The message of commit [ea401499e943](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=ea401499e943c307e6d44af6c2b4e068643e7884) says the event is cleared before config space is restored. It quotes the specification's rule that a port sends an interrupt when an event bit and its enable bit are both set.

So far, the three causes all end before the slot state machine. A reset through the slot method is bracketed, a containment at the port is recorded, and a Hot Reset from above is cleared from the register. A check after each brings back a link that stayed down.

### Messages, hand-offs and files expose the suppression

The suppression leaves few traces of its own, and a reader who sets out to see it work reads the log, the debug sites and the tracepoints of the paths around it. The table lists each class with its sites on the paths of this page.

| class | on these paths | sites |
|---|---|---|
| tracepoints | none in the bracket, the DPC record or the clear; `pci:pci_hp_event` fires from the slot state machine for events that pass the gate, a requested one included, while a dropped one fires none; `pci:pcie_link_event` fires from the bandwidth controller's interrupt handler when the port's link bandwidth status changes during a flap | [`pciehp_ctrl.c:251`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L251), [`pciehp_ctrl.c:258`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L258), [`bwctrl.c:237`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/bwctrl.c#L237) |
| info and warning messages | "Slot(%s): Link Down/Up ignored"; "unlocked secondary bus reset via: %pS", once per bridge; "Data Link Layer Link Active not set in %d msec"; "Data Link Layer Link Active not cleared in 1000 msec"; "%s Port link has been reset (%d)"; "subordinate device reset failed" | [`pciehp_hpc.c:610`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L610), [`pci.c:4857`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4857), [`pci.c:4816`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4816), [`dpc.c:166`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L166), [`aer.c:1704`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1704), [`err.c:253`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L253) |
| dynamic-debug sites | "pending interrupts %#06x from Slot Status"; "%s: lnk_status = %x"; "waiting %d ms for downstream link"; "broadcast slot_reset message" | [`pciehp_hpc.c:699`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L699), [`pciehp_hpc.c:246`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L246), [`pci.c:4790`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4790), [`pci.c:4812`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4812), [`err.c:265`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L265) |
| hand-offs | the threaded interrupts of pciehp and DPC; the wait queues [`pci_hp_link_change_wq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L491) and [`dpc_completed_waitqueue`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L78); `irq_wake_thread()` in [`pciehp_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L141); `synchronize_hardirq()` in [`pciehp_ignore_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L596); the poll thread [`pciehp_poll()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L800) when [`pciehp_poll_mode`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L34) is set | [`pciehp_hpc.c:725`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L725), [`dpc.c:380`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L380), [`pci_hotplug_core.c:554`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L554), [`dpc.c:123`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L123), [`pciehp_ctrl.c:145`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L145) |
| debugging surfaces | the sysfs attribute `reset_subordinate` of a bridge; the module parameter `pciehp_poll_mode`, given at boot as `pciehp.pciehp_poll_mode=1`; no debugfs file and no fault-injection point of the mechanism's own | [`pci-sysfs.c:574`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-sysfs.c#L574), [`pciehp_core.c:41`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L41) |

The pciehp messages go through [`ctrl_info()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L39) and [`ctrl_dbg()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L35), which wrap the PCI core's printers for the port's device. Read the four macros with the comment above them.

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

With [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) set, [`ctrl_dbg()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L35) is [`pci_dbg()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2896), a dynamic-debug callsite that a reader enables in /sys/kernel/debug/dynamic_debug/control or at boot with the dyndbg form the comment gives. The "pending interrupts" line then shows which Slot Status events a reset raised, and the lnk_status line shows the Link Status value that the check after a drop read. With [`CONFIG_PCI_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L70), unset here, the line at [`drivers/pci/Makefile:50`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Makefile#L50) adds `-DDEBUG` and the same sites print without being enabled.

```c
/* drivers/pci/Makefile:50 */
subdir-ccflags-$(CONFIG_PCI_DEBUG) := -DDEBUG
```

The line applies `-DDEBUG` to drivers/pci and the directories below it, pciehp and dpc.c included, when [`CONFIG_PCI_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L70) is set. A reader who sees "Link Down/Up ignored" with no "Link Down" after it knows that the drop stood. A "Link Down" or "Card not present" from the state machine after it means the check brought the events back.
