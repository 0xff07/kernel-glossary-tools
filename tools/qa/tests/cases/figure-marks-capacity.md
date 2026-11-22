# A family holds only what its capacity allows

## DETAILS

### The mask is recorded

The two assignments keep the records consistent.

```c
/* drivers/thunderbolt/tb.c:74 */
	port->clx = clx;
	port->remote->clx = clx;
```

The next figure shows the records.

```
    ┌────────────┐
    │ «1» mask   │
    │ «2» mask   │
    │ «3» mask   │
    │ «4» mask   │
    │ «5» mask   │
    │ «6» mask   │
    │ «7» mask   │
    │ «8» mask   │
    │ «9» mask   │
    │ «10» mask  │
    │ «11» mask  │
    └────────────┘

    «1» tb_port_clx_enable tb.c:74 records the near mask
    «2» tb_port_clx_enable tb.c:74 records the near mask
    «3» tb_port_clx_enable tb.c:74 records the near mask
    «4» tb_port_clx_enable tb.c:74 records the near mask
    «5» tb_port_clx_enable tb.c:74 records the near mask
    «6» tb_port_clx_enable tb.c:74 records the near mask
    «7» tb_port_clx_enable tb.c:74 records the near mask
    «8» tb_port_clx_enable tb.c:74 records the near mask
    «9» tb_port_clx_enable tb.c:74 records the near mask
    «10» tb_port_clx_enable tb.c:74 records the near mask
    «11» tb_port_clx_enable tb.c:74 records the near mask
```

Mark «1» lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask. Mark «2» lets tb_port_clx_enable() record the mask. Mark «3» lets tb_port_clx_enable() record the mask. Mark «4» lets tb_port_clx_enable() record the mask. Mark «5» lets tb_port_clx_enable() record the mask. Mark «6» lets tb_port_clx_enable() record the mask. Mark «7» lets tb_port_clx_enable() record the mask. Mark «8» lets tb_port_clx_enable() record the mask. Mark «9» lets tb_port_clx_enable() record the mask. Mark «10» lets tb_port_clx_enable() record the mask. Mark «11» lets tb_port_clx_enable() record the mask.

The next figure shows the records.

```
    ┌────────────┐
    │ «A» mask   │
    │ «B» mask   │
    │ «C» mask   │
    │ «D» mask   │
    │ «E» mask   │
    │ «F» mask   │
    │ «G» mask   │
    │ «H» mask   │
    │ «I» mask   │
    │ «J» mask   │
    │ «K» mask   │
    │ «L» mask   │
    │ «M» mask   │
    │ «N» mask   │
    │ «O» mask   │
    │ «P» mask   │
    │ «Q» mask   │
    │ «R» mask   │
    │ «S» mask   │
    │ «T» mask   │
    │ «U» mask   │
    │ «V» mask   │
    │ «W» mask   │
    │ «X» mask   │
    │ «Y» mask   │
    │ «Z» mask   │
    └────────────┘

    «A» tb_port_clx_enable tb.c:74 records the near mask
    «B» tb_port_clx_enable tb.c:74 records the near mask
    «C» tb_port_clx_enable tb.c:74 records the near mask
    «D» tb_port_clx_enable tb.c:74 records the near mask
    «E» tb_port_clx_enable tb.c:74 records the near mask
    «F» tb_port_clx_enable tb.c:74 records the near mask
    «G» tb_port_clx_enable tb.c:74 records the near mask
    «H» tb_port_clx_enable tb.c:74 records the near mask
    «I» tb_port_clx_enable tb.c:74 records the near mask
    «J» tb_port_clx_enable tb.c:74 records the near mask
    «K» tb_port_clx_enable tb.c:74 records the near mask
    «L» tb_port_clx_enable tb.c:74 records the near mask
    «M» tb_port_clx_enable tb.c:74 records the near mask
    «N» tb_port_clx_enable tb.c:74 records the near mask
    «O» tb_port_clx_enable tb.c:74 records the near mask
    «P» tb_port_clx_enable tb.c:74 records the near mask
    «Q» tb_port_clx_enable tb.c:74 records the near mask
    «R» tb_port_clx_enable tb.c:74 records the near mask
    «S» tb_port_clx_enable tb.c:74 records the near mask
    «T» tb_port_clx_enable tb.c:74 records the near mask
    «U» tb_port_clx_enable tb.c:74 records the near mask
    «V» tb_port_clx_enable tb.c:74 records the near mask
    «W» tb_port_clx_enable tb.c:74 records the near mask
    «X» tb_port_clx_enable tb.c:74 records the near mask
    «Y» tb_port_clx_enable tb.c:74 records the near mask
    «Z» tb_port_clx_enable tb.c:74 records the near mask
```

