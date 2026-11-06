# Configurable XYZ validation Courier

`ValidationCourier.cs` is the source-owned successor to the corrected October 25
trial Courier. It preserves that Courier's ordered buttons, exact process/build
checks, bounded reader commands, absence and stale-epoch rejection, no-overwrite
evidence package, and fixed claim/upload protocol endpoints. It does not exit or
launch RIFT, send game input, recover offsets, or operate VMware.

Use `scripts/prepare_xyz_courier.py` to compile it from a previously verified
`xyz-deployment-bundle/1`. Do not compile an edited copy ad hoc for guest use.
The generated `courier-config.txt` pins the run ID, reader/profile sizes and
hashes, and exact game build. `--preflight` parses that configuration, validates
the adjacent payloads and supported XYZ profile, then exits without installing,
executing the reader, opening the GUI, or using the network.

The current raw-pointer evidence request is deliberately limited to root RVA
`0x32E0200`, one dereference, an 816-byte terminal window and XYZ offsets
`+0x320/+0x324/+0x328`. Preflight rejects a profile with another recipe rather
than combining it with those fixed raw-capture constants.

An accepted prepared bundle has no `INCOMPLETE.txt` and has a valid
`courier-manifest.json`. Preparation alone is not deployment or live validation.
