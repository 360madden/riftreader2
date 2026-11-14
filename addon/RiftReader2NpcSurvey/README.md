# Read-only NPC survey

The standalone addon consists of `RiftAddon.toc` and `survey.lua`.
If the running client does not discover the new addon after refresh, the
existing Casting addon can load the same survey module. Back up the exact
installed Casting TOC, copy the survey into that directory as `npc_survey.lua`,
and append `"npc_survey.lua"` to the existing `RunOnStartup` list. Keep one
active copy of the survey. The registered slash owner comes from the loading
addon's metadata. The telemetry identifies its producer as RiftReader2NpcSurvey.

After a UI reload, enter `/rr2survey status` and verify the response is
`unbound`. Bind a fresh nonce with either form.

```text
/rr2survey bind <32 lowercase hex characters> visible
/rr2survey bind <32 lowercase hex characters> <unit-id>,<unit-id>
```

For visible units, the first page is selected by default. Use
`/rr2survey page 2` for the next group of up to twelve IDs. From the RR2
checkout, read a page into a new output directory.

```powershell
python scripts/npc_survey_live.py --expected-host AMD-DESKTOP --physical-pid $riftPid --session-id $nonce --visible-page 1 --output $newOutput
```

For an explicit selection, use `--unit-ids` with the same comma-separated IDs
used at bind. The addon calls Detail for every supplied ID, including those
absent from the specifier tree. The `visibleBefore` and `visibleAfter` fields
report membership in that tree when List succeeds. A visible-page row must
belong to both lists around its detail read. In both modes, the CLI's
`confirmedUnitIds` contain IDs returned by Detail in two advancing frames.
The raw `availability` scalar is retained when present. Missing relation is unknown. Any literal
`rawAttackable` value retains unqualified semantics. Use `/rr2survey clear`
to stop publication. To remove the Casting fallback, restore the backed-up
manifest and remove the added module.

## Physical acceptance, November 14, 2026

On AMD-DESKTOP, fresh nonce-bound physical captures returned an exact Coastal
Stalker instance (`u800000020502E041`, level 14) with API relation `hostile`;
Maris Telluria and a Sanctum Guard returned `friendly`. The map importer keeps
these timestamped instance observations separate from historical Magelo points.
The Stalker's captured point belongs to the adjacent 50-unit context layer,
not the exact Sanctum Watch polygon. Attackability remains unknown.

The bounded native-manager enumeration contained 61 position candidates.
Four explicit surveys queried 35 nonself candidates in/near the Watch polygon;
only the selected guard returned details during those batches. Unavailable is
not evidence of absence or friendliness. A separate selected Stalker capture
returned hostile details. This build therefore supports useful selected or
mouseover NPC reaction captures, not a complete passive nearby-NPC census.
Coastal Chomper and Sea Wart name lookups found no target from the test position.
No movement, attack, cast, or Resume was sent; `/rr2survey clear` was observed at
cleanup. Survey plus physical Waypoints checks passed 20 tests, including STOP
cases. Raw captures remain under ignored `artifacts/watch-api-survey-20261114-*`.

The next useful extension is a bounded local survey over known safe route
checkpoints, collecting newly available exact units and preserving unknown
coverage. Completing that census and proving attackability need separate
observations; neither is implied by this acceptance.