Mark «A» lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask. Mark «B» lets tb_port_clx_enable() record the mask. Mark «C» lets tb_port_clx_enable() record the mask. Mark «D» lets tb_port_clx_enable() record the mask. Mark «E» lets tb_port_clx_enable() record the mask. Mark «F» lets tb_port_clx_enable() record the mask. Mark «G» lets tb_port_clx_enable() record the mask. Mark «H» lets tb_port_clx_enable() record the mask. Mark «I» lets tb_port_clx_enable() record the mask. Mark «J» lets tb_port_clx_enable() record the mask. Mark «K» lets tb_port_clx_enable() record the mask. Mark «L» lets tb_port_clx_enable() record the mask. Mark «M» lets tb_port_clx_enable() record the mask. Mark «N» lets tb_port_clx_enable() record the mask. Mark «O» lets tb_port_clx_enable() record the mask. Mark «P» lets tb_port_clx_enable() record the mask. Mark «Q» lets tb_port_clx_enable() record the mask. Mark «R» lets tb_port_clx_enable() record the mask. Mark «S» lets tb_port_clx_enable() record the mask. Mark «T» lets tb_port_clx_enable() record the mask. Mark «U» lets tb_port_clx_enable() record the mask. Mark «V» lets tb_port_clx_enable() record the mask. Mark «W» lets tb_port_clx_enable() record the mask. Mark «X» lets tb_port_clx_enable() record the mask. Mark «Y» lets tb_port_clx_enable() record the mask. Mark «Z» lets tb_port_clx_enable() record the mask.

The next figure shows the records.

```
    ┌────────────┐
    │ @1 mask    │
    │ @2 mask    │
    │ @3 mask    │
    │ @4 mask    │
    │ @5 mask    │
    │ @6 mask    │
    │ @7 mask    │
    │ @8 mask    │
    │ @9 mask    │
    │ @10 mask   │
    │ @11 mask   │
    │ @12 mask   │
    │ @13 mask   │
    │ @14 mask   │
    │ @15 mask   │
    │ @16 mask   │
    │ @17 mask   │
    │ @18 mask   │
    │ @19 mask   │
    │ @20 mask   │
    │ @21 mask   │
    │ @22 mask   │
    │ @23 mask   │
    │ @24 mask   │
    │ @25 mask   │
    │ @26 mask   │
    │ @27 mask   │
    └────────────┘

    @1 tb_port_clx_enable tb.c:74 records the near mask
    @2 tb_port_clx_enable tb.c:74 records the near mask
    @3 tb_port_clx_enable tb.c:74 records the near mask
    @4 tb_port_clx_enable tb.c:74 records the near mask
    @5 tb_port_clx_enable tb.c:74 records the near mask
    @6 tb_port_clx_enable tb.c:74 records the near mask
    @7 tb_port_clx_enable tb.c:74 records the near mask
    @8 tb_port_clx_enable tb.c:74 records the near mask
    @9 tb_port_clx_enable tb.c:74 records the near mask
    @10 tb_port_clx_enable tb.c:74 records the near mask
    @11 tb_port_clx_enable tb.c:74 records the near mask
    @12 tb_port_clx_enable tb.c:74 records the near mask
    @13 tb_port_clx_enable tb.c:74 records the near mask
    @14 tb_port_clx_enable tb.c:74 records the near mask
    @15 tb_port_clx_enable tb.c:74 records the near mask
    @16 tb_port_clx_enable tb.c:74 records the near mask
    @17 tb_port_clx_enable tb.c:74 records the near mask
    @18 tb_port_clx_enable tb.c:74 records the near mask
    @19 tb_port_clx_enable tb.c:74 records the near mask
    @20 tb_port_clx_enable tb.c:74 records the near mask
    @21 tb_port_clx_enable tb.c:74 records the near mask
    @22 tb_port_clx_enable tb.c:74 records the near mask
    @23 tb_port_clx_enable tb.c:74 records the near mask
    @24 tb_port_clx_enable tb.c:74 records the near mask
    @25 tb_port_clx_enable tb.c:74 records the near mask
    @26 tb_port_clx_enable tb.c:74 records the near mask
    @27 tb_port_clx_enable tb.c:74 records the near mask
```

