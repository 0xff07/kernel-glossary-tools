# Fixture port

> CAUTION: AI-GENERATED CONTENT
>
> STRICTLY DO NOT SUBMIT THIS UPSTREAM UNLESS YOU ARE AN EXPERT INTIMATELY FAMILIAR WITH THIS SUBSYSTEM.

A port is one end of a link, and the kernel keeps one record per port so that the low-power states a link runs in are known at both ends. The record decides whether a link may drop into a CL state and which end programs the adapter. A state is enabled for the whole link, so the two records are written together under one lock. This page traces how a mask of states is validated, written to both adapters, recorded and cleared again.


## DETAILS

These figures exercise display-cell geometry.

### Hop-array path length

A through-trunk needs both vertical directions at the path-length bar.

```
    struct tb_path, and the two adapters each element of hops[] names
    ─────────────────────────────────────────────────────────────────

    struct tb_path       one allocation: the header, then path_length elements of hops[]
    ┌───────────────────────────────────────────────────────────────────────────────┐
    │  tb    name    priority    weight    drop_packages    clear_fc                │
    │  ingress_fc_enable    egress_fc_enable    ingress_shared_buffer               │
    │  egress_shared_buffer    activated    alloc_hopid    path_length = 2          │
    │                                                                               │
    │   ┌───────────────────────────────┬───────────────────────────────┐           │
    │   │ hops[0]                       │ hops[1]                       │           │
    │   │   in_hop_index      8         │   in_hop_index      h         │           │
    │   │   in_counter_index -1         │   in_counter_index -1         │           │
    │   │   next_hop_index    h         │   next_hop_index    8         │           │
    │   └───────────────┬───────────────┴───────────────┬───────────────┘           │
    │   ├───────────────┴──── path_length cells ────────┴───────────────┤           │
    └───────────────────┼───────────────────────────────┼───────────────────────────┘
                        │ in_port and out_port          │ in_port and out_port
    ┌── host router  route 0 ──┬───────┐    ┌── device router  route 0x3 ──┬────────┐
    │   ┌──────────────────────▼─────┐ │    │   ┌──────────────────────────▼──────┐ │
    │   │ PCIe down adapter      #9  │ │    │   │ lane 0 adapter            #1    │ │
    │   └───────────┬────────────────┘ │    │   └───────────┬─────────────────────┘ │
    │   ┌───────────▼────────────────┐ │    │   ┌───────────▼─────────────────────┐ │
    │   │ lane 0 adapter         #3  │ │    │   │ PCIe up adapter           #9    │ │
    │   └───────────┬────────────────┘ │    │   └─────────────────────────────────┘ │
    └───────────────┼──────────────────┘    └───────────────────────────────────────┘
                    │  the link, crossed by a packet carrying HopID h
                    └──────────────────────────────▶  lane 0 adapter #1 of route 0x3

    ▼   the cell above names the adapter the arrow lands on    #n  the adapter number
    h   one value: hops[0].next_hop_index and hops[1].in_hop_index hold it alike
```

### Topology decisions

Side exits from a box need a right-facing junction; heads embedded in top borders remain valid.

