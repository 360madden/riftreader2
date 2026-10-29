# VMware lab snapshots

`scripts/lab_snapshot.py` lists snapshots and creates a named, memory-inclusive
snapshot for either configured lab. It uses VMware's `vmcli` through a private
Windows pseudoconsole, supplies the VM-specific cached encryption credential,
and confirms creation with an independent `vmrun` snapshot listing. It returns
JSON status and an exit code. No credential is printed or placed in the child
command line. The guest configuration remains in ignored `.local/lab-codex.json`.

Install the pinned helper for the Python interpreter used by the script:

```powershell
python -m pip install --target .local\tools\snapshot-python pywinpty==3.1.2
```

```powershell
python scripts/lab_snapshot.py list --lab lab1
python scripts/lab_snapshot.py take --lab lab1 --name my-unique-snapshot
python scripts/lab_snapshot.py list --lab lab2
```

Create one snapshot at a time and check available disk space first. This tool
does not delete or revert snapshots. If a creation times out or reports failure,
inspect the snapshot list before trying again: the outcome may be uncertain.
The snapshots capture powered-on memory as well as disks, so a later revert can
restore stale network sessions; revalidate Codex and game identities afterward.
Snapshots consume additional disk space over time and are not independent
backups. Reversion would discard subsequent guest changes; it is a separate
decision from taking a snapshot.

On 2026-10-29 the tool created and independently listed
`baseline-codex-connected-lab1-20261029` and
`baseline-codex-connected-lab2-20261029`. The existing Lab-2
`pre-tools-20261026` snapshot was retained. Both were made while the VMs were
running, using the memory option; restoring them has not been tested.