Mark @1 lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask. Mark @2 lets tb_port_clx_enable() record the mask. Mark @3 lets tb_port_clx_enable() record the mask. Mark @4 lets tb_port_clx_enable() record the mask. Mark @5 lets tb_port_clx_enable() record the mask. Mark @6 lets tb_port_clx_enable() record the mask. Mark @7 lets tb_port_clx_enable() record the mask. Mark @8 lets tb_port_clx_enable() record the mask. Mark @9 lets tb_port_clx_enable() record the mask. Mark @10 lets tb_port_clx_enable() record the mask. Mark @11 lets tb_port_clx_enable() record the mask. Mark @12 lets tb_port_clx_enable() record the mask. Mark @13 lets tb_port_clx_enable() record the mask. Mark @14 lets tb_port_clx_enable() record the mask. Mark @15 lets tb_port_clx_enable() record the mask. Mark @16 lets tb_port_clx_enable() record the mask. Mark @17 lets tb_port_clx_enable() record the mask. Mark @18 lets tb_port_clx_enable() record the mask. Mark @19 lets tb_port_clx_enable() record the mask. Mark @20 lets tb_port_clx_enable() record the mask. Mark @21 lets tb_port_clx_enable() record the mask. Mark @22 lets tb_port_clx_enable() record the mask. Mark @23 lets tb_port_clx_enable() record the mask. Mark @24 lets tb_port_clx_enable() record the mask. Mark @25 lets tb_port_clx_enable() record the mask. Mark @26 lets tb_port_clx_enable() record the mask. Mark @27 lets tb_port_clx_enable() record the mask.

The next figure shows the records.

```
    ┌────────────┐
    │ @A mask    │
    │ @B mask    │
    │ @C mask    │
    │ @D mask    │
    │ @E mask    │
    │ @F mask    │
    │ @G mask    │
    │ @H mask    │
    │ @I mask    │
    │ @J mask    │
    │ @K mask    │
    │ @L mask    │
    │ @M mask    │
    │ @N mask    │
    │ @O mask    │
    │ @P mask    │
    │ @Q mask    │
    │ @R mask    │
    │ @S mask    │
    │ @T mask    │
    │ @U mask    │
    │ @V mask    │
    │ @W mask    │
    │ @X mask    │
    │ @Y mask    │
    │ @Z mask    │
    └────────────┘

    @A tb_port_clx_enable tb.c:74 records the near mask
    @B tb_port_clx_enable tb.c:74 records the near mask
    @C tb_port_clx_enable tb.c:74 records the near mask
    @D tb_port_clx_enable tb.c:74 records the near mask
    @E tb_port_clx_enable tb.c:74 records the near mask
    @F tb_port_clx_enable tb.c:74 records the near mask
    @G tb_port_clx_enable tb.c:74 records the near mask
    @H tb_port_clx_enable tb.c:74 records the near mask
    @I tb_port_clx_enable tb.c:74 records the near mask
    @J tb_port_clx_enable tb.c:74 records the near mask
    @K tb_port_clx_enable tb.c:74 records the near mask
    @L tb_port_clx_enable tb.c:74 records the near mask
    @M tb_port_clx_enable tb.c:74 records the near mask
    @N tb_port_clx_enable tb.c:74 records the near mask
    @O tb_port_clx_enable tb.c:74 records the near mask
    @P tb_port_clx_enable tb.c:74 records the near mask
    @Q tb_port_clx_enable tb.c:74 records the near mask
    @R tb_port_clx_enable tb.c:74 records the near mask
    @S tb_port_clx_enable tb.c:74 records the near mask
    @T tb_port_clx_enable tb.c:74 records the near mask
    @U tb_port_clx_enable tb.c:74 records the near mask
    @V tb_port_clx_enable tb.c:74 records the near mask
    @W tb_port_clx_enable tb.c:74 records the near mask
    @X tb_port_clx_enable tb.c:74 records the near mask
    @Y tb_port_clx_enable tb.c:74 records the near mask
    @Z tb_port_clx_enable tb.c:74 records the near mask
```