```
    One pass over one adapter: the questions and where each answer leads
    ────────────────────────────────────────────────────────────────────

                  an adapter of the router being scanned
                                 │
                      ┌──────────▼──────────┐   yes
                   ①  │ faces the host?     │───────▶ nothing done
                      └──────────┬──────────┘
                                 │ no
                      ┌──────────▼──────────┐   yes
                   ②  │ display asking for  │───────▶ a plug event is queued
                      │ a tunnel?           │
                      └──────────┬──────────┘
                                 │ no
                      ┌──────────▼──────────┐   yes
                   ③  │ not a lane adapter? │───────▶ nothing done
                      └──────────┬──────────┘
                                 │ no
                      ┌──────────▼──────────┐   yes
                   ④  │ secondary lane?     │───────▶ nothing done
                      └──────────┬──────────┘
                                 │ no
       ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┼ ─ ─ ─ ─ ─ ─ ─ ─ ─  a power reference is
                                 │                    taken below this line
                      ┌──────────▼──────────┐   yes   and released at every
                   ⑤  │ link not up?        │───────▶ exit under it
                      └──────────┬──────────┘
                                 │ no
                      ┌──────────▼──────────┐   yes
                   ⑥  │ adapter already     │───────▶ nothing done
                      │ has a peer?         │
                      └──────────┬──────────┘
                                 │ no
                      ┌──────────▼──────────┐   no
                   ⑦  │ router answers?     │───────▶ retimers exposed, maybe
                      └──────────┬──────────┘         another domain recorded
                                 │ yes
                      ┌──────────▼──────────┐   no
                   ⑧  │ router configured?  │───────▶ router object released
                      └──────────┬──────────┘
                                 │ yes
                      ┌──────────▼──────────┐   no
                   ⑨  │ router registered?  │───────▶ router object released
                      └──────────┬──────────┘
                                 │ yes
                      ┌──────────▼──────────┐
                      │ link joined, raised │
                      │ to two lanes, marked│
                      └──────────┬──────────┘
                                 │
                      ┌──────────▼──────────┐
                   ⑩  │ descend into the    │
                      │ router just added   │
                      └──────────┬──────────┘
                                 │
                                 └─ back-edge: every adapter of that router
                                    enters this chart at the top

    ①  tb_scan_port  tb.c:1296  the adapter facing the host is refused
    ②  tb_scan_port  tb.c:1299  a DP OUT with HPD set and no tunnel is handed on
    ③  tb_scan_port  tb.c:1307  an adapter that is not a lane adapter is refused
    ④  tb_scan_port  tb.c:1309  the secondary lane of a pair is refused
    ⑤  tb_scan_port  tb.c:1318  the link behind the adapter never reported up
    ⑥  tb_scan_port  tb.c:1320  the adapter already records a peer adapter
    ⑦  tb_scan_port  tb.c:1327  the router behind the adapter could not be allocated
    ⑧  tb_scan_port  tb.c:1344  the router could not be configured
    ⑨  tb_scan_port  tb.c:1375  the router could not be registered
    ⑩  tb_scan_port  tb.c:1422  the pass descends into the router it just added
```

### TMU field pair

Each self-loop must attach to the bottom border.

```
    The (mode, mode_request) pair of one router
    ───────────────────────────────────────────

         allocation leaves both fields zero, which is OFF
                           │
                           ▼
    ┌────────────────────────────┐                             ┌────────────────────────────┐
    │          settled           │    ② another mode asked     │         requested          │
    │    mode == mode_request    │ ──────────────────────────► │    mode != mode_request    │
    │                            │    ④ off, a mode asked      │                            │
    │                            │ ──────────────────────────► │                            │
    │                            │    ② running mode asked     │                            │
    │                            │ ◄────────────────────────── │                            │
    │                            │    ③ transition returns 0   │                            │
    │                            │ ◄────────────────────────── │                            │
    │                            │    ④ off, OFF asked         │                            │
    │                            │ ◄────────────────────────── │                            │
    └────────────────────────────┘                             └────────────────────────────┘
       ▲             ▲ │                                             ▲ │
       │             └─┘ ② same or refused, ③ no change,             └─┘ ② another, same or refused,
       │                 ④ already off                                   ③ fails, ④ off with a mode asked
       ① read back from the registers on add and on resume

    ① tmu_mode_init            tmu.c:395   mode read back from the registers, then mode_request ← mode
    ② tb_switch_tmu_configure  tmu.c:1068  mode_request ← the asked mode, when it differs from the old request
    ③ tb_switch_tmu_enable     tmu.c:1013  mode ← mode_request, once the transition has returned 0
    ④ tb_switch_tmu_disable    tmu.c:620   mode ← TB_SWITCH_TMU_MODE_OFF, once the off writes have succeeded
    OFF is TB_SWITCH_TMU_MODE_OFF, value 0; "a mode asked" means mode_request is not OFF
```

### Lane-bonding registers

Each callout trunk needs a downward port at the register border.

