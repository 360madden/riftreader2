# Primary cast-duration factories — November7,2026

Exact-build static findings for retained PE
`artifacts/lab2-rift-exe-20261027-01-copy.exe`, SHA256
`1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`.
No native getter, constructor, debugger, memory write or game input was used.

## Useful distinction

The idle ability catalog already captures the input to the common0650 runtime
primary-duration getter. The earlier unobserved tick-snapshot class belongs to
a DIFFERENT input type0653, observed on the generic **Use** definition. Repeating
idle searches for that snapshot class will not resolve ordinary0650 spell timing.

Factory536310 dispatches the input descriptor's name through the initialized
registry at module33624B8. Registration and lookup share name/hash/lookup4EF440.

| Input | Factory and runtime getter | Passive interpretation |
| --- | --- | --- |
|0650|name`!f0260399` →536150 →wrapper VT26AA020, slot8 method537270|Type-checks saved reference+10; reads the SAME input signed DWORD+20 and multiplies float32 by0.001. Prospective unadjusted primary duration.|
|0759|name`!cfc7ae00` →535D00 →wrapper VT26AA220, slot8 method5370F0|Returns constant2.0 seconds. Constructor side effects are unnecessary and must not be invoked. No such primary input was found in the retained two catalogs.|
|0653|name`!2b786c80` →5361C0 →5355E0 →wrapper VT26AA0E0, slot8 method09D680|Returns constructor-snapshot float+18, initially-1; context tick source and adjustment can replace it. Later idle source values cannot reconstruct that instance.|

Observed0653 input fingerprint: object VT2D26430, slot40 getter234BD60,
initialized descriptor35B47D0/VT2D2E438, descriptor slot8 method23686D0
(type0653), slot10 method23690B0 (factory name). Both catalogs contain exactly
one such primary: **Use**, full ID candidate`A0000002B72E024A4`, key43,
raw filter0 and empty cost vector. This identifies an idle definition, not an
active Use instance or public castbar value.

## Selection and qualification limits

Active child construction first selects the first reference in type0056 context
vector+48/+50 when nonempty. Only when empty does it choose the definition0051
vector+5F0. Context key is DWORD+30. A missing active context does not prove its
future vector empty. Runtime child stores definition+10, context+18 and primary
duration wrapper+20. The secondary+28 wrapper has separate selection rules.

Ability.Detail castingTime producer49D230 separately requires a single primary
entry and can apply player modifier5A8E00 mode1/truncation. The0650 primary
runtime getter instead reads its chosen input directly. These values must not
be silently equated. Existing21 Lab1/23 Lab2 typed0650 inputs support conditional
prospective durations; examples: Vile Spores2s, Natural Healing2.5s, Icicle1.5s,
Ascended Resurrection8s, Shadow Fire2s, Call of the Ascended20s. These are named
definition candidates, not current cast state, availability or adjusted API values.

Catalog receipts:

- Lab1`artifacts/native-ability-catalog-20261107/runs/lab1/365bbf7420e24dea8fcd37181d08b7d9/catalog-summary.json`,
  SHA256`12F4218AA20A6C873BF3EE3B949E71934C0B6D58FC86FE6E4BD0437F90235D9D`.
- Lab2`artifacts/native-ability-catalog-20261107/runs/lab2/af7c85d204dd4aae80a08d46ef9856a1/catalog-summary.json`,
  SHA256`5AB4EEC9C65698FC200C3A973930114D6370EE93EAE44B146C02BB27823D1466`.

Next useful observation binds an actual context/selected input/wrapper under a
fresh identity and existing guards. For0650 capture saved reference/type/+20;
for0653 capture the actual instance+18, preserving-1. An independent castbar
comparison and changed-state/restart/freshness work remain separate. Detailed
retained instruction trace:`artifacts/discovery-20261107-cast/cast-duration-next-discriminator.md`.

## Primary live wrapper decoder - 2026-11-07 16:35 Eastern

The world-cast reader now decodes primary runtime wrapper26AA020/slot8=537270,
requiring its +8 backlink to the selected child and following the actual saved
input at +10. It verifies the existing typed0650 profile and reports signedDWORD
input+20 milliseconds and float32 seconds. These fields join consumed-byte
rereads; nonpositive values retain raw evidence with a separate status. The
0653 path and fallback branch remain unchanged. Sixteen focused cases passed.
This closes an offline reader gap; no positive live cast or API/changed-state,
freshness or restart qualification has been observed. Idle definition inputs do
not fill missing live cast values. Evidence note:
`artifacts/discovery-20261107-cast/live-cast-duration-gap.md`.