Mark @A lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask. Mark @B lets tb_port_clx_enable() record the mask. Mark @C lets tb_port_clx_enable() record the mask. Mark @D lets tb_port_clx_enable() record the mask. Mark @E lets tb_port_clx_enable() record the mask. Mark @F lets tb_port_clx_enable() record the mask. Mark @G lets tb_port_clx_enable() record the mask. Mark @H lets tb_port_clx_enable() record the mask. Mark @I lets tb_port_clx_enable() record the mask. Mark @J lets tb_port_clx_enable() record the mask. Mark @K lets tb_port_clx_enable() record the mask. Mark @L lets tb_port_clx_enable() record the mask. Mark @M lets tb_port_clx_enable() record the mask. Mark @N lets tb_port_clx_enable() record the mask. Mark @O lets tb_port_clx_enable() record the mask. Mark @P lets tb_port_clx_enable() record the mask. Mark @Q lets tb_port_clx_enable() record the mask. Mark @R lets tb_port_clx_enable() record the mask. Mark @S lets tb_port_clx_enable() record the mask. Mark @T lets tb_port_clx_enable() record the mask. Mark @U lets tb_port_clx_enable() record the mask. Mark @V lets tb_port_clx_enable() record the mask. Mark @W lets tb_port_clx_enable() record the mask. Mark @X lets tb_port_clx_enable() record the mask. Mark @Y lets tb_port_clx_enable() record the mask. Mark @Z lets tb_port_clx_enable() record the mask.

The next figure shows the records.

```
    ┌────────────┐
    │ ① mask     │
    │ ② mask     │
    │ ③ mask     │
    │ ④ mask     │
    │ ⑤ mask     │
    │ ⑥ mask     │
    │ ⑦ mask     │
    │ ⑧ mask     │
    │ ⑨ mask     │
    │ ⑩ mask     │
    └────────────┘

    ① tb_port_clx_enable tb.c:74 records the near mask
    ② tb_port_clx_enable tb.c:74 records the near mask
    ③ tb_port_clx_enable tb.c:74 records the near mask
    ④ tb_port_clx_enable tb.c:74 records the near mask
    ⑤ tb_port_clx_enable tb.c:74 records the near mask
    ⑥ tb_port_clx_enable tb.c:74 records the near mask
    ⑦ tb_port_clx_enable tb.c:74 records the near mask
    ⑧ tb_port_clx_enable tb.c:74 records the near mask
    ⑨ tb_port_clx_enable tb.c:74 records the near mask
    ⑩ tb_port_clx_enable tb.c:74 records the near mask
```

Mark ① lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask. Mark ② lets tb_port_clx_enable() record the mask. Mark ③ lets tb_port_clx_enable() record the mask. Mark ④ lets tb_port_clx_enable() record the mask. Mark ⑤ lets tb_port_clx_enable() record the mask. Mark ⑥ lets tb_port_clx_enable() record the mask. Mark ⑦ lets tb_port_clx_enable() record the mask. Mark ⑧ lets tb_port_clx_enable() record the mask. Mark ⑨ lets tb_port_clx_enable() record the mask. Mark ⑩ lets tb_port_clx_enable() record the mask.

The next figure shows the records.

```
    ┌────────────┐
    │ ➊ mask     │
    │ ➋ mask     │
    │ ➌ mask     │
    │ ➍ mask     │
    │ ➎ mask     │
    │ ➏ mask     │
    │ ➐ mask     │
    │ ➑ mask     │
    │ ➒ mask     │
    │ ➓ mask     │
    └────────────┘

    ➊ tb_port_clx_enable tb.c:74 records the near mask
    ➋ tb_port_clx_enable tb.c:74 records the near mask
    ➌ tb_port_clx_enable tb.c:74 records the near mask
    ➍ tb_port_clx_enable tb.c:74 records the near mask
    ➎ tb_port_clx_enable tb.c:74 records the near mask
    ➏ tb_port_clx_enable tb.c:74 records the near mask
    ➐ tb_port_clx_enable tb.c:74 records the near mask
    ➑ tb_port_clx_enable tb.c:74 records the near mask
    ➒ tb_port_clx_enable tb.c:74 records the near mask
    ➓ tb_port_clx_enable tb.c:74 records the near mask
```

Mark ➊ lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask. Mark ➋ lets tb_port_clx_enable() record the mask. Mark ➌ lets tb_port_clx_enable() record the mask. Mark ➍ lets tb_port_clx_enable() record the mask. Mark ➎ lets tb_port_clx_enable() record the mask. Mark ➏ lets tb_port_clx_enable() record the mask. Mark ➐ lets tb_port_clx_enable() record the mask. Mark ➑ lets tb_port_clx_enable() record the mask. Mark ➒ lets tb_port_clx_enable() record the mask. Mark ➓ lets tb_port_clx_enable() record the mask.

### The mask is recorded again

The next figure shows the records.

