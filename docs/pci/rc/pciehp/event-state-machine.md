# pciehp event state machine

> CAUTION: AI-GENERATED CONTENT
>
> STRICTLY DO NOT SUBMIT THIS UPSTREAM UNLESS YOU ARE AN EXPERT INTIMATELY FAMILIAR WITH THIS SUBSYSTEM.

A PCIe hotplug slot reports button presses, cards coming and going and its link going up or down as Slot Status ([`PCI_EXP_SLTSTA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L633)) events such as [`PCI_EXP_SLTSTA_ABP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L634), [`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637) and [`PCI_EXP_SLTSTA_DLLSC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L642). A user can also ask through sysfs for the slot to be turned on or off, and these reports and requests arrive in any order from several contexts. The native PCIe hotplug driver, pciehp, keeps one [`struct controller`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L91) per hotplug port and funnels them into one word, [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104), that one IRQ thread per port consumes. The slot's [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109), kept under [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110), records whether the slot is off, on, inside the five-second window a button press opens, or changing power. This page follows each request into that word and through the handlers that move the state, and ends with the messages and the tracepoint that record each move.

```text
    Every request meets the others in one word, and one thread turns them into state
    ────────────────────────────────────────────────────────────────────────────────

    sources of a request                                     struct controller of one hotplug port
    ┌─────────────────────────────────┐
    │ hard IRQ of the port: the Slot  ├─ event bits ──┐
    │ Status events it latched        │               │
    └─────────────────────────────────┘               │
    ┌─────────────────────────────────┐               │      ┌──────────────────────────────────┐
    │ button_work, 5 s after a press  ├─ PDC or ──────┤      │ pending_events, an atomic_t:     │
    └─────────────────────────────────┘  DISABLE_SLOT ├─────▶│ every source ORs its bits        │
    ┌─────────────────────────────────┐               │      │ into the same word               │
    │ write to the slot's power file  ├─ PDC or ──────┤      └────────────────┬─────────────────┘
    └─────────────────────────────────┘  DISABLE_SLOT │                       │ taken whole and reset to 0
    ┌─────────────────────────────────┐               │                       │
    │ probe, resume, error recovery   ├─ PDC or ──────┘                       │
    └─────────────────────────────────┘  DLLSC                                ▼
                                                             ┌──────────────────────────────────┐
                                                             │ IRQ thread of the port: one      │
                                                             │ snapshot per run, one            │
                                                             │ handler at a time                │
                                                             └────────────────┬─────────────────┘
                                                                              │ handlers write it
                                                                              │ under state_lock
                                                                              │
                                                                              ▼
                                                             ┌──────────────────────────────────┐
                                                             │ state, one of six values:        │
                                                             │ OFF_STATE  BLINKINGON_STATE      │
                                                             │ BLINKINGOFF_STATE  POWERON_STATE │
                                                             │ POWEROFF_STATE  ON_STATE         │
                                                             └──────────────────────────────────┘
```

## SUMMARY

The model is one word and one thread per hotplug port, and the table settles which kernel object stands for each term of the specification before the page uses it.

| Specification term | Kernel object | Role on this page |
|---|---|---|
| Hot-Plug Slot of a Downstream Port | [`struct controller`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L91), one per hotplug port, which also stands for the slot | holds [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109), [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110) and [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104) |
| Downstream Port that carries the slot | the [`port`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L61) of [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59), the portdrv service instance of the hotplug service | the [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) whose Slot registers the handlers read |
| Hot-plug event latched in Slot Status | a bit of [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104) at the position of its mask, such as [`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637) | what the IRQ thread [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728) dispatches on |
| Software request to the slot | [`DISABLE_SLOT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L153), a bit above the Slot Status bits, or a synthesized [`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637) | how the button work, sysfs and resume reach [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728) through [`pciehp_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L141) |
| Attention Button and its 5-second abort interval | [`PCI_EXP_SLTSTA_ABP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L634), [`button_work`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L111) and the states [`BLINKINGON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L134) and [`BLINKINGOFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L135) | the window a press opens before the slot changes power |
| User request to enable or disable the slot | the [`enable_slot`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L39) and [`disable_slot`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L40) callbacks, set to [`pciehp_sysfs_enable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L393) and [`pciehp_sysfs_disable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L432) | a write that sleeps on [`requester`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L118) for [`request_result`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L117) |

Every source sets bits in [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104) and wakes the thread, and after probe the handlers that thread runs are the writers of [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109), each under [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110). A slot is therefore enabled or disabled by one thread at a time, and a presence or link change turns a powered slot off before it turns an occupied slot back on.

## SPECIFICATIONS

- PCI Express Base Specification r4.0, section 6.7.1.5, cited by commit d331710ea78f ("PCI: pciehp: Become resilient to missed events"), whose message quotes it as "Once the Power Indicator begins blinking, a 5-second abort interval exists during which a second depression of the Attention Button cancels the operation."
- PCI Express Base Specification r4.0, section 6.7.1.8, cited by commit 9590192f2584 ("PCI: pciehp: Track enable/disable status") for the Power Controller Control bit, which is unreliable when a power fault occurs.
- PCI Express Base Specification r4.0, section 6.7.3.4, cited by the comment above [`pciehp_check_presence()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L167) at [`pciehp_core.c:163-165`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L163) for events that occur while interrupt generation is disabled.

No specification defines the six slot states. They are pciehp's own, named by the `DOC: Slot state` comment of [`pciehp.h`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h), and the page describes the machine as a synthesis of that comment and the handlers of [`pciehp_ctrl.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c) at v7.2.

## COVERAGE

### The slot state and its lock (drivers/pci/hotplug/pciehp.h)

- [`'controller.state'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109): the slot's position in the state machine
- [`'controller.state_lock'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110): the mutex over the state and over scheduling, running and cancelling the button work
- [`'OFF_STATE'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133): slot powered off, nothing enumerated below it
- [`'BLINKINGON_STATE'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L134): the five-second window before a power-on
- [`'BLINKINGOFF_STATE'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L135): the five-second window before a power-off
- [`'POWERON_STATE'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L136): the IRQ thread is enabling the slot
- [`'POWEROFF_STATE'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L137): the IRQ thread is disabling the slot
- [`'ON_STATE'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138): slot powered on, devices enumerated

### Requests into the IRQ thread (drivers/pci/hotplug/pciehp_ctrl.c, pciehp.h)

- [`'\<pciehp_request\>':'drivers/pci/hotplug/pciehp_ctrl.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L141): ORs a request bit into the event word and wakes the IRQ thread
- [`'DISABLE_SLOT'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L153): request bit 16, a disable that no Slot Status event expresses
- [`'controller.pending_events'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104): Slot Status events and requests waiting for the IRQ thread

### The Attention Button window (drivers/pci/hotplug/pciehp_ctrl.c)

- [`'\<pciehp_handle_button_press\>':'drivers/pci/hotplug/pciehp_ctrl.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L167): opens or cancels a five-second window
- [`'\<pciehp_queue_pushbutton_work\>':'drivers/pci/hotplug/pciehp_ctrl.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L148): turns an expired window into a request
- [`'controller.button_work'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L111): the delayed work that ends a window

### Event handlers (drivers/pci/hotplug/pciehp_ctrl.c)

- [`'\<pciehp_handle_disable_request\>':'drivers/pci/hotplug/pciehp_ctrl.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L217): forces the slot off through a safe removal
- [`'\<pciehp_handle_presence_or_link_change\>':'drivers/pci/hotplug/pciehp_ctrl.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L232): turns a powered slot off, then an occupied slot on
- [`'trace_pci_hp_event'`](https://elixir.bootlin.com/linux/v7.2/source/include/trace/events/pci.h#L43): the tracepoint the presence and link handler fires

### Enable and disable (drivers/pci/hotplug/pciehp_ctrl.c)

- [`'\<__pciehp_enable_slot\>':'drivers/pci/hotplug/pciehp_ctrl.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L317): checks the latch and the power, then hands over to the hot-add path
- [`'pciehp_enable_slot'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L342): holds a runtime PM reference on the port and stores [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) or [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) from the result
- [`'\<__pciehp_disable_slot\>':'drivers/pci/hotplug/pciehp_ctrl.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L361): checks the power, then hands over to the hot-remove path
- [`'pciehp_disable_slot'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L378): holds a runtime PM reference on the port and stores [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133)
- [`'SAFE_REMOVAL'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L31): the removal kind of a requested disable
- [`'SURPRISE_REMOVAL'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L32): the removal kind after a presence or link change

### Synchronous sysfs requests (drivers/pci/hotplug/pciehp_ctrl.c, pciehp.h)

- [`'\<pciehp_sysfs_enable_slot\>':'drivers/pci/hotplug/pciehp_ctrl.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L393): requests an enable from the IRQ thread and waits for its result
- [`'\<pciehp_sysfs_disable_slot\>':'drivers/pci/hotplug/pciehp_ctrl.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L432): requests a disable from the IRQ thread and waits for its result
- [`'controller.ist_running'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L116): set while the IRQ thread runs, half of the sysfs wait condition
- [`'controller.request_result'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L117): the result a sysfs request returns
- [`'controller.requester'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L118): the wait queue a sysfs writer sleeps on

## DOCUMENTATION

- [`Documentation/trace/events-pci.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/trace/events-pci.rst): the `pci:pci_hp_event` tracepoint, its four event types and a sample trace of a hot-add
- [`Documentation/PCI/pciebus-howto.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/PCI/pciebus-howto.rst): the PCIe port bus driver and its services, among them the native hotplug service that pciehp provides
- [`Documentation/ABI/testing/sysfs-bus-pci`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/ABI/testing/sysfs-bus-pci): the `/sys/bus/pci/slots/.../module` entry, the one ABI entry of the slot directory; the `power` file the sysfs requests arrive through has none

## OTHER SOURCES

### Added by Claude Opus 5.5

- [PCI: trace: Add generic RAS tracepoint for hotplug event (commit 9e541b3cee70)](https://patch.msgid.link/20251210132907.58799-2-xueshuai@linux.alibaba.com)
- [PCI: pciehp: Simplify Attention Button logging (commit 5054133a8862)](https://lore.kernel.org/r/20230522214051.619337-1-helgaas@kernel.org)
- [PCI: pciehp: Cancel bringup sequence if card is not present (commit e8afd0d9fccc)](https://lore.kernel.org/r/20230512021518.336460-1-clementwei90@163.com)
- [PCI: pciehp: Avoid returning prematurely from sysfs requests (commit 157c1062fcd8)](https://lore.kernel.org/linux-pci/1562226638-54134-1-git-send-email-wangxiongfeng2@huawei.com)
- [PCI: pciehp: Avoid returning prematurely from sysfs requests (commit 157c1062fcd8)](https://lore.kernel.org/r/4174210466e27eb7e2243dd1d801d5f75baaffd8.1565345211.git.lukas@wunner.de)
- [PCI: pciehp: Ignore Link State Changes after powering off a slot (commit 3943af9d01e9)](https://bugzilla.kernel.org/show_bug.cgi?id=203237)

## REGISTERS

The handlers on this page decide on four registers of the hotplug port's PCI Express Capability. They reach them through the Slot register accessors of [`pciehp_hpc.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c), or through the copy of Slot Capabilities ([`PCI_EXP_SLTCAP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L597)) that [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) keeps in [`slot_cap`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L95). A drawing marks the fields these paths read or write, and the paragraph above it says what those fields decide here.

Slot Capabilities ([`PCI_EXP_SLTCAP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L597)) is read once at probe, and the handlers test its presence bits through the macros of [`pciehp.h`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h) on the cached copy. [`POWER_CTRL()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L157) tests Power Controller Present ([`PCI_EXP_SLTCAP_PCP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L599)) before the power checks of the enable and disable helpers, and [`MRL_SENS()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L158) tests MRL Sensor Present ([`PCI_EXP_SLTCAP_MRLSP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L600)) before the latch check. [`ATTN_BUTTN()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L156) tests Attention Button Present ([`PCI_EXP_SLTCAP_ABP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L598)) before a failed enable turns the Power Indicator ([`PCI_EXP_SLTCTL_PIC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L622)) off. [`PWR_LED()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L160) and [`ATTN_LED()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L159) decide whether an indicator write reaches the port at all, and [`PSN()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L162) gives the slot the name that the Slot(%s) messages and the tracepoint carry.

```text
    Slot Capabilities, offset 0x14 of the PCIe capability, cached in controller.slot_cap
    ────────────────────────────────────────────────────────────────────────────────────

    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x14  │           PSN           │  not read on these paths  │P│A│M│C│B│
          │         (31:19)         │           (18:5)          │ │ │ │ │ │
          └─────────────────────────┴───────────────────────────┴┬┴┬┴┬┴┬┴┬┘
                                                                 │ │ │ │ │
    PIP ─────────────────────────────────────────────────────────┘ │ │ │ │
    AIP ───────────────────────────────────────────────────────────┘ │ │ │
    MRLSP ───────────────────────────────────────────────────────────┘ │ │
    PCP ───────────────────────────────────────────────────────────────┘ │
    ABP ─────────────────────────────────────────────────────────────────┘

    PSN   = PCI_EXP_SLTCAP_PSN (Physical Slot Number, read by PSN(), the slot name in every message)
    PIP   = PCI_EXP_SLTCAP_PIP (Power Indicator Present, tested by PWR_LED())
    AIP   = PCI_EXP_SLTCAP_AIP (Attention Indicator Present, tested by ATTN_LED())
    MRLSP = PCI_EXP_SLTCAP_MRLSP (MRL Sensor Present, tested by MRL_SENS())
    PCP   = PCI_EXP_SLTCAP_PCP (Power Controller Present, tested by POWER_CTRL())
    ABP   = PCI_EXP_SLTCAP_ABP (Attention Button Present, tested by ATTN_BUTTN())
```

Slot Control ([`PCI_EXP_SLTCTL`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L610)) carries the enables that decide which events interrupt, the indicator fields the button handler writes and the power bit the enable and disable helpers read. Probe sets [`PCI_EXP_SLTCTL_DLLSCE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L630) unconditionally and [`PCI_EXP_SLTCTL_ABPE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L611) or [`PCI_EXP_SLTCTL_PDCE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L614) by whether the slot has an Attention Button ([`PCI_EXP_SLTCAP_ABP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L598)). The indicator values such as [`PCI_EXP_SLTCTL_PWR_IND_BLINK`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L624) reach Power Indicator Control ([`PCI_EXP_SLTCTL_PIC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L622)) and Attention Indicator Control ([`PCI_EXP_SLTCTL_AIC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L617)) through [`pciehp_set_indicators()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L513), and [`pciehp_get_power_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L395) reads Power Controller Control ([`PCI_EXP_SLTCTL_PCC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L626)).

```text
    Slot Control, offset 0x18 of the PCIe capability
    ────────────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x18  │·│·│·│L│·│C│PIC│AIC│·│·│P│·│·│B│
          │ │ │ │ │ │ │9:8│7:6│ │ │ │ │ │ │
          └─┴─┴─┴┬┴─┴┬┴───┴───┴─┴─┴┬┴─┴─┴┬┘
                 │   │             │     │
    DLLSCE ──────┘   │             │     │
    PCC ─────────────┘             │     │
    PDCE ──────────────────────────┘     │
    ABPE ────────────────────────────────┘

    DLLSCE = PCI_EXP_SLTCTL_DLLSCE (Data Link Layer State Changed Enable, always set)
    PCC    = PCI_EXP_SLTCTL_PCC (Power Controller Control: PCI_EXP_SLTCTL_PWR_ON 0, PCI_EXP_SLTCTL_PWR_OFF 1)
    PIC    = PCI_EXP_SLTCTL_PIC (Power Indicator Control: _PWR_IND_ON 01, _PWR_IND_BLINK 10, _PWR_IND_OFF 11)
    AIC    = PCI_EXP_SLTCTL_AIC (Attention Indicator Control: _ATTN_IND_ON 01, _ATTN_IND_BLINK 10, _ATTN_IND_OFF 11)
    PDCE   = PCI_EXP_SLTCTL_PDCE (Presence Detect Changed Enable, set when the slot has no Attention Button)
    ABPE   = PCI_EXP_SLTCTL_ABPE (Attention Button Pressed Enable, set when the slot has one)
    ·      = other enables and controls (bits 15:13, 11, 5:4, 2:1), outside these paths
```

Slot Status ([`PCI_EXP_SLTSTA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L633)) supplies the events and the presence and latch states. Its four event bits reach [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104) at the same bit positions. Presence Detect State ([`PCI_EXP_SLTSTA_PDS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L640)) answers [`pciehp_card_present()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L438), and MRL Sensor State ([`PCI_EXP_SLTSTA_MRLSS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L639)) answers [`pciehp_get_latch_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L417).

```text
    Slot Status, offset 0x1a of the PCIe capability
    ───────────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x1a  │   reserved  │L│·│S│M│·│D│·│F│A│
          │    (15:9)   │ │ │ │ │ │ │ │ │ │
          └─────────────┴┬┴─┴┬┴┬┴─┴┬┴─┴┬┴┬┘
                         │   │ │   │   │ │
    DLLSC ───────────────┘   │ │   │   │ │
    PDS ─────────────────────┘ │   │   │ │
    MRLSS ─────────────────────┘   │   │ │
    PDC ───────────────────────────┘   │ │
    PFD ───────────────────────────────┘ │
    ABP ─────────────────────────────────┘

    DLLSC = PCI_EXP_SLTSTA_DLLSC (Data Link Layer State Changed, an event bit)
    PDS   = PCI_EXP_SLTSTA_PDS (Presence Detect State, 1 when a card is present)
    MRLSS = PCI_EXP_SLTSTA_MRLSS (MRL Sensor State, 1 when the latch is open)
    PDC   = PCI_EXP_SLTSTA_PDC (Presence Detect Changed, an event bit)
    PFD   = PCI_EXP_SLTSTA_PFD (Power Fault Detected, an event bit)
    ABP   = PCI_EXP_SLTSTA_ABP (Attention Button Pressed, an event bit)
    ·     = PCI_EXP_SLTSTA_EIS (7), PCI_EXP_SLTSTA_CC (4) and PCI_EXP_SLTSTA_MRLSC (2), outside these paths
```

Link Status ([`PCI_EXP_LNKSTA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L577)) contributes Data Link Layer Link Active ([`PCI_EXP_LNKSTA_DLLLA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L593)), which [`pciehp_check_link_active()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L235) reports to the presence handler. A slot whose link is up counts as occupied there even when its Presence Detect State ([`PCI_EXP_SLTSTA_PDS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L640)) bit is clear.

```text
    Link Status, offset 0x12 of the PCIe capability
    ───────────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x12  │·│·│D│ not read on these paths │
          │ │ │ │          (12:0)         │
          └─┴─┴┬┴─────────────────────────┘
               │
    DLLLA ─────┘

    DLLLA = PCI_EXP_LNKSTA_DLLLA (Data Link Layer Link Active, 1 when the link is up)
    ·     = PCI_EXP_LNKSTA_LABS (15) and PCI_EXP_LNKSTA_LBMS (14), outside these paths
```

## DETAILS

DETAILS first builds the model from the controller that holds a slot's state and request channels, the six values of that state and the probe that sets the first one. It then follows a request into the event word and the IRQ thread that takes a snapshot of it. The handlers come next in the order the thread dispatches them, the button window and its work, the forced disable, and the presence and link handler. The enable and disable helpers that settle the transient states follow, then the power file and the sysfs request that waits for the thread. The last subsections cover the presence re-checks of probe and resume, the readers that skip the lock, removal, and the traces, messages, hand-offs and files of these steps.

### Kconfig assumptions

The page documents the x86-64 defconfig resolved at the v7.2 tag, on x86-64 with ACPI firmware, with the PCIe port, hotplug and dynamic-debug options of the table set on top of it. The defconfig sets the port bus and the hotplug core and leaves [`CONFIG_HOTPLUG_PCI_PCIE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L16) unset, and the page assumes it set, since pciehp is built only with it.

| option | assumed value | what it decides here |
|---|---|---|
| [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5) | y, set by the defconfig | builds the port services, whose hotplug service instance is the [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59) a controller points at |
| [`CONFIG_HOTPLUG_PCI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/Kconfig#L6) | y, set by the defconfig | builds the hotplug core, whose [`power_write_file()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L67) calls the sysfs requests |
| [`CONFIG_HOTPLUG_PCI_PCIE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L16) | y, unset in the defconfig | builds pciehp through [`drivers/pci/hotplug/Makefile:14`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/Makefile#L14) |
| [`CONFIG_PM`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L217) | y | builds [`pciehp_resume()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L318) and [`pciehp_runtime_resume()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L336), which re-check presence |
| [`CONFIG_PM_SLEEP`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L140) | y | builds [`pciehp_resume_noirq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L288), which detects a device replaced during sleep |
| [`CONFIG_TRACING`](https://elixir.bootlin.com/linux/v7.2/source/kernel/trace/Kconfig#L179) | y | builds the file that instantiates the `pci:pci_hp_event` tracepoint |
| [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) | y | makes the [`ctrl_dbg()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L35) sites of these paths switchable at run time |
| [`CONFIG_PCI_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L70) | n | would compile drivers/pci with -DDEBUG and print those sites unconditionally |

The table indexes the prose. Each subsection below names the option at the point where its effect applies.

### A controller holds a slot's state and its request channels

pciehp needs one place per hotplug port to remember where the slot stands and what has been asked of it. That place is [`struct controller`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L91), one per port that the hotplug service binds to, in the pciehp that [`CONFIG_HOTPLUG_PCI_PCIE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L16) builds. The end of its kerneldoc, at [`pciehp.h:83-88`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L83), names the three members a sysfs request uses and states how the object relates to the slot:

```c
/* drivers/pci/hotplug/pciehp.h:83 */
 * @ist_running: flag to keep user request waiting while IRQ thread is running
 * @request_result: result of last user request submitted to the IRQ thread
 * @requester: wait queue to wake up on completion of user request,
 *	used for synchronous slot enable/disable request via sysfs
 *
 * PCIe hotplug has a 1:1 relationship between controller and slot, hence
```

PCIe hotplug has a 1:1 relationship between controller and slot, so the one object stands for both, and the figure shows the objects it joins.

```text
    A controller embeds the slot the hotplug core registers and points at its port
    ──────────────────────────────────────────────────────────────────────────────

    ┌────────────────────────────────┐       ┌─────────────────────────────────┐         ┌──────────────────────────┐
    │ struct controller              │ pcie  │ struct pcie_device              │         │ struct pci_dev           │
    │ pcie                           ├──────▶│ portdrv's hotplug service       │ port    │ the hotplug port: a Root │
    │ state, state_lock              │       │ port                            ├────────▶│ Port or Downstream Port  │
    │ pending_events, button_work    │       │ irq: the IRQ thread runs on it  │         └─────────────┬────────────┘
    │ ist_running, request_result,   │◀──────┤ priv_data                       │                       │
    │ requester                      │       └─────────────────────────────────┘                       │ subordinate
    │ hotplug_slot: an embedded      │                                                                 │
    │ struct hotplug_slot, whose     │       ┌─────────────────────────────────────────┐               │
    │ ops points at the slot ops     ├──────▶│ struct hotplug_slot_ops, pciehp's       │               │
    └────────────────────────────────┘       │ enable_slot:  pciehp_sysfs_enable_slot  │               │
                                             │ disable_slot: pciehp_sysfs_disable_slot │               │
                                             └─────────────────────────────────────────┘               ▼
                                                                                         ┌──────────────────────────┐
    to_ctrl() turns a struct hotplug_slot pointer back into                              │ struct pci_bus           │
    the controller around it with container_of().                                        │ the slot's secondary bus │
                                                                                         └──────────────────────────┘
```

The figure places the controller between the port service it serves and the slot the hotplug core registers for it. The table names what each group of its members answers and which code writes or reads it. This page follows the event word, the state with its lock and work item, and the three members a sysfs request waits on.

| members | what they answer | written or read by |
|---|---|---|
| [`pcie`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L92) | which port service, and through it which port and IRQ, the controller serves | set by [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006), read by the four message macros of `pciehp.h` and by [`pciehp_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L141) |
| [`dsn`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L93), [`slot_cap`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L95), [`inband_presence_disabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L96) | the cached serial number, Slot Capabilities and an In-Band Presence Detect setting | [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006); [`slot_cap`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L95) is read by [`POWER_CTRL()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L157) and its sibling macros |
| [`slot_ctrl`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L98), [`ctrl_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L99), [`cmd_started`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L100), [`cmd_busy`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L101), [`queue`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L102) | the Slot Control write protocol | the command code of [`pciehp_hpc.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c), outside this page |
| [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104) | which events and requests wait for the IRQ thread | ORed in by [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623) and [`pciehp_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L141), taken by [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728) |
| [`notification_enabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L105), [`power_fault_detected`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L106), [`poll_thread`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L107) | whether the IRQ is set up, a power fault already reported, the poll thread | the interrupt setup and [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623), outside this page |
| [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109), [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110), [`button_work`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L111) | where the slot stands, the lock over it and the five-second work | the handlers of this page |
| [`hotplug_slot`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L113) | the slot the hotplug core registers, with its ops | [`init_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L51), and [`to_ctrl()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L207) on the way back |
| [`reset_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114), [`depth`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L115) | that no slot reset runs while the thread handles presence or link, and the lock's nesting level | [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728) and the slot reset code |
| [`ist_running`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L116), [`request_result`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L117), [`requester`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L118) | what a sysfs writer waits for and the result it returns | [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728), the handlers and the sysfs functions |

The definition of [`struct controller`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L91) in `pciehp.h` groups its members by those concerns, with a comment naming each group, and the excerpt is the object the rest of the page follows:

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

The comments mark the groups the table describes, the event handling around [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104), the state machine around [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109) and the hotplug core interface around [`hotplug_slot`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L113). [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109) is a u8 holding one of the six values of the next subsection, and [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110) is a mutex, so a holder may sleep. [`button_work`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L111) is a delayed work item embedded in the controller, and [`requester`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L118) is a wait queue head beside the two members a waiter tests. The first member, [`pcie`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L92), leads to the port, through the portdrv structure [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59) defined in `portdrv.h`:

```c
/* drivers/pci/pcie/portdrv.h:59 */
struct pcie_device {
	int		irq;	    /* Service IRQ/MSI/MSI-X Vector */
	struct pci_dev *port;	    /* Root/Upstream/Downstream Port */
	u32		service;    /* Port service this device represents */
	void		*priv_data; /* Service Private Data */
	struct device	device;     /* Generic Device Interface */
};
```

A [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59) is portdrv's service instance, one per service that [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5) builds for a port, and here it is the instance of the hotplug service. [`port`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L61) is the hotplug port itself, a [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) whose Slot registers the handlers read. [`irq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L60) is the vector the IRQ thread is attached to, which [`pciehp_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L141) wakes. [`service`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L62) names the service, [`priv_data`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L63) holds the controller as the service's data, and [`device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L64) is the generic device of the instance. Two inline helpers of `pciehp.h` cross between the controller and the hotplug core's slot, and the excerpt shows both:

```c
/* drivers/pci/hotplug/pciehp.h:202 */
static inline const char *slot_name(struct controller *ctrl)
{
	return hotplug_slot_name(&ctrl->hotplug_slot);
}

static inline struct controller *to_ctrl(struct hotplug_slot *hotplug_slot)
{
	return container_of(hotplug_slot, struct controller, hotplug_slot);
}
```

[`slot_name()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L202) returns the name the hotplug core holds for the embedded slot, and every `Slot(%s)` message of `pciehp_ctrl.c` prints it. [`to_ctrl()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L207) turns the [`struct hotplug_slot`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L57) pointer that the hotplug core passes to a callback back into the controller around it with `container_of()`, which is how the sysfs functions find the controller. The object a request changes is therefore one controller, reached from the port service through [`priv_data`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L63) and from the hotplug core through the embedded slot.

### The state takes six values that place a slot in a transition

A slot's power cannot be read from the hardware alone. Commit commit [9590192f2584](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=9590192f2584c2cfc2fee88be22fe6e8921ed115) ("PCI: pciehp: Track enable/disable status") replaced a reading of the Power Controller Control ([`PCI_EXP_SLTCTL_PCC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L626)) bit with a tracked state. Its message gives two reasons, that the bit is unreliable when a power fault occurs and that an Attention Button ([`PCI_EXP_SLTCAP_ABP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L598)) does not imply a power controller. [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109) therefore records where the slot stands in software, as one of the six values in the table.

| value | meaning, from the `DOC: Slot state` comment | entered when |
|---|---|---|
| [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) | slot powered off, no subordinate devices enumerated | probe finds the secondary bus empty, a disable ends, or an enable fails |
| [`BLINKINGON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L134) | slot powered on after the 5-second delay, Power Indicator blinking | a button press arrives in [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) |
| [`BLINKINGOFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L135) | slot powered off after the 5-second delay, Power Indicator blinking | a button press arrives in [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) |
| [`POWERON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L136) | slot currently powering on | the presence and link handler starts an enable |
| [`POWEROFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L137) | slot currently powering off | a disable request or the presence and link handler starts a disable |
| [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) | slot powered on, subordinate devices enumerated | probe finds devices, an enable succeeds, or a press cancels a power-off |

The values are plain macros beside their DOC comment in `pciehp.h`, so the field compares and stores small integers and nothing in the type restricts it to the six:

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

[`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) is 0, so a freshly allocated controller, whose field is zeroed, already reads as a slot that is off. The two blinking states are the windows of an Attention Button ([`PCI_EXP_SLTCAP_ABP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L598)) press, the two powering states are held while the IRQ thread changes the slot's power, and [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) and [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) are the settled ends. The figure draws the six values with every write that moves the slot between them:

```text
    controller.state: the six values and every write that moves the slot between them
    ─────────────────────────────────────────────────────────────────────────────────

                       «4» press             ┌──────────────────────┐ «10» occupied
                     ┌──────────────────────▶│ BLINKINGON_STATE     ├────────────────┐
                     │       ┌───────────────┤ 5 s power-on window  │                │
                     │       │               └──────────────────────┘                │
                     │       │ «6» press                                             │
                     │       │ «9» empty                                             │
                     │       │                                                       │
                     │       ▼                                                       ▼
               ┌─────┴──────────────────┐    «10» occupied or link up    ┌────────────────────────┐
    «1» «2» ──▶│ OFF_STATE              ├───────────────────────────────▶│ POWERON_STATE          │
               │ off, bus empty         │◀───────────────────────────────┤ slot powering on       │
               └────────────────────────┘          «11» failed           └───────────┬────────────┘
                           ▲                                                         │
                           │                                                         │ «11» enabled
                           │ «12» disabled                                           │
                           │                                                         │
                           │                                                         ▼
               ┌───────────┴────────────┐   «7» DISABLE_SLOT, any state  ┌────────────────────────┐
               │ POWEROFF_STATE         │◀───────────────────────────────┤ ON_STATE               │◀── «2»
               │ slot powering off      │   «8» PDC or DLLSC             │ on, devices enumerated │
               └────────────────────────┘                                └───────────────┬────────┘
                     ▲                                                           ▲       │
                     │                                                           │       │
                     │                                                           │       │ «3» press
                     │ «7» «8»                                         «5» press │       │
                     │                       ┌──────────────────────┐            │       │
                     └───────────────────────┤ BLINKINGOFF_STATE    ├────────────┘       │
                                             │ 5 s power-off window │◀───────────────────┘
                                             └──────────────────────┘

    «13» the controller is freed in any state

    «1»  pcie_init                              pciehp_hpc.c:1014  the zeroed allocation reads as OFF_STATE
    «2»  pcie_init                              :1042              OFF_STATE or ON_STATE from the secondary bus
    «3»  pciehp_handle_button_press             pciehp_ctrl.c:174  a press on ON_STATE opens the power-off window
    «4»  pciehp_handle_button_press             :178               a press on OFF_STATE opens the power-on window
    «5»  pciehp_handle_button_press             :196               a second press cancels the power-off
    «6»  pciehp_handle_button_press             :202               a second press cancels the power-on
    «7»  pciehp_handle_disable_request          :226               DISABLE_SLOT forces POWEROFF_STATE
    «8»  pciehp_handle_presence_or_link_change  :246               a change on a powered slot starts removal
    «9»  pciehp_handle_presence_or_link_change  :275               an empty slot closes the power-on window
    «10» pciehp_handle_presence_or_link_change  :294               occupancy or link starts the bring-up
    «11» pciehp_enable_slot                     :355               the enable result picks ON_STATE or OFF_STATE
    «12» pciehp_disable_slot                    :387               a finished disable settles OFF_STATE
    «13» pciehp_release_ctrl                    pciehp_hpc.c:1099  kfree() ends the field with the controller
```

«1» [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) allocates the controller zeroed, so [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109) reads as [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) before any write. «2» `pcie_init()` then stores [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) or [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) from the devices on the secondary bus. «3» [`pciehp_handle_button_press()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L167) opens a power-off window when a press arrives in [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138). «4» `pciehp_handle_button_press()` opens a power-on window when a press arrives in [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133). «5» `pciehp_handle_button_press()` returns a power-off window to [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) on a second press. «6» `pciehp_handle_button_press()` returns a power-on window to [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) on a second press. «7» [`pciehp_handle_disable_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L217) stores [`POWEROFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L137) for a [`DISABLE_SLOT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L153) request from any state. «8» [`pciehp_handle_presence_or_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L232) stores [`POWEROFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L137) when a powered slot or a power-off window sees a presence or link change. «9» `pciehp_handle_presence_or_link_change()` returns a power-on window to [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) when the slot is empty. «10» `pciehp_handle_presence_or_link_change()` stores [`POWERON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L136) when an occupied slot is off or in a power-on window. «11» [`pciehp_enable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L342) settles [`POWERON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L136) into [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) or [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) by the enable's result. «12» [`pciehp_disable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L378) settles [`POWEROFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L137) into [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133). «13» [`pciehp_release_ctrl()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1096) frees the controller, and the field with it.

At v7.2 these thirteen marks are every write of this field, all in `pciehp_ctrl.c` and `pciehp_hpc.c`, and the page shows each of them. The same macro names in cpqphp.h and shpchp.h belong to other hotplug drivers with their own [`struct controller`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L91) types, outside this page.

### Probe derives the first state from the secondary bus

A slot can already hold enumerated devices when pciehp binds to its port, for example after the boot scan found a card in it. The first state therefore comes from the bus below the port, and probe later asks the IRQ thread to compare it with the slot's presence. [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) allocates the controller and initializes the members this page follows, as the stage of it below shows, from the allocation to the first state:

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
	... /* 15 lines, to :1032 */
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

`kzalloc_obj()` zeroes the controller, so [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104), [`ist_running`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L116) and [`request_result`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L117) start at 0 and [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109) at [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133), the state figure's «1». [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110), [`requester`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L118) and [`button_work`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L111) are initialized next, and `INIT_DELAYED_WORK` binds the work to [`pciehp_queue_pushbutton_work()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L148). Under [`pci_bus_sem`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/search.c#L17), the first state is [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) when the [`devices`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L706) list of the secondary bus holds a device and [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) when it is empty. That write takes no lock of the controller, and [`pciehp_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L185) publishes the controller and requests its interrupt only after `pcie_init()` returns, in the order the stage of the probe callback shows:

```c
/* drivers/pci/hotplug/pciehp_core.c:185 */
static int pciehp_probe(struct pcie_device *dev)
{
	int rc;
	struct controller *ctrl;
	... /* 12 lines, to :201 */
	ctrl = pcie_init(dev);
	if (!ctrl) {
		pci_err(dev->port, "Controller initialization failed\n");
		return -ENODEV;
	}
	set_service_data(dev, ctrl);

	/* Setup the slot information structures */
	rc = init_slot(ctrl);
	if (rc) {
		if (rc == -EBUSY)
			ctrl_warn(ctrl, "Slot already registered by another hotplug driver\n");
		else
			ctrl_err(ctrl, "Slot initialization failed (%d)\n", rc);
		goto err_out_release_ctlr;
	}

	/* Enable events after we have setup the data structures */
	rc = pcie_init_notification(ctrl);
	if (rc) {
		ctrl_err(ctrl, "Notification initialization failed (%d)\n", rc);
		goto err_out_free_ctrl_slot;
	}

	/* Publish to user space */
	rc = pci_hp_add(&ctrl->hotplug_slot);
	if (rc) {
		ctrl_err(ctrl, "Publication to user space failed (%d)\n", rc);
		goto err_out_shutdown_notification;
	}

	pciehp_check_presence(ctrl);

	return 0;
```

The controller becomes the service's data before [`init_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L51) registers the slot ops. [`pcie_init_notification()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L960) requests the IRQ and enables the Slot Control ([`PCI_EXP_SLTCTL`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L610)) notifications, and the slot is published to user space after that. [`pciehp_check_presence()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L167) runs last, so a request it makes finds the thread attached and the sysfs files present. A probed controller thus starts in [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) or [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) with an empty event word, and the next subsection follows the first request into that word.

### A request becomes a bit in pending_events

The IRQ thread has to learn what happened since its last run, from the hardware and from software, without a queue that could overflow or reorder. Commit commit [d331710ea78f](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=d331710ea78fea8b10624c87546d8bc0cd0389c9) ("PCI: pciehp: Become resilient to missed events") notes that Slot Status ([`PCI_EXP_SLTSTA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L633)) records that an event occurred without counting its occurrences. pciehp therefore keeps one atomic word per controller, [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104), ORs latched events into it and gives software requests bits of the same word. The DOC comment above [`DISABLE_SLOT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L153) in `pciehp.h` says where the software bits go:

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

[`DISABLE_SLOT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L153) is bit 16 and [`RERUN_ISR`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L154) bit 17, above the 16-bit width of Slot Status ([`PCI_EXP_SLTSTA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L633)), so neither collides with an event mask such as [`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637) (0x0008). The word therefore carries two kinds of bit on one ruler, the event bits at their Slot Status positions and the request bits above them, as the drawing shows.

```text
    controller.pending_events: Slot Status event bits and request bits in one word
    ──────────────────────────────────────────────────────────────────────────────

    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    word  │       unused (31:18)      │R│D│unused (15:9)│L│·│·│·│C│P│·│F│A│
          └───────────────────────────┴┬┴┬┴─────────────┴┬┴─┴─┴─┴─┴┬┴─┴┬┴┬┘
                                       │ │               │         │   │ │
    RERUN_ISR ─────────────────────────┘ │               │         │   │ │
    DISABLE_SLOT ────────────────────────┘               │         │   │ │
    DLLSC ───────────────────────────────────────────────┘         │   │ │
    PDC ───────────────────────────────────────────────────────────┘   │ │
    PFD ───────────────────────────────────────────────────────────────┘ │
    ABP ─────────────────────────────────────────────────────────────────┘

    ABP          = PCI_EXP_SLTSTA_ABP (bit 0, Attention Button Pressed, from the hard IRQ handler)
    PFD          = PCI_EXP_SLTSTA_PFD (bit 1, Power Fault Detected, from the hard IRQ handler)
    PDC          = PCI_EXP_SLTSTA_PDC (bit 3, Presence Detect Changed, from the hard IRQ handler or a request)
    DLLSC        = PCI_EXP_SLTSTA_DLLSC (bit 8, Data Link Layer State Changed, from the hard IRQ handler or a request)
    DISABLE_SLOT = DISABLE_SLOT (bit 16, a request to turn the slot off although it is occupied)
    RERUN_ISR    = RERUN_ISR (bit 17, the hard IRQ handler found the port inaccessible)
    C            = PCI_EXP_SLTSTA_CC (bit 4, Command Completed, consumed by the hard IRQ handler, never stored)
    ·            = Slot Status bits 2 and 7:5 (MRLSC, MRLSS, PDS, EIS), masked out by the hard IRQ handler
```

A software request that the hardware could also report reuses the event's bit as a synthesized Presence Detect Changed ([`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637)) or Data Link Layer State Changed ([`PCI_EXP_SLTSTA_DLLSC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L642)). [`DISABLE_SLOT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L153) exists because a disable must turn the slot off although it is occupied, the reason commit commit [32a8cef274fe](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=32a8cef274feacd00b748a4f13b84d60aa6d82ff) ("PCI: pciehp: Enable/disable exclusively from IRQ thread") gives for the bit. [`pciehp_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L141) is how software sets one of these bits, and the excerpt shows the store and the wake-up:

```c
/* drivers/pci/hotplug/pciehp_ctrl.c:141 */
void pciehp_request(struct controller *ctrl, int action)
{
	atomic_or(action, &ctrl->pending_events);
	if (!pciehp_poll_mode)
		irq_wake_thread(ctrl->pcie->irq, ctrl);
}
```

`atomic_or()` adds the bits without a lock, so concurrent requests and the hard IRQ handler merge in the word and a request already pending is not duplicated. `irq_wake_thread()` wakes the IRQ thread of the vector in [`irq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L60) unless [`pciehp_poll_mode`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L34) is set, and in that mode the poll thread finds the bits on its next pass. The hardware's bits come from the hard IRQ handler [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623), whose stages below show the deferral to the thread and the store into the same word:

```c
/* drivers/pci/hotplug/pciehp_hpc.c:623 */
static irqreturn_t pciehp_isr(int irq, void *dev_id)
{
	struct controller *ctrl = (struct controller *)dev_id;
	struct pci_dev *pdev = ctrl_dev(ctrl);
	struct device *parent = pdev->dev.parent;
	u16 status, events = 0;
	... /* 14 lines, to :643 */
	if (parent) {
		pm_runtime_get_noresume(parent);
		if (!pm_runtime_active(parent)) {
			pm_runtime_put(parent);
			disable_irq_nosync(irq);
			atomic_or(RERUN_ISR, &ctrl->pending_events);
			return IRQ_WAKE_THREAD;
		}
	}
	... /* 47 lines, to :699 */
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

When the port's parent is not runtime active, the comment says the parent's resume is deferred to the IRQ thread. The handler then masks the interrupt, stores [`RERUN_ISR`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L154) and leaves the reading of Slot Status ([`PCI_EXP_SLTSTA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L633)) to the thread. Command Completed ([`PCI_EXP_SLTSTA_CC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L638)) is consumed in the handler and removed from the events, and a port flagged [`ignore_hotplug`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L424) drops its events after a debug message. The remaining bits reach [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104) through `atomic_or()` before the handler returns `IRQ_WAKE_THREAD`. Software requests come from seven functions at v7.2, and the table names the context, the bit and the condition of each.

| caller | context | bit requested | when |
|---|---|---|---|
| [`pciehp_queue_pushbutton_work()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L148) | system workqueue | [`DISABLE_SLOT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L153) or [`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637) | an Attention Button window expired |
| [`pciehp_sysfs_enable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L393) | writer of the power file | [`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637) | a user enables a slot that is off |
| [`pciehp_sysfs_disable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L432) | writer of the power file | [`DISABLE_SLOT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L153) | a user disables a slot that is on |
| [`pciehp_check_presence()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L167) | probe and resume | [`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637) | presence disagrees with the state |
| [`pciehp_resume_noirq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L288) | system resume | [`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637) | the device in the slot was replaced during sleep |
| [`pciehp_ignore_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L596) | IRQ thread | the ignored [`PCI_EXP_SLTSTA_DLLSC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L642) and [`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637) | the link is down or the device replaced after an ignored link change |
| [`pciehp_slot_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L915) | AER or DPC recovery | [`PCI_EXP_SLTSTA_DLLSC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L642) | the link stayed down after an error-induced reset |

Every source thus ends in the same word, and the word records which kinds of event and request are pending until the thread takes it.

### The IRQ thread takes one snapshot and dispatches it

The thread is where requests are carried out, and probe attaches it to the port's service interrupt through [`pciehp_request_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L58). The function installs [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623) as the hard handler and [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728) as its thread, or starts a poll thread when [`pciehp_poll_mode`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L34) is set, and [`pciehp_free_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L78) after it undoes either:

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

static inline void pciehp_free_irq(struct controller *ctrl)
{
	if (pciehp_poll_mode)
		kthread_stop(ctrl->poll_thread);
	else
		free_irq(ctrl->pcie->irq, ctrl);
}
```

The vector is [`irq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L60) of the port service, requested with `IRQF_SHARED` so that other handlers may share it, and the controller is the `dev_id` argument both functions receive. The poll alternative serves ports without a usable interrupt, and two module parameters defined in `pciehp_core.c` select it and set its period:

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

The comment explains that `module_param` keeps the old boot arguments working, so a kernel with pciehp built in takes `pciehp.pciehp_poll_mode` and `pciehp.pciehp_poll_time` on its command line. In that mode [`pciehp_poll()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L800) runs the hard handler and the thread function itself:

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

The poll thread calls [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728) as long as the hard handler reports `IRQ_WAKE_THREAD` or the word holds bits, so a request made with [`pciehp_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L141) reaches the handlers on the poll thread in this mode. The period is [`pciehp_poll_time`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L35) seconds, set to 2 when it is outside 1 to 60. Either way, [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728) begins every run by marking itself running and taking the word, which the first stage below shows:

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
```

[`ist_running`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L116) is set before anything else, which keeps a sysfs writer asleep for the whole run. A pending [`RERUN_ISR`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L154) makes the thread run the hard handler first, now that a runtime PM reference makes the port accessible. `synchronize_hardirq()` waits for a hard handler still running on another CPU, and `atomic_xchg()` then takes the word and leaves 0, so a bit set after that point belongs to the next run. The second stage of [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728) dispatches the snapshot to the handlers and ends the run:

```c
/* drivers/pci/hotplug/pciehp_hpc.c:728 */
static irqreturn_t pciehp_ist(int irq, void *dev_id)
{
	struct controller *ctrl = (struct controller *)dev_id;
	struct pci_dev *pdev = ctrl_dev(ctrl);
	irqreturn_t ret;
	u32 events;
	... /* 19 lines, to :753 */
	/* Check Attention Button Pressed */
	if (events & PCI_EXP_SLTSTA_ABP)
		pciehp_handle_button_press(ctrl);

	/* Check Power Fault Detected */
	if (events & PCI_EXP_SLTSTA_PFD) {
		ctrl_err(ctrl, "Slot(%s): Power fault\n", slot_name(ctrl));
		pciehp_set_indicators(ctrl, PCI_EXP_SLTCTL_PWR_IND_OFF,
				      PCI_EXP_SLTCTL_ATTN_IND_ON);
	}

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

	ret = IRQ_HANDLED;
out:
	pci_config_pm_runtime_put(pdev);
	ctrl->ist_running = false;
	wake_up(&ctrl->requester);
	return ret;
}
```

A button press is handled first, and a power fault only logs an error and sets the indicators. Presence and link events that a successful DPC recovery or a suppressed link change explains are removed from the snapshot while the slot is in [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138). That test reads [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109) without [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110), and its checks of DPC recovery and of a suppressed link change belong to the DPC and reset code, which this page leaves out. [`reset_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114) is held for reading around the two main handlers, so a slot reset, which takes it for writing, cannot overlap them. [`DISABLE_SLOT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L153) wins over Presence Detect Changed ([`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637)) and Data Link Layer State Changed ([`PCI_EXP_SLTSTA_DLLSC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L642)) in the same snapshot, as the comment says, and the run ends by clearing [`ist_running`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L116) and waking [`requester`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L118).

The events removed from the snapshot go to [`pciehp_ignore_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L596), which the dispatch stage calls with them, and which writes the event word and can hand the events back as a request:

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

It waits for a hard handler still running and clears the ignored bits from [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104) with `atomic_and()`, so a copy the hard handler stored meanwhile is dropped as well. In poll mode it clears them in Slot Status ([`PCI_EXP_SLTSTA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L633)) too. When the link is down after all, or the device in the slot was replaced, it requests the same bits through [`pciehp_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L141), and the next run hands them to the presence handler.

So far, a request or a hardware event has become a bit in [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104). The IRQ thread has taken the word whole and passed it to the handlers, a disable request ahead of a presence or link change. The handlers that follow are where [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109) moves.

### An Attention Button press opens a five-second window

A slot with an Attention Button ([`PCI_EXP_SLTCAP_ABP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L598)) lets the user ask for a power change by pressing it, which Slot Status ([`PCI_EXP_SLTSTA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L633)) reports as Attention Button Pressed ([`PCI_EXP_SLTSTA_ABP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L634)). The specification then gives the user a 5-second abort interval, in the words commit commit [d331710ea78f](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=d331710ea78fea8b10624c87546d8bc0cd0389c9) quotes from PCIe r4.0, section 6.7.1.5. pciehp implements that window with the two blinking states and the delayed work [`button_work`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L111). A press moves the slot into a window and arms the work for 5 * HZ, and a second press inside the window cancels both. Presses arrive as interrupts because probe enables Attention Button Pressed in Slot Control ([`PCI_EXP_SLTCTL`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L610)) on a slot whose Slot Capabilities ([`PCI_EXP_SLTCAP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L597)) report a button, the choice the stage of [`pcie_enable_notification()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L821) below makes:

```c
/* drivers/pci/hotplug/pciehp_hpc.c:821 */
static void pcie_enable_notification(struct controller *ctrl)
{
	u16 cmd, mask;

	... /* 11 lines, to :836 */
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
```

Data Link Layer State Changed ([`PCI_EXP_SLTSTA_DLLSC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L642)) is enabled unconditionally, Attention Button Pressed ([`PCI_EXP_SLTSTA_ABP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L634)) on a slot with a button and Presence Detect Changed ([`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637)) on a slot without one, as the comment says. A card inserted into a slot with a button therefore raises no Presence Detect Changed interrupt, and such a slot comes up when its link comes up or when the work of a press requests a Presence Detect Changed. [`pcie_init_notification()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L960), which [`pciehp_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L185) calls, runs that function once the IRQ is requested:

```c
/* drivers/pci/hotplug/pciehp_hpc.c:960 */
int pcie_init_notification(struct controller *ctrl)
{
	if (pciehp_request_irq(ctrl))
		return -1;
	pcie_enable_notification(ctrl);
	ctrl->notification_enabled = 1;
	return 0;
}
```

[`notification_enabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L105) records that both steps succeeded, and removal tests it before it disables the notifications again. The IRQ thread then calls [`pciehp_handle_button_press()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L167) for every snapshot that holds Attention Button Pressed ([`PCI_EXP_SLTSTA_ABP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L634)), and its 49 lines fall into two pieces.

| piece | lines | stage |
|---|---|---|
| ❶ | `pciehp_ctrl.c`:167-186 | a press on [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) or [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) opens a window |
| ❷ | `pciehp_ctrl.c`:187-215 | a press inside a window cancels it, and any other state is logged |

Piece ❶ of [`pciehp_handle_button_press()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L167) takes [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110) and opens a window from a settled state:

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
```

[`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) becomes [`BLINKINGOFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L135) and [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) becomes [`BLINKINGON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L134), each with an info message naming the action that follows in 5 seconds. The Power Indicator ([`PCI_EXP_SLTCTL_PIC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L622)) starts blinking and the Attention Indicator ([`PCI_EXP_SLTCTL_AIC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L617)) turns off, and `schedule_delayed_work()` arms the work item [`button_work`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L111) for 5 * HZ, all while the lock is held. Piece ❷ of [`pciehp_handle_button_press()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L167) handles a press that arrives while a window is open:

```c
/* drivers/pci/hotplug/pciehp_ctrl.c:187 */
	case BLINKINGOFF_STATE:
	case BLINKINGON_STATE:
		/*
		 * Cancel if we are still blinking; this means that we
		 * press the attention again before the 5 sec. limit
		 * expires to cancel hot-add or hot-remove
		 */
		cancel_delayed_work(&ctrl->button_work);
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
	default:
		ctrl_err(ctrl, "Slot(%s): Button press: ignoring invalid state %#x\n",
			 slot_name(ctrl), ctrl->state);
		break;
	}
	mutex_unlock(&ctrl->state_lock);
}
```

`cancel_delayed_work()` stops a pending timer and does not wait for a work item that already runs. The work takes [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110) and re-reads [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109) before it acts, so a work item that runs after this cancel finds [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) or [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) and does nothing. [`BLINKINGOFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L135) returns to [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) with the Power Indicator ([`PCI_EXP_SLTCTL_PIC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L622)) on, and [`BLINKINGON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L134) returns to [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) with it off. Commit commit [32a8cef274fe](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=32a8cef274feacd00b748a4f13b84d60aa6d82ff) ("PCI: pciehp: Enable/disable exclusively from IRQ thread") removed the handling of the two powering states from this function, because, as its message says, the IRQ thread does not observe them itself. The default branch logs any value other than the four as invalid. Both pieces drive the indicators through [`pciehp_set_indicators()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L513) of `pciehp_hpc.c`, which writes only the indicators the slot has:

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

[`PWR_LED()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L160) and [`ATTN_LED()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L159) test the cached Slot Capabilities ([`PCI_EXP_SLTCAP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L597)), and [`INDICATOR_NOOP`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L181) leaves an indicator unchanged. A slot with neither indicator gets no Slot Control ([`PCI_EXP_SLTCTL`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L610)) write at all, so the press changes [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109) and [`button_work`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L111) whatever indicators the slot has. The figure follows [`button_work`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L111) through the two ways a window ends, expiry and cancellation, with every write of the work item marked:

```text
    controller.button_work over one Attention Button window, expired or cancelled
    ─────────────────────────────────────────────────────────────────────────────

    time             ───────────────────────────────────────────────────────────────────────────────────────────▶
    event             probe       press at 0 s          an event inside               5 s later      removal
                                                        the window
                      ▼           ▼                     ▼                             ▼              ▼
                     ┌───────────┬───────────────────────────────────────────────────┬──────────────┬───────────
    window           │ idle      │ pending: the timer runs for 5 * HZ                │ work ran,    │ synced
    expires          │           │                                                   │ idle again   │
                     └───────────┴───────────────────────────────────────────────────┴──────────────┴───────────
                     ┌───────────┬─────────────────────┬────────────────────────────────────────────┬───────────
    window           │ idle      │ pending             │ cancelled, idle; the work never runs       │ synced
    cancelled        └───────────┴─────────────────────┴────────────────────────────────────────────┴───────────
                      ①           ②                     ③ ④ ⑤ ⑥ ⑦                                    ⑧

    ① pcie_init                              pciehp_hpc.c:1038  INIT_DELAYED_WORK binds the work to its function
    ② pciehp_handle_button_press             pciehp_ctrl.c:185  schedule_delayed_work arms the 5 * HZ timer
    ③ pciehp_handle_button_press             :194               cancel_delayed_work on a second press
    ④ pciehp_handle_disable_request          :223               cancel_delayed_work before a forced disable
    ⑤ pciehp_handle_presence_or_link_change  :243               cancel_delayed_work as a powered slot goes off
    ⑥ pciehp_handle_presence_or_link_change  :276               cancel_delayed_work for an empty slot
    ⑦ pciehp_handle_presence_or_link_change  :291               cancel_delayed_work before the bring-up
    ⑧ pciehp_release_ctrl                    pciehp_hpc.c:1098  cancel_delayed_work_sync waits out a running work
```

① [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) binds [`button_work`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L111) to its function with `INIT_DELAYED_WORK` at probe. ② [`pciehp_handle_button_press()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L167) arms the timer with `schedule_delayed_work()` when a press opens a window. ③ `pciehp_handle_button_press()` cancels it with `cancel_delayed_work()` when a second press closes the window. ④ [`pciehp_handle_disable_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L217) cancels it before a forced disable, whichever window was open. ⑤ [`pciehp_handle_presence_or_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L232) cancels a power-off window when its slot loses presence or link. ⑥ `pciehp_handle_presence_or_link_change()` cancels a power-on window when the slot turns out to be empty. ⑦ `pciehp_handle_presence_or_link_change()` cancels a power-on window when an occupied slot comes up before it expires. ⑧ [`pciehp_release_ctrl()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1096) waits with `cancel_delayed_work_sync()` for a work item still running when the controller is freed.

These eight sites are the writes of [`button_work`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L111) at v7.2. The handlers cancel the work under [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110) in the IRQ thread, and removal waits for it, so a window ends by a cancellation or by the work itself, which the next subsection reads.

### The button work turns an expired window into a request

When no second press or handler cancels the window, the work runs five seconds after the press on the system workqueue, outside the IRQ thread. Commit commit [32a8cef274fe](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=32a8cef274feacd00b748a4f13b84d60aa6d82ff) made the IRQ thread the one context that enables or disables a slot, so the work turns the expired window into a request for that thread. [`pciehp_queue_pushbutton_work()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L148) recovers the controller from the work item, reads [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109) under [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110) and requests the action the window was for:

```c
/* drivers/pci/hotplug/pciehp_ctrl.c:148 */
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

`container_of()` on [`button_work`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L111) leads back to the controller, as [`to_ctrl()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L207) does for the hotplug slot. A [`BLINKINGOFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L135) window becomes a [`DISABLE_SLOT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L153) request, so the thread forces the slot off although it is occupied. A [`BLINKINGON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L134) window becomes a synthesized Presence Detect Changed ([`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637)), so the thread reads presence and link and powers the slot only if it is occupied. Any other state means a press or a handler closed the window after the timer fired, and the work requests nothing.

The work writes no state, so the slot stays in its blinking state until the thread acts on the request. Before commit commit [e8afd0d9fccc](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=e8afd0d9fccc27c8ad263db5cf5952cfcf72d6fe) ("PCI: pciehp: Cancel bringup sequence if card is not present"), an empty slot stayed in [`BLINKINGON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L134) after its window, and the next press was read as a cancellation. The presence handler's empty-slot exit, read two subsections below, now returns such a slot to [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133).

### A disable request forces the slot through POWEROFF_STATE

A disable that comes from a button window or from sysfs must turn the slot off while a card is still present, which no Slot Status ([`PCI_EXP_SLTSTA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L633)) event expresses, so the request travels as [`DISABLE_SLOT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L153). Its handler also tells the removal path that the devices below the slot may still respond. Two macros of `pciehp_ctrl.c` name that boolean, [`SAFE_REMOVAL`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L31) for a requested disable and [`SURPRISE_REMOVAL`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L32) for a card or link that went away:

```c
/* drivers/pci/hotplug/pciehp_ctrl.c:31 */
#define SAFE_REMOVAL	 true
#define SURPRISE_REMOVAL false
```

Commit commit [11e87702be65](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=11e87702be65780be92fb1f0a5b7b293954185f7) ("PCI: pciehp: Differentiate between surprise and safe removal") introduced the distinction, so that devices are quiesced on a safe removal and marked disconnected on a surprise removal. [`pciehp_handle_disable_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L217) closes a window if one is open, moves the slot to [`POWEROFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L137) and disables it as a safe removal:

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

The write of [`POWEROFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L137) is unconditional, whatever state the request found, and [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110) is released before the disable, which sleeps for as long as the hot-remove path takes. The result of [`pciehp_disable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L378) goes to [`request_result`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L117) for a sysfs writer that may be waiting for it. From [`POWEROFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L137) the disable settles the slot in [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133), as the subsection on disabling shows.

### A presence or link change first turns a powered slot off

Slot Status ([`PCI_EXP_SLTSTA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L633)) latches that presence or link changed without counting the occurrences, so the handler cannot replay events and acts on the slot's current condition. Commit commit [d331710ea78f](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=d331710ea78fea8b10624c87546d8bc0cd0389c9) states the rule that a slot in [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) is turned off unconditionally and that a slot occupied now is then turned on. Its reason is caution, since the card in the slot after a change is not assumed to be the same card. The table gives the actions the handler takes by the state it finds and by the slot's occupancy, presence or an active link.

| state found | occupied now | what the handler does | state it leaves |
|---|---|---|---|
| [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) or [`BLINKINGOFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L135) | no | disables the slot as a surprise removal | [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) |
| [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) or [`BLINKINGOFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L135) | yes | disables the slot, then enables it | [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138), or [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) when the enable fails |
| [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) | no | nothing | [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) |
| [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) or [`BLINKINGON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L134) | yes | enables the slot | [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138), or [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) when the enable fails |
| [`BLINKINGON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L134) | no | closes the power-on window and turns the Power Indicator off | [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) |

A run therefore has two passes over [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109), and the lock is released before the disable and before the enable. The figure follows one run on a powered slot that is occupied again, with the spans in which [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110) is held and the events the tracepoint records:

```text
    One presence or link change on a powered, occupied slot: the lock is held only around state
    ───────────────────────────────────────────────────────────────────────────────────────────

    time             ──────────────────────────────────────────────────────────────────────────────────────▶
                     off pass: a powered slot goes off               on pass: an occupied slot comes on
    handler run      ├────────────────────────────────────────────────────────────────────────────────────┤
    state_lock       ├───────┤                               ├───┤   ├───────┤                       ├───┤
    disable                    ├─────────────────────────────────┤
    enable                                                                     ├─────────────────────────┤
                             ╎                                   ╎           ╎                           ╎
    state            ON      ╎ POWEROFF                          ╎ OFF       ╎ POWERON                   ╎ ON or OFF
    pci_hp_event              LINK_DOWN                                       CARD_PRESENT
                              CARD_NOT_PRESENT                                LINK_UP

    In this run the handler holds state_lock only to read and write state; the tracepoint and the slot
    work run outside it, and the disable and the enable take it again only to store their result. An empty
    slot ends the run after the off pass, and a slot that was off starts at the on pass.
```

The disable and the enable each sleep for the length of a hot-remove or a hot-add, and neither runs under [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110), which other contexts take to read the state. The handler, [`pciehp_handle_presence_or_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L232), is 84 lines long, read in three pieces, the off pass in this subsection and the empty-slot exit and the on pass in the next.

| piece | lines | stage |
|---|---|---|
| Ⓐ | `pciehp_ctrl.c`:232-267 | a powered slot or a power-off window is turned off |
| Ⓑ | `pciehp_ctrl.c`:268-287 | an empty slot ends the run, closing a power-on window |
| Ⓒ | `pciehp_ctrl.c`:288-315 | an occupied slot that is off or in a power-on window is turned on |

Piece Ⓐ of [`pciehp_handle_presence_or_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L232) is the off pass, which acts on the state the run found:

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

A slot in [`BLINKINGOFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L135) loses its window and falls through to the [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) case. [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109) becomes [`POWEROFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L137), and the lock is released before the messages, the tracepoint and the disable. The snapshot's events choose the records. Data Link Layer State Changed ([`PCI_EXP_SLTSTA_DLLSC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L642)) logs Link Down and fires `pci:pci_hp_event` with [`PCI_HOTPLUG_LINK_DOWN`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci.h#L44), Presence Detect Changed ([`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637)) logs Card not present and fires it with [`PCI_HOTPLUG_CARD_NOT_PRESENT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci.h#L46), and a snapshot with both records both. The disable is a [`SURPRISE_REMOVAL`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L32), and its result is not stored in [`request_result`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L117). Any other state releases the lock and goes on to the on pass unchanged. After the off pass the slot is in [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) if it was powered, or in the state the run found, and the on pass decides from presence and link.

### An occupied slot is turned back on in the same run

The on pass needs the slot's condition after any power-off, and it asks the port two questions, whether a card is present and whether the link is up. A slot counts as occupied when either answer is yes, so a link that is up brings a slot on even when its Presence Detect State is clear. [`pciehp_card_present()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L438) answers the first question from Presence Detect State ([`PCI_EXP_SLTSTA_PDS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L640)) in Slot Status ([`PCI_EXP_SLTSTA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L633)):

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

It returns 1 or 0, or -ENODEV when the read fails or returns all ones, the answer its kerneldoc gives for a hotplug controller that is not available anymore. [`pciehp_check_link_active()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L235) answers the second question from Data Link Layer Link Active ([`PCI_EXP_LNKSTA_DLLLA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L593)) in Link Status ([`PCI_EXP_LNKSTA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L577)), with the same error convention:

```c
/* drivers/pci/hotplug/pciehp_hpc.c:235 */
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

Its debug message prints the whole Link Status ([`PCI_EXP_LNKSTA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L577)) value. With [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) set, as the page assumes, the [`ctrl_dbg()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L35) line is a callsite a reader can enable, and a kernel without it and without [`CONFIG_PCI_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L70) compiles the message out. Piece Ⓑ of [`pciehp_handle_presence_or_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L232) takes [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110) again, asks both questions and ends the run when neither answer is positive:

```c
/* drivers/pci/hotplug/pciehp_ctrl.c:268 */

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

The locals `present` and `link_active` of the handler hold the two answers, and the test treats -ENODEV like an empty slot. A slot in [`BLINKINGON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L134) returns to [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) with its window cancelled and its Power Indicator ([`PCI_EXP_SLTCTL_PIC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L622)) off, logging Card not present and firing [`PCI_HOTPLUG_CARD_NOT_PRESENT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci.h#L46) while the lock is held. Any other state is left as it is, and the run returns. Piece Ⓒ of [`pciehp_handle_presence_or_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L232) turns an occupied slot on when the run finds it in [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) or in a power-on window:

```c
/* drivers/pci/hotplug/pciehp_ctrl.c:288 */

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

A [`BLINKINGON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L134) window is cancelled and falls through, [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109) becomes [`POWERON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L136), and the lock is released before the messages and the enable. A present card logs Card present and fires [`PCI_HOTPLUG_CARD_PRESENT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci.h#L45), an active link logs Link Up and fires [`PCI_HOTPLUG_LINK_UP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci.h#L43), and the enable's result goes to [`request_result`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L117) for a sysfs writer that may wait for it. Any other state releases the lock and leaves the slot as it is.

So far, a hardware event or a request has reached the IRQ thread, and a button window has opened, expired or closed. A disable request or a presence or link change has then moved the slot into [`POWEROFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L137) or [`POWERON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L136). The enable and disable helpers settle those two transient states.

### Enabling settles POWERON_STATE into ON_STATE or OFF_STATE

[`POWERON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L136) and [`POWEROFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L137) mark a slot whose power is changing, and both must end in a settled state whatever the hardware does. Two pairs of helpers in `pciehp_ctrl.c` do that. An outer function keeps the port at D0 and stores the result in [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109), and an inner one checks the slot and hands over to the hot-add or hot-remove path. The figure shows the decisions of both pairs.

```text
    An enable and a disable, from the state the handler set to the state they store
    ───────────────────────────────────────────────────────────────────────────────

    enable, state is POWERON_STATE                           disable, state is POWEROFF_STATE
    ┌──────────────────────────────┐                         ┌──────────────────────────────┐
    │ a runtime PM reference       │                         │ a runtime PM reference       │
    │ keeps the port at D0         │                         │ keeps the port at D0         │
    └──────────────┬───────────────┘                         └──────────────┬───────────────┘
                   │                                                        │
                   ▼                                                        ▼
    ┌──────────────────────────────┐ yes: -ENODEV            ┌──────────────────────────────┐ yes: -EINVAL
    │ MRL sensor present and       ├─────────────┐           │ power controller present     ├──────────┐
    │ the latch open?              │             │           │ and slot power off?          │          │
    └──────────────┬───────────────┘             │           └──────────────┬───────────────┘          │
                   │ no                          │                          │ no                       │
                   │                             │                          │                          │
                   ▼                             │                          ▼                          │
    ┌──────────────────────────────┐ yes: 0      │           ┌──────────────────────────────┐          │
    │ power controller present     ├─────────────┤           │ hot-remove: unconfigure,     │          │
    │ and slot power on?           │             │           │ power off, wait 1 s          │          │
    └──────────────┬───────────────┘             │           └──────────────┬───────────────┘          │
                   │ no                          │                          │ result 0                 │
                   │                             │                          ▼                          │
                   ▼                             │           ┌──────────────────────────────┐          │
    ┌──────────────────────────────┐             │           │ the reference is dropped;    │◀─────────┘
    │ hot-add: power the slot,     │             │           │ under state_lock:            │
    │ check the link, enumerate    │             │           │ OFF_STATE for any result     │
    └──────────────┬───────────────┘             │           └──────────────────────────────┘
                   │ result                      │
                   ▼                             │
    ┌──────────────────────────────┐             │
    │ a non-zero result on a       │◀────────────┘
    │ slot with a button turns     │
    │ the Power Indicator off      │
    └──────────────┬───────────────┘
                   │
                   ▼
    ┌──────────────────────────────┐
    │ the reference is dropped;    │
    │ under state_lock: ON_STATE   │
    │ on 0, OFF_STATE otherwise    │
    └──────────────────────────────┘
```

Each outer helper stores the final state under [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110) after it drops its runtime PM reference, so the slot shows a powering state for the whole power change. The inner helpers test the slot's capabilities through macros of `pciehp.h` over the cached Slot Capabilities ([`PCI_EXP_SLTCAP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L597)), and the excerpt shows the five that this page meets beside [`NO_CMD_CMPL()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L161) and [`PSN()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L162):

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

Each macro is a mask test of [`slot_cap`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L95), the copy [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) made at probe, so these tests read no register. The latch and power tests do read registers, through [`pciehp_get_power_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L395) and [`pciehp_get_latch_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L417) of `pciehp_hpc.c`:

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

void pciehp_get_latch_status(struct controller *ctrl, u8 *status)
{
	struct pci_dev *pdev = ctrl_dev(ctrl);
	u16 slot_status;

	pcie_capability_read_word(pdev, PCI_EXP_SLTSTA, &slot_status);
	*status = !!(slot_status & PCI_EXP_SLTSTA_MRLSS);
}
```

[`pciehp_get_power_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L395) reports 1 when Power Controller Control ([`PCI_EXP_SLTCTL_PCC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L626)) reads [`PCI_EXP_SLTCTL_PWR_ON`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L627) and 0 when it reads [`PCI_EXP_SLTCTL_PWR_OFF`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L628), and its debug message prints the Slot Control ([`PCI_EXP_SLTCTL`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L610)) value. [`pciehp_get_latch_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L417) reports 1 when MRL Sensor State ([`PCI_EXP_SLTSTA_MRLSS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L639)) says the latch is open. [`__pciehp_enable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L317) uses both to refuse an open latch and to accept a slot that is already powered, and hands any other slot to [`board_added()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L62):

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

An open latch returns -ENODEV with a Latch open message, and a powered slot returns 0 with Already enabled. A slot without an MRL sensor or without a power controller skips the corresponding test. [`board_added()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L62) is the hot-add path, whose return value decides the state the enable stores; it powers the slot, checks the link and a power fault, and enumerates the devices:

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

A failure after the power-on jumps to the `err_exit` label of the function, which turns the slot off again and returns the error. A configuration that finds its device already present counts as success through the -EEXIST test, and a slot that comes up gets its Power Indicator ([`PCI_EXP_SLTCTL_PIC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L622)) on and its Attention Indicator ([`PCI_EXP_SLTCTL_AIC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L617)) off. The link check that [`board_added()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L62) calls, [`pciehp_check_link_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L291) of pciehp_hpc.c, also writes the event word, since a hot-add raises link and presence events of its own:

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

The check waits for the link, and on a port with In-Band Presence Detect disabled for presence, then looks for a function at device 0 of the secondary bus. When it finds one it drops Data Link Layer State Changed ([`PCI_EXP_SLTSTA_DLLSC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L642)) and Presence Detect Changed ([`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637)) from [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104), so the events the bring-up itself caused start no second run. A link still training or with no negotiated width fails the check, the link speed update records the link for the `pci:pcie_link_event` tracepoint that the tracepoint subsection reads, and a missing device fails it after that. [`pciehp_enable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L342), which the presence handler calls in [`POWERON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L136), wraps the inner helper with a runtime PM reference on the port and stores the outcome:

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

`pm_runtime_get_sync()` resumes the hotplug port for the duration of the enable, and `pm_runtime_put()` releases it. A non-zero result on a slot with an Attention Button ([`PCI_EXP_SLTCAP_ABP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L598)) turns the Power Indicator ([`PCI_EXP_SLTCTL_PIC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L622)) off, since the comment notes it may be blinking from a button window. [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109) then becomes [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) for any error and [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) for 0, and the result returns to the presence handler, which stores it in [`request_result`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L117). An enable thus ends in [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) when the hot-add path returned 0 or the slot was already powered, and in [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) otherwise.

### Disabling settles POWEROFF_STATE into OFF_STATE

A disable ends in [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) whatever its result, and its inner helper decides only whether the hot-remove path runs. [`__pciehp_disable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L361) refuses a slot whose power is already off and hands any other slot to [`remove_board()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L112):

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
```

With a power controller present, a slot whose Power Controller Control ([`PCI_EXP_SLTCTL_PCC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L626)) reads off returns -EINVAL with Already disabled, and any other slot is removed and the function returns 0. [`remove_board()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L112) is the hot-remove path, and besides unconfiguring the devices and cutting power it removes from [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104) the events its own power-off raised:

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

The parameter `safe_removal` of `remove_board()` carries the removal kind, [`SAFE_REMOVAL`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L31) or [`SURPRISE_REMOVAL`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L32), to the unconfigure call. After the power-off and the one-second wait, `atomic_and()` drops Data Link Layer State Changed ([`PCI_EXP_SLTSTA_DLLSC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L642)) and Presence Detect Changed ([`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637)) from the word. The link-down and presence change that the power-off caused therefore start no new run, a step commit commit [3943af9d01e9](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=3943af9d01e94330d0cfac6fccdbc829aad50c92) ("PCI: pciehp: Ignore Link State Changes after powering off a slot") added. The Power Indicator ([`PCI_EXP_SLTCTL_PIC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L622)) then turns off. [`pciehp_disable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L378) wraps the inner helper the way the enable side does:

```c
/* drivers/pci/hotplug/pciehp_ctrl.c:378 */
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

[`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109) becomes [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) under [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110) for any result, and the result returns to the caller. [`pciehp_handle_disable_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L217) stores it in [`request_result`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L117), and the off pass of the presence handler discards it. The two settled states are thus reached from the transient ones inside the IRQ thread, and the next subsections turn to a writer outside the thread that waits for them.

### The power file reaches pciehp through the slot's ops

A user enables or disables a slot by writing 1 or 0 to the `power` file of its directory under /sys/bus/pci/slots. The file belongs to the PCI hotplug core that [`CONFIG_HOTPLUG_PCI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/Kconfig#L6) builds. The core reaches a driver through the [`struct hotplug_slot_ops`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L38) the driver registered with the slot, a function pointer struct whose first two members the power file calls:

```c
/* include/linux/pci_hotplug.h:38 */
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

[`enable_slot`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L39) and [`disable_slot`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L40) receive the [`struct hotplug_slot`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L57) the driver embedded in its own object. The other members back the slot's attention, latch and adapter files, a hardware test, the read side of the power file and the slot reset, all outside this page. [`power_write_file()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L67) of `pci_hotplug_core.c` parses the written value and calls the matching member:

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

A 1 calls [`enable_slot`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L39) and a 0 calls [`disable_slot`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L40), a non-zero return becomes the write's error, and any other value fails with -EINVAL. The write therefore blocks for as long as the callback does. pciehp sets both members in [`init_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L51) at probe and names the slot after its Physical Slot Number ([`PCI_EXP_SLTCAP_PSN`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L609)):

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
	... /* 13 lines, to :77 */
	/* register this slot with the hotplug pci core */
	ctrl->hotplug_slot.ops = ops;
	snprintf(name, SLOT_NAME_SIZE, "%u", PSN(ctrl));

	retval = pci_hp_initialize(&ctrl->hotplug_slot,
				   ctrl->pcie->port->subordinate,
				   PCI_SLOT_ALL_DEVICES, name);
```

[`PSN()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L162) extracts the number from [`slot_cap`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L95), and [`slot_name()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L202) returns the name that `snprintf()` formats from it in the `Slot(%s)` messages of pciehp. The power file thus calls into pciehp in the writer's process, and the next subsection follows that writer through the request and its wait.

### A sysfs request sleeps on requester until the thread finishes

The writer of the power file runs outside the IRQ thread, so it does not change the slot itself. It asks the thread and waits for the answer. Commit commit [157c1062fcd8](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=157c1062fcd86ade3c674503705033051fd3d401) ("PCI: pciehp: Avoid returning prematurely from sysfs requests") states the rule that a sysfs request to enable or disable a slot should not return before it has been carried out. What a write does depends on the state it finds, as the table shows.

| state found | write of 1, [`pciehp_sysfs_enable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L393) | write of 0, [`pciehp_sysfs_disable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L432) |
|---|---|---|
| [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) or [`BLINKINGON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L134) | requests [`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637) and returns the thread's result | logs Already disabled, returns -ENODEV |
| [`POWERON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L136) | logs Already in powering on state, returns -ENODEV | logs Already disabled, returns -ENODEV |
| [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) or [`BLINKINGOFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L135) | logs Already enabled, returns -ENODEV | requests [`DISABLE_SLOT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L153) and returns the thread's result |
| [`POWEROFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L137) | logs Already enabled, returns -ENODEV | logs Already in powering off state, returns -ENODEV |

The writer and the thread exchange the request through [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104) and the answer through [`request_result`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L117) and [`requester`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L118). The figure follows a write of 1 to an empty slot in [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133), the case that shows why the result is preset:

```text
    A write of 1 to the power file of an empty OFF_STATE slot, handed to the IRQ thread and back
    ─────────────────────────────────────────────────────────────────────────────────────────────

    time ↓
    writer of the power file             ╎ IRQ thread of the port
    ─────────────────────────────────────┼─────────────────────────────────────────────────
    under state_lock: OFF_STATE, so the  ╎ asleep
    request goes to the thread           ╎
    request_result = -ENODEV             ╎
    PDC ORed into pending_events ──────────▶ woken: ist_running = true,
                                         ╎ pending_events taken, now 0
    asleep on requester: pending_events  ╎ presence handler: the slot is
    is 0, but ist_running is true        ╎ empty, state stays OFF_STATE
                                         ╎ request_result left at -ENODEV
                                         ╎ ist_running = false
    woken, condition true ◀─────────────── requester woken
    returns -ENODEV to the write         ╎ asleep
```

The writer sleeps until the word is 0 and the thread is not running, and the empty slot makes the presence handler return without an enable, so the write returns the preset -ENODEV. [`pciehp_sysfs_enable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L393) is the left lane for a write of 1:

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
	case POWERON_STATE:
		ctrl_info(ctrl, "Slot(%s): Already in powering on state\n",
			  slot_name(ctrl));
		break;
	case BLINKINGOFF_STATE:
	case ON_STATE:
	case POWEROFF_STATE:
		ctrl_info(ctrl, "Slot(%s): Already enabled\n",
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

[`to_ctrl()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L207) finds the controller, and [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110) is released before the request so that the thread can take it. The comment explains the preset of [`request_result`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L117) to -ENODEV: the IRQ thread becomes a no-op if the user pulls out the card before the thread wakes up. `wait_event()` then sleeps on [`requester`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L118) until the word is 0 and [`ist_running`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L116) is clear, and the function returns the result the thread left. [`pciehp_sysfs_disable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L432) has the same shape for a write of 0, with [`DISABLE_SLOT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L153) as the request:

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

It presets nothing, and the [`DISABLE_SLOT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L153) request reaches [`pciehp_handle_disable_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L217), which stores the result of the disable before the run ends. Both functions log why they do nothing in the other states, and an unknown value of [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109) is logged as an error. The three members of the exchange are written by several functions, and the strip shows every write of them along one enable request that finds an occupied slot:

```text
    pending_events, ist_running and request_result over one sysfs enable request
    ────────────────────────────────────────────────────────────────────────────

    time            ──────────────────────────────────────────────────────────────────────────────────────────▶
    event            probe    sysfs     request      thread    snapshot  handler        thread      removal
                              write                  starts    taken     runs           ends
                     ▼        ▼         ▼            ▼         ▼         ▼              ▼           ▼
                    ┌────────┬─────────┬────────────┬─────────┬─────────┬──────────────┬───────────┬──────────
    pending_events  │ 0      │ 0       │ PDC        │ PDC     │ 0       │ 0            │ 0         │ freed
                    └────────┴─────────┴────────────┴─────────┴─────────┴──────────────┴───────────┴──────────
                    ┌────────┬─────────┬────────────┬─────────┬─────────┬──────────────┬───────────┬──────────
    ist_running     │ false  │ false   │ false      │ true    │ true    │ true         │ false     │ freed
                    └────────┴─────────┴────────────┴─────────┴─────────┴──────────────┴───────────┴──────────
                    ┌────────┬─────────┬────────────┬─────────┬─────────┬──────────────┬───────────┬──────────
    request_result  │ 0      │ -ENODEV │ -ENODEV    │ -ENODEV │ -ENODEV │ 0            │ 0         │ freed
                    └────────┴─────────┴────────────┴─────────┴─────────┴──────────────┴───────────┴──────────
                     «1»      «14»      «2» «3» «4»  «5» «6»   «7» «9»   «10» «11»      «8»         «15»
                                                                         «12» «13»

    «1»  pcie_init                              pciehp_hpc.c:1014  the zeroed allocation starts all three fields at 0
    «2»  pciehp_request                         pciehp_ctrl.c:143  atomic_or adds a request bit
    «3»  pciehp_isr                             pciehp_hpc.c:648   atomic_or adds RERUN_ISR for an inaccessible port
    «4»  pciehp_isr                             :724               atomic_or adds the latched Slot Status events
    «5»  pciehp_ist                             :735               the thread marks itself running
    «6»  pciehp_ist                             :739               atomic_fetch_and clears RERUN_ISR
    «7»  pciehp_ist                             :747               atomic_xchg takes the word and leaves 0
    «8»  pciehp_ist                             :795               the thread marks itself done before the wake-up
    «9»  pciehp_ignore_link_change              :606               atomic_and drops a suppressed link change
    «10» pciehp_handle_disable_request          pciehp_ctrl.c:229  stores the result of a forced disable
    «11» pciehp_handle_presence_or_link_change  :309               stores the result of an enable
    «12» pciehp_check_link_status               pciehp_hpc.c:310   atomic_and drops the events of a hot-add
    «13» remove_board                           pciehp_ctrl.c:127  atomic_and drops its own PDC and DLLSC
    «14» pciehp_sysfs_enable_slot               :406               presets -ENODEV before the request
    «15» pciehp_release_ctrl                    pciehp_hpc.c:1099  kfree() ends all three fields
```

«1» [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) starts all three members at 0 with the zeroed allocation. «2» [`pciehp_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L141) ORs the requested bit into [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104). «3» [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623) ORs [`RERUN_ISR`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L154) into the word when the port cannot be read in hard IRQ context. «4» `pciehp_isr()` ORs the latched Slot Status ([`PCI_EXP_SLTSTA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L633)) events into the same word. «5» [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728) sets [`ist_running`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L116) before it reads the word. «6» `pciehp_ist()` clears [`RERUN_ISR`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L154) with `atomic_fetch_and()`. «7» `pciehp_ist()` takes the word with `atomic_xchg()` and leaves 0. «8» `pciehp_ist()` clears [`ist_running`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L116) at the end of the run, before it wakes [`requester`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L118). «9» [`pciehp_ignore_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L596) drops a suppressed link change from the word. «10» [`pciehp_handle_disable_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L217) stores the result of a forced disable. «11» [`pciehp_handle_presence_or_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L232) stores the result of an enable. «12» [`pciehp_check_link_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L291) drops the link and presence events of a hot-add that found its device. «13» [`remove_board()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L112) drops the link and presence events its own power-off raised. «14» [`pciehp_sysfs_enable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L393) presets [`request_result`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L117) to -ENODEV before its request. «15» [`pciehp_release_ctrl()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1096) frees the three members with the controller.

The marks follow the order in which the page shows their code, so «14» comes first in time and «2» after it. Between «7» and «8» the word is already 0 while the handler still runs, and [`ist_running`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L116) keeps the writer asleep through that interval, the reason commit commit [157c1062fcd8](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=157c1062fcd86ade3c674503705033051fd3d401) added the member. At v7.2 these fifteen sites are the writes of the three members, and the page shows each of them.

### Probe and resume ask the thread to re-check presence

A slot can change while no interrupt is delivered, before probe, during system sleep or while the port is runtime suspended. The Slot Status ([`PCI_EXP_SLTSTA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L633)) events of those intervals may be stale or missing, so probe and resume compare the slot's presence with [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109) and request a run when the two disagree. [`pciehp_check_presence()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L167) makes that comparison, and its comment gives the reason in the specification's words:

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

An occupied slot in [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) or [`BLINKINGON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L134), or an empty slot in [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) or [`BLINKINGOFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L135), gets a synthesized Presence Detect Changed ([`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637)), and a slot whose presence agrees with its state gets no request. The comparison runs under [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110) and the read side of [`reset_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114), so neither a handler nor a slot reset changes the slot between the read and the request. Probe calls the check last, and the resume callbacks of `pciehp_core.c` call it too, in [`pciehp_resume()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L318) directly and in [`pciehp_runtime_resume()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L336) through `pciehp_resume()`:

```c
/* drivers/pci/hotplug/pciehp_core.c:318 */
static int pciehp_resume(struct pcie_device *dev)
{
	struct controller *ctrl = get_service_data(dev);

	if (pme_is_native(dev))
		pcie_enable_interrupt(ctrl);

	pciehp_check_presence(ctrl);

	return 0;
}

static int pciehp_runtime_suspend(struct pcie_device *dev)
{
	pciehp_disable_interrupt(dev);
	return 0;
}

static int pciehp_runtime_resume(struct pcie_device *dev)
{
	struct controller *ctrl = get_service_data(dev);

	/* pci_restore_state() just wrote to the Slot Control register */
	ctrl->cmd_started = jiffies;
	ctrl->cmd_busy = true;

	/* clear spurious events from rediscovery of inserted card */
	if ((ctrl->state == ON_STATE || ctrl->state == BLINKINGOFF_STATE) &&
	     pme_is_native(dev))
		pcie_clear_hotplug_events(ctrl);

	return pciehp_resume(dev);
}
```

With [`CONFIG_PM`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L217) set, as the page assumes, these callbacks are built; a kernel without it has no resume path, and probe is then the one caller of the check. [`pciehp_runtime_resume()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L336) tests [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109) for [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) or [`BLINKINGOFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L135) without [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110) before it clears stale events. System resume also catches a device that was replaced during sleep, earlier, in [`pciehp_resume_noirq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L288), which [`CONFIG_PM_SLEEP`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L140) builds:

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

For a slot in [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) or [`BLINKINGOFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L135), it clears stale events and, when the device in the slot is not the one seen before, marks the old devices disconnected and requests Presence Detect Changed ([`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637)). Its state test reads without [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110) as well, and its debug message is a dynamic-debug callsite under [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120). Probe and resume thus reach the slot through requests, and the handlers of the IRQ thread make the change.

### The IRQ thread writes state, and four readers skip the lock

Several contexts read [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109), and which of them may trust what they read depends on where the writes happen. The kerneldoc of [`struct controller`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L91) gives [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110) two duties, at [`pciehp.h:73-75`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L73):

```c
/* drivers/pci/hotplug/pciehp.h:73 */
 * @state_lock: protects reads and writes of @state;
 *	protects scheduling, execution and cancellation of @button_work
 * @button_work: work item to turn the slot on or off after 5 seconds
```

The first duty covers the state and the second the button work of the window subsections. After probe every write of [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109) shown on this page takes the lock. The writers also run in one thread, the one that runs [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728). At v7.2 the three handlers have [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728) as their one caller, and the enable and disable helpers are called from those handlers alone. [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) writes before the thread exists. The readers outside that thread use the field in the ways the table lists.

| reader | context | [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110) | what the value decides |
|---|---|---|---|
| [`pciehp_queue_pushbutton_work()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L148) | system workqueue | held | the request for an expired window |
| [`pciehp_sysfs_enable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L393), [`pciehp_sysfs_disable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L432) | writer of the power file | held | whether to request and wait |
| [`pciehp_check_presence()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L167) | probe and resume | held | whether to request Presence Detect Changed |
| [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728) | the IRQ thread itself | not held | whether a recovered or suppressed link change is ignored |
| [`pciehp_slot_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L915) | AER or DPC recovery | not held | whether to check the link after a reset |
| [`pciehp_resume_noirq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L288) | system resume, noirq phase | not held | whether to clear events and look for a replaced device |
| [`pciehp_runtime_resume()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L336) | runtime resume | not held | whether to clear stale events |

The unlocked read in [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728) runs in the thread that writes the field, so it reads the thread's own last write, as the lines of its dispatch stage show again:

```c
/* drivers/pci/hotplug/pciehp_hpc.c:728 */
static irqreturn_t pciehp_ist(int irq, void *dev_id)
{
	struct controller *ctrl = (struct controller *)dev_id;
	... /* 38 lines, to :769 */
	if ((events & (PCI_EXP_SLTSTA_PDC | PCI_EXP_SLTSTA_DLLSC)) &&
	    (pci_dpc_recovered(pdev) || pci_hp_spurious_link_change(pdev)) &&
	    ctrl->state == ON_STATE) {
		u16 ignored_events = PCI_EXP_SLTSTA_DLLSC;

		if (!ctrl->inband_presence_disabled)
			ignored_events |= PCI_EXP_SLTSTA_PDC;

		events &= ~ignored_events;
		pciehp_ignore_link_change(ctrl, pdev, irq, ignored_events);
	}
```

The test admits [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) alone, the state of a slot whose devices are enumerated, and the events it removes from this snapshot reach the presence handler in a later run when the suppression requests them again. [`pciehp_slot_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L915) is the hotplug service's callback after AER or DPC reset a link above the port, and it reads the field from the recovery context:

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

It acts for a slot in [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138), clears the Data Link Layer State Changed ([`PCI_EXP_SLTSTA_DLLSC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L642)) the reset latched and requests that event from the thread when the link has not come back. Its read takes no lock, and its change goes through [`pciehp_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L141), so the thread still makes the transition.

So far, every change of [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109) after probe has been made in the IRQ thread under [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110), and the readers outside the thread either take the lock or act through a request. What remains is the end of the controller and the traces the machine leaves.

### Removal stops the thread before the controller is freed

Removing the hotplug service ends the state machine, and the controller can be freed only once no interrupt, IRQ thread or button work can run on it. [`pciehp_remove()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L245), the service's remove callback, takes the slot away from user space first, then shuts the notifications down and frees the controller:

```c
/* drivers/pci/hotplug/pciehp_core.c:245 */
static void pciehp_remove(struct pcie_device *dev)
{
	struct controller *ctrl = get_service_data(dev);

	pci_hp_del(&ctrl->hotplug_slot);
	pcie_shutdown_notification(ctrl);
	cleanup_slot(ctrl);
	pciehp_release_ctrl(ctrl);
}
```

Taking the slot away first means no new sysfs request arrives. [`pcie_shutdown_notification()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L969) undoes what [`pcie_init_notification()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L960) set up, guarded by [`notification_enabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L105):

```c
/* drivers/pci/hotplug/pciehp_hpc.c:969 */
void pcie_shutdown_notification(struct controller *ctrl)
{
	if (ctrl->notification_enabled) {
		pcie_disable_notification(ctrl);
		pciehp_free_irq(ctrl);
		ctrl->notification_enabled = 0;
	}
}
```

The notifications are disabled in Slot Control ([`PCI_EXP_SLTCTL`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L610)), and [`pciehp_free_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L78) frees the interrupt or stops the poll thread. [`pciehp_release_ctrl()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1096) then waits for the button work and frees the controller:

```c
/* drivers/pci/hotplug/pciehp_hpc.c:1096 */
void pciehp_release_ctrl(struct controller *ctrl)
{
	cancel_delayed_work_sync(&ctrl->button_work);
	kfree(ctrl);
}
```

`cancel_delayed_work_sync()` cancels a pending window and waits for a work item that is running, the button figure's ⑧, so the work cannot request a run on freed memory. `kfree()` then ends [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109), the state figure's «13», together with [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104) and the request members, the strip's «13».

### The pci_hp_event tracepoint records the presence handler's decisions

To watch the state machine without debug messages, a reader can enable one tracepoint, `pci:pci_hp_event`, which the presence and link handler fires for each presence or link fact it acts on. Its event codes are an enum of the UAPI header, so that user-space tools can parse them:

```c
/* include/uapi/linux/pci.h:42 */
enum pci_hotplug_event {
	PCI_HOTPLUG_LINK_UP,
	PCI_HOTPLUG_LINK_DOWN,
	PCI_HOTPLUG_CARD_PRESENT,
	PCI_HOTPLUG_CARD_NOT_PRESENT,
};
```

The trace header turns the four codes into the strings the record prints, with a macro that lists each code beside its name:

```c
/* include/trace/events/pci.h:11 */
#define PCI_HOTPLUG_EVENT						\
	EM(PCI_HOTPLUG_LINK_UP,			"LINK_UP")		\
	EM(PCI_HOTPLUG_LINK_DOWN,		"LINK_DOWN")		\
	EM(PCI_HOTPLUG_CARD_PRESENT,		"CARD_PRESENT")		\
	EMe(PCI_HOTPLUG_CARD_NOT_PRESENT,	"CARD_NOT_PRESENT")
```

The event itself, [`trace_pci_hp_event`](https://elixir.bootlin.com/linux/v7.2/source/include/trace/events/pci.h#L43), is defined with `TRACE_EVENT` in include/trace/events/pci.h, which generates the function the handler calls:

```c
/* include/trace/events/pci.h:34 */
/*
 * Note: For generic PCI hotplug events, we pass already-resolved strings
 * (port_name, slot) instead of driver-specific structures like 'struct
 * controller'.  This is because different PCI hotplug drivers (pciehp, cpqphp,
 * ibmphp, shpchp) define their own versions of 'struct controller' with
 * different fields and helper functions. Using driver-specific structures would
 * make the tracepoint interface non-generic and cause compatibility issues
 * across different drivers.
 */
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

The record holds the hotplug port's name, the slot's name and the event code, and prints the code as "LINK_UP", "LINK_DOWN", "CARD_PRESENT" or "CARD_NOT_PRESENT". The comment above it explains that the strings are passed resolved so that several hotplug drivers could share the event. At v7.2 the five calls in [`pciehp_handle_presence_or_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L232) are the event's call sites, and the table lists them with the piece that holds each.

| site | piece | event | condition |
|---|---|---|---|
| [`pciehp_ctrl.c:251-253`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L251) | Ⓐ, off pass | [`PCI_HOTPLUG_LINK_DOWN`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci.h#L44) | Data Link Layer State Changed in the snapshot of a powered slot |
| [`pciehp_ctrl.c:258-260`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L258) | Ⓐ, off pass | [`PCI_HOTPLUG_CARD_NOT_PRESENT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci.h#L46) | Presence Detect Changed in the snapshot of a powered slot |
| [`pciehp_ctrl.c:281-283`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L281) | Ⓑ, empty-slot exit | [`PCI_HOTPLUG_CARD_NOT_PRESENT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci.h#L46) | a power-on window found the slot empty |
| [`pciehp_ctrl.c:299-301`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L299) | Ⓒ, on pass | [`PCI_HOTPLUG_CARD_PRESENT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci.h#L45) | a card is present as the slot comes on |
| [`pciehp_ctrl.c:305-307`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L305) | Ⓒ, on pass | [`PCI_HOTPLUG_LINK_UP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci.h#L43) | the link is up as the slot comes on |

The button handler, the disable request and the sysfs functions make no call of this event, so a forced disable leaves no `pci:pci_hp_event` record. The PCI core instantiates its tracepoints in one file that the Makefile of drivers/pci builds with [`CONFIG_TRACING`](https://elixir.bootlin.com/linux/v7.2/source/kernel/trace/Kconfig#L179):

```c
/* drivers/pci/Makefile:52 */
CFLAGS_trace.o := -I$(src)
obj-$(CONFIG_TRACING)		+= trace.o
```

With [`CONFIG_TRACING`](https://elixir.bootlin.com/linux/v7.2/source/kernel/trace/Kconfig#L179) set, as the page assumes, the event appears under `events/pci` of tracefs, and [`Documentation/trace/events-pci.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/trace/events-pci.rst) shows it enabled through `/sys/kernel/debug/tracing/events/pci/pci_hp_event/enable`.

One more event fires on the paths this page hands over to. The link check of the hot-add path calls [`__pcie_update_link_speed()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L637) of drivers/pci/pci.h, which stores the link speed in the secondary bus and records the link through `pci:pcie_link_event`:

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

The record carries the `PCIE_HOTPLUG` reason the link check passes, the negotiated width and the status bits of Link Status ([`PCI_EXP_LNKSTA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L577)). A hot-add therefore leaves a `pci:pci_hp_event` record from the presence handler and a `pci:pcie_link_event` record from its link check, and the speeds stored in the bus belong to the link-speed code, which this page leaves out.

### Messages, hand-offs and files expose the rest

Besides the tracepoint, the state machine shows itself in the kernel log, in the hand-offs between the contexts it crosses and in two kinds of file. The messages go through four macros of `pciehp.h` that print with the hotplug port's name, and the comment above them says how to enable the debug level:

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

[`ctrl_info()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L39) and [`ctrl_err()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L37) print through `pci_info()` and `pci_err()` on the hotplug port, and [`ctrl_dbg()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L35) prints through `pci_dbg()`, a dynamic-debug callsite under [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120). The comment enables those callsites with `dyndbg="file pciehp* +p"` on the command line, and the same query written to `/sys/kernel/debug/dynamic_debug/control` enables them at run time. [`CONFIG_PCI_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L70), which the page assumes unset, would define DEBUG for every file under drivers/pci, as the Makefile line shows:

```c
/* drivers/pci/Makefile:50 */
subdir-ccflags-$(CONFIG_PCI_DEBUG) := -DDEBUG
```

The handlers' messages print at the info and error levels whenever their branch runs, and the table lists them with the state change each one reports. Every one of them starts with `Slot(%s): `, the slot name.

| site | level | message | what it reports |
|---|---|---|---|
| [`pciehp_ctrl.c:175`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L175) | info | Button press: will power off in 5 sec | [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) to [`BLINKINGOFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L135) |
| [`pciehp_ctrl.c:179`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L179) | info | Button press: will power on in 5 sec | [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) to [`BLINKINGON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L134) |
| [`pciehp_ctrl.c:199`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L199) | info | Button press: canceling request to power off | [`BLINKINGOFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L135) back to [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) |
| [`pciehp_ctrl.c:205`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L205) | info | Button press: canceling request to power on | [`BLINKINGON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L134) back to [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) |
| [`pciehp_ctrl.c:210`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L210) | err | Button press: ignoring invalid state %#x | a press in a value outside the four [`pciehp_handle_button_press()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L167) handles |
| [`pciehp_ctrl.c:249`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L249), [`pciehp_ctrl.c:256`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L256) | info | Link Down, Card not present | the off pass of [`pciehp_handle_presence_or_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L232) |
| [`pciehp_ctrl.c:279`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L279) | info | Card not present | a power-on window closed on an empty slot |
| [`pciehp_ctrl.c:297`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L297), [`pciehp_ctrl.c:304`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L304) | info | Card present, Link Up | the on pass of [`pciehp_handle_presence_or_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L232) |
| [`pciehp_ctrl.c:324`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L324), [`pciehp_ctrl.c:333`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L333) | info | Latch open, Already enabled | why [`__pciehp_enable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L317) did not hand over to the hot-add path |
| [`pciehp_ctrl.c:368`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L368) | info | Already disabled | why [`__pciehp_disable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L361) did not hand over to the hot-remove path |
| [`pciehp_ctrl.c:413`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L413), [`pciehp_ctrl.c:419`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L419), [`pciehp_ctrl.c:423`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L423) | info, info, err | Already in powering on state, Already enabled, Invalid state %#x | why [`pciehp_sysfs_enable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L393) made no request |
| [`pciehp_ctrl.c:447`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L447), [`pciehp_ctrl.c:453`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L453), [`pciehp_ctrl.c:457`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L457) | info, info, err | Already in powering off state, Already disabled, Invalid state %#x | why [`pciehp_sysfs_disable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L432) made no request |
| [`pciehp_hpc.c:759`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L759) | err | Power fault | Power Fault Detected in a snapshot of [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728) |

The dynamic-debug callsites these paths reach print register values and event words, and enabling them shows what the handlers decided on. The table lists the ones this page shows.

| site | message | what a reader learns |
|---|---|---|
| [`pciehp_hpc.c:699`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L699) | pending interrupts %#06x from Slot Status | the event bits the hard IRQ handler passes on |
| [`pciehp_hpc.c:719`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L719) | ignoring hotplug event %#06x | events dropped on a port flagged [`ignore_hotplug`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L424) |
| [`pciehp_hpc.c:246`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L246) | %s: lnk_status = %x | the Link Status value behind the link answer of the on pass |
| [`pciehp_hpc.c:401`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L401) | %s: SLOTCTRL %x value read %x | the Slot Control value behind the power checks of enable and disable |
| [`pciehp_hpc.c:529`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L529) | %s: SLOTCTRL %x write cmd %x | an indicator write of the button handler or a handler's exit |
| [`pciehp_core.c:307`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L307) | device replaced during system sleep | the replacement check of system resume |

The flows cross four hand-offs. The hard IRQ handler hands events to the IRQ thread by returning `IRQ_WAKE_THREAD`, and [`pciehp_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L141) wakes the same thread with `irq_wake_thread()`, or the poll thread picks the word up when [`pciehp_poll_mode`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L34) is set. [`button_work`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L111) moves an expired window from the IRQ thread to the system workqueue and back through a request. A sysfs writer sleeps on [`requester`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L118) until the end of a run wakes it, and the enable and disable helpers hold a runtime PM reference on the port for the duration of the slot change. The state machine's own code crosses no RCU callback or notifier chain; the hot-add and hot-remove paths it hands over to register and unregister devices with the driver core, outside this page.

The files that expose the machine are the slot's `power` file under /sys/bus/pci/slots, whose writes become the sysfs requests, and the parameters `pciehp_poll_mode` and `pciehp_poll_time` under /sys/module/pciehp/parameters, writable with mode 0644, besides the matching boot parameters. [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109) itself appears in no file. pciehp creates no debugfs or procfs entry and has no fault-injection point at v7.2, so the state is observed through the messages and the tracepoint above.