```
    USB4 port word at port->cap_usb4 + 0x12 (USB4 routers)
    ──────────────────────────────────────────────────────

    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    CS_18 │·│·│·│·│·│·│·│T│·│C│·│·│·│W│W│W│·│·│·│·│·│C│T│B│·│·│·│·│·│·│·│·│
          └─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┘
                         │   │       │ │ │           │ │ │
                    TIP ─┘   │       │ │ │           │ │ │
                        CSA ─┘       │ │ │           │ │ │
                              WOU4S ─┘ │ │           │ │ │
                                 WODS ─┘ │           │ │ │
                                   WOCS ─┘           │ │ │
                                                CPS ─┘ │ │
                                                  TCM ─┘ │
                                                     BE ─┘

    Link controller word at the port's LC window + 0x8d (older routers)
    ───────────────────────────────────────────────────────────────────

    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    ATTR  │·│·│·│·│·│·│·│·│·│·│·│·│·│·│·│·│·│·│·│B│·│·│·│·│·│·│·│·│·│·│·│·│
          └─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┘
                                                 │
                                             BE ─┘

    BE (CS_18, bit 8) = PORT_CS_18_BE (set when lane bonding with the upstream router is possible)
    BE (ATTR, bit 12) = TB_LC_PORT_ATTR_BE (the same answer on a router below USB4, generation 2 or later)
    TIP, CSA = PORT_CS_18_TIP, PORT_CS_18_CSA (asymmetric link); CPS = PORT_CS_18_CPS (CLx support)
    TCM = PORT_CS_18_TCM; WOCS, WODS, WOU4S = PORT_CS_18_WOCS, _WODS, _WOU4S (wake reasons)
    · = no macro in tb_regs.h for this word
```

### Router and port devices

The first box has its right wall at column 68, but its corners at column 67.

```
    A router, its USB4 port devices, and what attaches to each
    ──────────────────────────────────────────────────────────

    struct tb_switch                                sysfs name 0-1
    ┌─────────────────────────────────────────────────────────────┐
    │  ports[]   a lane 0 adapter carrying cap_usb4 earns one      │
    │            device, and port->usb4 keeps the handle back      │
    └──────────────────────────────┬──────────────────────────────┘
                                   │ device parent of
                  ┌────────────────┴───────────────┐
                  ▼                                ▼
    ┌───────────────────────────┐    ┌───────────────────────────┐
    │ usb4_port1                │    │ usb4_port2                │
    │   port ──▶ lane adapter 1 │    │   port ──▶ lane adapter 3 │
    │   can_offline   true      │    │   can_offline   false     │
    │   offline       false     │    │   offline       false     │
    ├───────────────────────────┤    ├───────────────────────────┤
    │   link   offline  rescan  │    │   link                    │
    │   connector  power/wakeup │    │   power/wakeup            │
    └───────┬───────────────┬───┘    └───────────────────────────┘
            │               │
            │               └──────▶  Type-C connector device,
            │                         holding a usb4_port1 link back
            ▼
    ┌─────────────────────────┐
    │  0-1:1.1      0-1:1.2   │  the on-board retimer children
    └─────────────────────────┘

    Beside each device stands its ACPI companion, the firmware child of
    the router's own node whose _ADR is the adapter number. can_offline
    is set only where that companion carries the retimer _DSM.
```

<!-- kg:expect
only:
- geometry.layout
findings:
- - geometry.layout
  - review
  - 34
  - │   ├───────────────┴──── path_length cells ────────┴───────────────┤           │
- - geometry.layout
  - review
  - 63
  - ①  │ faces the host?     │───────▶ nothing done
- - geometry.layout
  - review
  - 67
  - ②  │ display asking for  │───────▶ a plug event is queued
- - geometry.layout
  - review
  - 72
  - ③  │ not a lane adapter? │───────▶ nothing done
- - geometry.layout
  - review
  - 76
  - ④  │ secondary lane?     │───────▶ nothing done
- - geometry.layout
  - review
  - 82
  - ⑤  │ link not up?        │───────▶ exit under it
- - geometry.layout
  - review
  - 86
  - ⑥  │ adapter already     │───────▶ nothing done
- - geometry.layout
  - review
  - 91
  - ⑦  │ router answers?     │───────▶ retimers exposed, maybe
- - geometry.layout
  - review
  - 95
  - ⑧  │ router configured?  │───────▶ router object released
- - geometry.layout
  - review
  - 99
  - ⑨  │ router registered?  │───────▶ router object released
- - geometry.layout
  - review
  - 149
  - └────────────────────────────┘                             └────────────────────────────┘
- - geometry.layout
  - review
  - 174
  - └─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┘
- - geometry.layout
  - review
  - 192
  - └─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┘
- - geometry.layout
  - review
  - 213
  - │  ports[]   a lane 0 adapter carrying cap_usb4 earns one      │
- - geometry.layout
  - review
  - 214
  - │            device, and port->usb4 keeps the handle back      │
- - geometry.layout
  - review
  - 215
  - └──────────────────────────────┬──────────────────────────────┘
incomplete: []
-->