```
    ┌────────────┐
    │ «1» mask   │
    │ «2» mask   │
    │ «3» mask   │
    │ «4» mask   │
    │ «5» mask   │
    │ «6» mask   │
    │ «7» mask   │
    │ «8» mask   │
    │ «9» mask   │
    │ «10» mask  │
    │ «11» mask  │
    │ «12» mask  │
    │ «13» mask  │
    │ «14» mask  │
    │ «15» mask  │
    │ «16» mask  │
    │ «17» mask  │
    │ «18» mask  │
    │ «19» mask  │
    │ «20» mask  │
    │ «21» mask  │
    │ «22» mask  │
    │ «23» mask  │
    │ «24» mask  │
    │ «25» mask  │
    │ «26» mask  │
    │ «27» mask  │
    └────────────┘

    «1» tb_port_clx_enable tb.c:74 records the near mask
    «2» tb_port_clx_enable tb.c:74 records the near mask
    «3» tb_port_clx_enable tb.c:74 records the near mask
    «4» tb_port_clx_enable tb.c:74 records the near mask
    «5» tb_port_clx_enable tb.c:74 records the near mask
    «6» tb_port_clx_enable tb.c:74 records the near mask
    «7» tb_port_clx_enable tb.c:74 records the near mask
    «8» tb_port_clx_enable tb.c:74 records the near mask
    «9» tb_port_clx_enable tb.c:74 records the near mask
    «10» tb_port_clx_enable tb.c:74 records the near mask
    «11» tb_port_clx_enable tb.c:74 records the near mask
    «12» tb_port_clx_enable tb.c:74 records the near mask
    «13» tb_port_clx_enable tb.c:74 records the near mask
    «14» tb_port_clx_enable tb.c:74 records the near mask
    «15» tb_port_clx_enable tb.c:74 records the near mask
    «16» tb_port_clx_enable tb.c:74 records the near mask
    «17» tb_port_clx_enable tb.c:74 records the near mask
    «18» tb_port_clx_enable tb.c:74 records the near mask
    «19» tb_port_clx_enable tb.c:74 records the near mask
    «20» tb_port_clx_enable tb.c:74 records the near mask
    «21» tb_port_clx_enable tb.c:74 records the near mask
    «22» tb_port_clx_enable tb.c:74 records the near mask
    «23» tb_port_clx_enable tb.c:74 records the near mask
    «24» tb_port_clx_enable tb.c:74 records the near mask
    «25» tb_port_clx_enable tb.c:74 records the near mask
    «26» tb_port_clx_enable tb.c:74 records the near mask
    «27» tb_port_clx_enable tb.c:74 records the near mask
```

Mark «1» lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask. Mark «2» lets tb_port_clx_enable() record the mask. Mark «3» lets tb_port_clx_enable() record the mask. Mark «4» lets tb_port_clx_enable() record the mask. Mark «5» lets tb_port_clx_enable() record the mask. Mark «6» lets tb_port_clx_enable() record the mask. Mark «7» lets tb_port_clx_enable() record the mask. Mark «8» lets tb_port_clx_enable() record the mask. Mark «9» lets tb_port_clx_enable() record the mask. Mark «10» lets tb_port_clx_enable() record the mask. Mark «11» lets tb_port_clx_enable() record the mask. Mark «12» lets tb_port_clx_enable() record the mask. Mark «13» lets tb_port_clx_enable() record the mask. Mark «14» lets tb_port_clx_enable() record the mask. Mark «15» lets tb_port_clx_enable() record the mask. Mark «16» lets tb_port_clx_enable() record the mask. Mark «17» lets tb_port_clx_enable() record the mask. Mark «18» lets tb_port_clx_enable() record the mask. Mark «19» lets tb_port_clx_enable() record the mask. Mark «20» lets tb_port_clx_enable() record the mask. Mark «21» lets tb_port_clx_enable() record the mask. Mark «22» lets tb_port_clx_enable() record the mask. Mark «23» lets tb_port_clx_enable() record the mask. Mark «24» lets tb_port_clx_enable() record the mask. Mark «25» lets tb_port_clx_enable() record the mask. Mark «26» lets tb_port_clx_enable() record the mask. Mark «27» lets tb_port_clx_enable() record the mask.

### The mask is recorded a third time

The next figure shows the records.

```
    ┌────────────┐
    │ @1 mask    │
    │ @2 mask    │
    │ @3 mask    │
    │ @4 mask    │
    │ @5 mask    │
    │ @6 mask    │
    │ @7 mask    │
    │ @8 mask    │
    │ @9 mask    │
    │ @10 mask   │
    │ @11 mask   │
    │ @12 mask   │
    │ @13 mask   │
    │ @14 mask   │
    │ @15 mask   │
    │ @16 mask   │
    │ @17 mask   │
    │ @18 mask   │
    │ @19 mask   │
    │ @20 mask   │
    │ @21 mask   │
    │ @22 mask   │
    │ @23 mask   │
    │ @24 mask   │
    │ @25 mask   │
    │ @26 mask   │
    │ @27 mask   │
    └────────────┘

    @1 tb_port_clx_enable tb.c:74 records the near mask
    @2 tb_port_clx_enable tb.c:74 records the near mask
    @3 tb_port_clx_enable tb.c:74 records the near mask
    @4 tb_port_clx_enable tb.c:74 records the near mask
    @5 tb_port_clx_enable tb.c:74 records the near mask
    @6 tb_port_clx_enable tb.c:74 records the near mask
    @7 tb_port_clx_enable tb.c:74 records the near mask
    @8 tb_port_clx_enable tb.c:74 records the near mask
    @9 tb_port_clx_enable tb.c:74 records the near mask
    @10 tb_port_clx_enable tb.c:74 records the near mask
    @11 tb_port_clx_enable tb.c:74 records the near mask
    @12 tb_port_clx_enable tb.c:74 records the near mask
    @13 tb_port_clx_enable tb.c:74 records the near mask
    @14 tb_port_clx_enable tb.c:74 records the near mask
    @15 tb_port_clx_enable tb.c:74 records the near mask
    @16 tb_port_clx_enable tb.c:74 records the near mask
    @17 tb_port_clx_enable tb.c:74 records the near mask
    @18 tb_port_clx_enable tb.c:74 records the near mask
    @19 tb_port_clx_enable tb.c:74 records the near mask
    @20 tb_port_clx_enable tb.c:74 records the near mask
    @21 tb_port_clx_enable tb.c:74 records the near mask
    @22 tb_port_clx_enable tb.c:74 records the near mask
    @23 tb_port_clx_enable tb.c:74 records the near mask
    @24 tb_port_clx_enable tb.c:74 records the near mask
    @25 tb_port_clx_enable tb.c:74 records the near mask
    @26 tb_port_clx_enable tb.c:74 records the near mask
    @27 tb_port_clx_enable tb.c:74 records the near mask
```

Mark @1 lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask. Mark @2 lets tb_port_clx_enable() record the mask. Mark @3 lets tb_port_clx_enable() record the mask. Mark @4 lets tb_port_clx_enable() record the mask. Mark @5 lets tb_port_clx_enable() record the mask. Mark @6 lets tb_port_clx_enable() record the mask. Mark @7 lets tb_port_clx_enable() record the mask. Mark @8 lets tb_port_clx_enable() record the mask. Mark @9 lets tb_port_clx_enable() record the mask. Mark @10 lets tb_port_clx_enable() record the mask. Mark @11 lets tb_port_clx_enable() record the mask. Mark @12 lets tb_port_clx_enable() record the mask. Mark @13 lets tb_port_clx_enable() record the mask. Mark @14 lets tb_port_clx_enable() record the mask. Mark @15 lets tb_port_clx_enable() record the mask. Mark @16 lets tb_port_clx_enable() record the mask. Mark @17 lets tb_port_clx_enable() record the mask. Mark @18 lets tb_port_clx_enable() record the mask. Mark @19 lets tb_port_clx_enable() record the mask. Mark @20 lets tb_port_clx_enable() record the mask. Mark @21 lets tb_port_clx_enable() record the mask. Mark @22 lets tb_port_clx_enable() record the mask. Mark @23 lets tb_port_clx_enable() record the mask. Mark @24 lets tb_port_clx_enable() record the mask. Mark @25 lets tb_port_clx_enable() record the mask. Mark @26 lets tb_port_clx_enable() record the mask. Mark @27 lets tb_port_clx_enable() record the mask.

### The mask is recorded a fourth time

The next figure shows the records.

```
    ┌────────────┐
    │ @A mask    │
    └────────────┘

    @A tb_port_clx_enable tb.c:74 records the near mask
```

Mark @A lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask.

### The mask is recorded a fifth time

The next figure shows the records.

```
    ┌────────────┐
    │ ① mask     │
    └────────────┘

    ① tb_port_clx_enable tb.c:74 records the near mask
```

Mark ① lets [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) record the mask.

<!-- kg:expect
only:
- drawing.marks
- drawing.legend
- drawing.walk
- geometry.layout
- geometry.unicode
findings: []
incomplete: []
-->
