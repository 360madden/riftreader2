"""Durable offline experiment coordination; this module never sends game input.

A grant is not live authorization. The future trusted control adapter must enforce
its token/epoch/generation at dispatch, and produce real cleanup evidence. All
workers must share one local database, not a database per worktree. No daemon or
automatic experiment replay is provided here. Python 3.12+; standard library only.
"""

from contextlib import contextmanager
import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time


APPLICATION_ID = 0x52523251
SCHEMA_VERSION = 1
AGING_MS = 30_000
MAX_PENDING = 1000
MAX_RESOURCES = 64
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
RESOURCE = re.compile(r"[a-z0-9][a-z0-9:._/-]{0,127}\Z")
TERMINAL = frozenset(("succeeded", "failed", "cancelled", "expired", "stale", "dependency_failed"))


class QueueError(ValueError):
    """A request cannot safely advance; no game action has been attempted."""


def _identifier(value, name, pattern=ID):
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise QueueError(f"invalid {name}")
    return value


def _integer(value, name, lower, upper):
    if type(value) is not int or not lower <= value <= upper:
        raise QueueError(f"{name} must be an integer in [{lower}, {upper}]")
    return value


def _text(value, name, maximum=512):
    if (not isinstance(value, str) or not 1 <= len(value) <= maximum
            or value != value.strip() or any(ord(c) < 32 for c in value)):
        raise QueueError(f"invalid {name}")
    return value


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise QueueError(f"duplicate JSON property: {key}")
        result[key] = value
    return result


class AccessQueue:
    def __init__(self, path, *, create=False, clock=None):
        path = Path(path)
        if not path.is_absolute():
            raise QueueError("database path must be absolute and shared across workers")
        self.path = path.resolve()
        self.clock = clock or (lambda: time.time_ns() // 1_000_000)
        if create:
            # Never reset an existing authority, even an empty or corrupt one.
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
            self._initialize()
        with self._connection() as database:
            self._verify_schema(database)

    @contextmanager
    def _connection(self):
        # mode=rw refuses a missing/deleted database instead of silently creating it.
        database = sqlite3.connect(
            self.path.as_uri() + "?mode=rw", uri=True, timeout=5,
            isolation_level=None, autocommit=sqlite3.LEGACY_TRANSACTION_CONTROL,
        )
        try:
            database.row_factory = sqlite3.Row
            database.execute("PRAGMA foreign_keys=ON")
            database.execute("PRAGMA synchronous=FULL")
            yield database
        finally:
            database.close()

    def _initialize(self):
        statements = (
            "CREATE TABLE metadata (key TEXT PRIMARY KEY, value INTEGER NOT NULL)",
            "INSERT INTO metadata VALUES ('last_ms', 0)",
            """CREATE TABLE requests (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT UNIQUE NOT NULL, specification TEXT NOT NULL,
                state TEXT NOT NULL, created_ms INTEGER NOT NULL,
                token_hash TEXT, lease TEXT, expires_ms INTEGER, deadline_ms INTEGER,
                finish_state TEXT, evidence TEXT NOT NULL DEFAULT '[]')""",
            """CREATE TABLE resources (
                name TEXT PRIMARY KEY, epoch TEXT NOT NULL,
                generation INTEGER NOT NULL DEFAULT 0,
                blocked INTEGER NOT NULL CHECK (blocked IN (0, 1)),
                blocked_since_ms INTEGER NOT NULL, holder TEXT,
                cleanup_receipt TEXT,
                FOREIGN KEY(holder) REFERENCES requests(request_id))""",
            """CREATE TABLE events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp_ms INTEGER NOT NULL, kind TEXT NOT NULL,
                request_id TEXT, detail TEXT NOT NULL)""",
            "CREATE INDEX requests_state ON requests(state, sequence)",
        )
        with self._connection() as database:
            database.execute("BEGIN IMMEDIATE")
            try:
                for statement in statements:
                    database.execute(statement)
                database.execute(f"PRAGMA application_id={APPLICATION_ID}")
                database.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                database.execute("COMMIT")
            except BaseException:
                database.execute("ROLLBACK")
                raise

    @staticmethod
    def _verify_schema(database):
        if (database.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID
                or database.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION):
            raise QueueError("unrecognized queue database; do not reset or recreate it")

    @staticmethod
    def _event(database, now, kind, request_id=None, **detail):
        database.execute("INSERT INTO events(timestamp_ms,kind,request_id,detail) VALUES (?,?,?,?)",
                         (now, kind, request_id, _json(detail)))

    def _quarantine(self, database, now, request_id, outcome, reason):
        database.execute("UPDATE requests SET state='cleanup',finish_state=? WHERE request_id=?",
                         (outcome, request_id))
        database.execute("""UPDATE resources SET blocked=1, blocked_since_ms=?,
                            generation=generation+1, cleanup_receipt=NULL WHERE holder=?""",
                         (now, request_id))
        self._event(database, now, "cleanup-required", request_id, outcome=outcome, reason=reason)

    @contextmanager
    def _transaction(self):
        with self._connection() as database:
            self._verify_schema(database)
            database.execute("BEGIN IMMEDIATE")
            try:
                now = _integer(self.clock(), "clock", 0, 2**63 - 1 - 120000)
                last = database.execute("SELECT value FROM metadata WHERE key='last_ms'").fetchone()[0]
                if now < last:
                    for row in database.execute("SELECT request_id FROM requests WHERE state='active'").fetchall():
                        self._quarantine(database, last, row[0], "expired", "clock-rollback")
                    database.execute("COMMIT")
                    raise QueueError("clock moved backwards; active leases quarantined; wait for clock reconciliation")
                for row in database.execute(
                        "SELECT request_id FROM requests WHERE state='active' AND expires_ms<=?", (now,)).fetchall():
                    self._quarantine(database, now, row[0], "expired", "lease-expired")
                database.execute("UPDATE metadata SET value=? WHERE key='last_ms'", (now,))
                # Rejected caller requests must not roll back expiry maintenance.
                database.execute("SAVEPOINT operation")
                try:
                    yield database, now
                except BaseException:
                    database.execute("ROLLBACK TO operation")
                    database.execute("RELEASE operation")
                    database.execute("COMMIT")
                    raise
                database.execute("RELEASE operation")
                database.execute("COMMIT")
            except BaseException:
                if database.in_transaction:
                    database.execute("ROLLBACK")
                raise

    def register(self, resource, epoch):
        resource = _identifier(resource, "resource", RESOURCE)
        epoch = _identifier(epoch, "epoch")
        with self._transaction() as (database, now):
            row = database.execute("SELECT * FROM resources WHERE name=?", (resource,)).fetchone()
            if row is None:
                if database.execute("SELECT count(*) FROM resources").fetchone()[0] >= MAX_RESOURCES:
                    raise QueueError("resource limit reached")
                database.execute("INSERT INTO resources(name,epoch,blocked,blocked_since_ms) VALUES (?,?,1,?)",
                                 (resource, epoch, now))
                self._event(database, now, "resource-registered", resource=resource, epoch=epoch)
            elif row["epoch"] != epoch:
                if row["holder"]:
                    state = database.execute("SELECT state FROM requests WHERE request_id=?", (row["holder"],)).fetchone()[0]
                    if state == "active":
                        self._quarantine(database, now, row["holder"], "stale", "resource-epoch-changed")
                    else:
                        database.execute("UPDATE requests SET finish_state='stale' WHERE request_id=?", (row["holder"],))
                database.execute("""UPDATE resources SET epoch=?,generation=generation+1,
                                    blocked=1,blocked_since_ms=?,cleanup_receipt=NULL WHERE name=?""",
                                 (epoch, now, resource))
                self._event(database, now, "resource-epoch-changed", resource=resource, epoch=epoch)
            return dict(database.execute("SELECT * FROM resources WHERE name=?", (resource,)).fetchone())

    def submit(self, request_id, owner, track, resources, *, priority=0, benefit=1,
               estimated_ms=1000, ttl_ms=5000, max_ms=30000, dependencies=()):
        request_id = _identifier(request_id, "request_id")
        owner = _identifier(owner, "owner")
        if track not in ("A", "B", "C"):
            raise QueueError("track must be A, B, or C")
        if not isinstance(resources, dict) or not 1 <= len(resources) <= 8:
            raise QueueError("declare one through eight resource epochs")
        resources = {_identifier(k, "resource", RESOURCE): _identifier(v, "epoch")
                     for k, v in resources.items()}
        if not isinstance(dependencies, (list, tuple)) or len(dependencies) > 16:
            raise QueueError("dependencies must contain at most sixteen existing request IDs")
        dependencies = [_identifier(value, "dependency") for value in dependencies]
        if len(set(dependencies)) != len(dependencies) or request_id in dependencies:
            raise QueueError("duplicate or self dependency")
        specification = {
            "owner": owner, "track": track, "resources": resources,
            "priority": _integer(priority, "priority", 0, 10),
            "benefit": _integer(benefit, "benefit", 1, 3),
            "estimated_ms": _integer(estimated_ms, "estimated_ms", 1, 120000),
            "ttl_ms": _integer(ttl_ms, "ttl_ms", 1000, 30000),
            "max_ms": _integer(max_ms, "max_ms", 1000, 120000),
            "dependencies": sorted(dependencies),
        }
        if ttl_ms > max_ms or estimated_ms > max_ms:
            raise QueueError("ttl and estimated duration must fit the hard deadline")
        encoded = _json(specification)
        with self._transaction() as (database, now):
            existing = database.execute("SELECT * FROM requests WHERE request_id=?", (request_id,)).fetchone()
            if existing:
                if existing["specification"] != encoded:
                    raise QueueError("request ID already belongs to a different specification")
                return self._public(existing)
            pending = database.execute("SELECT count(*) FROM requests WHERE state IN ('queued','active','cleanup')").fetchone()[0]
            if pending >= MAX_PENDING:
                raise QueueError("pending request limit reached")
            for resource, epoch in resources.items():
                row = database.execute("SELECT epoch FROM resources WHERE name=?", (resource,)).fetchone()
                if row is None or row[0] != epoch:
                    raise QueueError("resource is unregistered or its epoch is stale")
            for dependency in dependencies:
                if not database.execute("SELECT 1 FROM requests WHERE request_id=?", (dependency,)).fetchone():
                    raise QueueError("dependency must already exist")
            database.execute("INSERT INTO requests(request_id,specification,state,created_ms) VALUES (?,?,'queued',?)",
                             (request_id, encoded, now))
            self._event(database, now, "submitted", request_id, specification=specification)
            return self._public(database.execute("SELECT * FROM requests WHERE request_id=?", (request_id,)).fetchone())

    def dispatch(self):
        """Grant one eligible request; never start an experiment or replay a lease."""
        with self._transaction() as (database, now):
            candidates = []
            for row in database.execute("SELECT * FROM requests WHERE state='queued' ORDER BY sequence").fetchall():
                spec = json.loads(row["specification"])
                resource_rows = [database.execute("SELECT * FROM resources WHERE name=?", (key,)).fetchone()
                                 for key in spec["resources"]]
                dependencies = [database.execute("SELECT state FROM requests WHERE request_id=?", (key,)).fetchone()[0]
                                for key in spec["dependencies"]]
                stale = any(r is None or r["epoch"] != spec["resources"][r["name"]] for r in resource_rows)
                failed = any(state in TERMINAL and state != "succeeded" for state in dependencies)
                if stale or failed:
                    state = "stale" if stale else "dependency_failed"
                    database.execute("UPDATE requests SET state=? WHERE request_id=?", (state, row["request_id"]))
                    self._event(database, now, state, row["request_id"])
                    continue
                if any(state != "succeeded" for state in dependencies):
                    continue
                if any(r["blocked"] or r["holder"] is not None for r in resource_rows):
                    continue
                score = spec["priority"] + (now - row["created_ms"]) // AGING_MS
                candidates.append(((-score, -spec["benefit"], spec["estimated_ms"], row["sequence"]), row, spec))
            if not candidates:
                return None
            _, row, spec = min(candidates, key=lambda item: item[0])
            token = secrets.token_hex(32)
            lease = {}
            for resource, epoch in sorted(spec["resources"].items()):
                database.execute("UPDATE resources SET holder=?,generation=generation+1 WHERE name=?",
                                 (row["request_id"], resource))
                generation = database.execute("SELECT generation FROM resources WHERE name=?", (resource,)).fetchone()[0]
                lease[resource] = {"epoch": epoch, "generation": generation}
            expires = now + spec["ttl_ms"]
            deadline = now + spec["max_ms"]
            database.execute("""UPDATE requests SET state='active',token_hash=?,lease=?,expires_ms=?,deadline_ms=?
                                WHERE request_id=?""",
                             (hashlib.sha256(token.encode()).hexdigest(), _json(lease), expires, deadline, row["request_id"]))
            self._event(database, now, "granted", row["request_id"], lease=lease, expires_ms=expires, deadline_ms=deadline)
            return {"request_id": row["request_id"], "owner": spec["owner"], "track": spec["track"],
                    "token": token, "lease": lease, "expires_ms": expires, "deadline_ms": deadline}

    @staticmethod
    def _authorized(database, request_id, token):
        _identifier(request_id, "request_id")
        if not isinstance(token, str) or not re.fullmatch(r"[a-f0-9]{64}", token):
            raise QueueError("invalid lease token")
        row = database.execute("SELECT * FROM requests WHERE request_id=?", (request_id,)).fetchone()
        if (row is None or row["state"] != "active"
                or not hmac.compare_digest(row["token_hash"], hashlib.sha256(token.encode()).hexdigest())):
            raise QueueError("lease is not active or token does not match")
        for resource, identity in json.loads(row["lease"]).items():
            current = database.execute("SELECT * FROM resources WHERE name=?", (resource,)).fetchone()
            if (current is None or current["blocked"] or current["holder"] != request_id
                    or current["epoch"] != identity["epoch"] or current["generation"] != identity["generation"]):
                raise QueueError("resource fencing or epoch mismatch")
        return row

    def check(self, request_id, token):
        with self._transaction() as (database, _):
            return self._public(self._authorized(database, request_id, token))

    def heartbeat(self, request_id, token):
        with self._transaction() as (database, now):
            row = self._authorized(database, request_id, token)
            expires = min(now + json.loads(row["specification"])["ttl_ms"], row["deadline_ms"])
            database.execute("UPDATE requests SET expires_ms=? WHERE request_id=?", (expires, request_id))
            self._event(database, now, "heartbeat", request_id, expires_ms=expires)
            return {"request_id": request_id, "expires_ms": expires, "deadline_ms": row["deadline_ms"]}

    def finish(self, request_id, token, outcome, evidence):
        if outcome not in ("succeeded", "failed"):
            raise QueueError("finish outcome must be succeeded or failed")
        if not isinstance(evidence, list) or not 1 <= len(evidence) <= 16:
            raise QueueError("finish requires one through sixteen evidence references")
        evidence = [_text(item, "evidence reference") for item in evidence]
        with self._transaction() as (database, now):
            self._authorized(database, request_id, token)
            database.execute("UPDATE requests SET evidence=? WHERE request_id=?", (_json(evidence), request_id))
            self._quarantine(database, now, request_id, outcome, "experiment-finished")
            return {"request_id": request_id, "state": "cleanup", "requested_outcome": outcome}

    def cancel(self, request_id, owner):
        _identifier(request_id, "request_id")
        _identifier(owner, "owner")
        with self._transaction() as (database, now):
            row = database.execute("SELECT * FROM requests WHERE request_id=?", (request_id,)).fetchone()
            if row is None or json.loads(row["specification"])["owner"] != owner:
                raise QueueError("request does not belong to owner")
            if row["state"] == "active":
                self._quarantine(database, now, request_id, "cancelled", "cancellation-requested")
            elif row["state"] == "queued":
                database.execute("UPDATE requests SET state='cancelled' WHERE request_id=?", (request_id,))
                self._event(database, now, "cancelled", request_id)
            return self._public(database.execute("SELECT * FROM requests WHERE request_id=?", (request_id,)).fetchone())

    def cleanup(self, resource, epoch, generation, observed_ms, receipt, *, stopped, released, in_flight):
        """Accept a trusted adapter's attestation, not proof generated by this queue."""
        _identifier(resource, "resource", RESOURCE)
        _identifier(epoch, "epoch")
        _integer(generation, "generation", 0, 2**63 - 1)
        _integer(observed_ms, "observed_ms", 0, 2**63 - 1)
        _text(receipt, "cleanup receipt")
        if stopped is not True or released is not True or in_flight is not False:
            raise QueueError("cleanup requires stopped, released, and no in-flight input")
        with self._transaction() as (database, now):
            row = database.execute("SELECT * FROM resources WHERE name=?", (resource,)).fetchone()
            if (row is None or row["epoch"] != epoch or row["generation"] != generation
                    or not row["blocked"]):
                raise QueueError("cleanup epoch/generation/state mismatch")
            if not row["blocked_since_ms"] <= observed_ms <= now or now - observed_ms > 5000:
                raise QueueError("cleanup evidence is stale or predates quarantine")
            holder = row["holder"]
            if holder:
                state = database.execute("SELECT state FROM requests WHERE request_id=?", (holder,)).fetchone()[0]
                if state != "cleanup":
                    raise QueueError("active owner cannot be cleaned up without revocation")
            database.execute("UPDATE resources SET blocked=0,holder=NULL,cleanup_receipt=? WHERE name=?", (receipt, resource))
            self._event(database, now, "cleanup-attested", holder, resource=resource, epoch=epoch,
                        generation=generation, observed_ms=observed_ms, receipt=receipt)
            if holder and not database.execute("SELECT 1 FROM resources WHERE holder=?", (holder,)).fetchone():
                database.execute("UPDATE requests SET state=finish_state WHERE request_id=?", (holder,))
                self._event(database, now, "finalized", holder)
            return dict(database.execute("SELECT * FROM resources WHERE name=?", (resource,)).fetchone())

    @staticmethod
    def _public(row):
        result = dict(row)
        result.pop("token_hash", None)
        for key in ("specification", "lease", "evidence"):
            if result[key] is not None:
                result[key] = json.loads(result[key])
        return result

    def status(self, *, after_sequence=0, limit=100):
        _integer(after_sequence, "after_sequence", 0, 2**63 - 1)
        _integer(limit, "limit", 1, 100)
        with self._transaction() as (database, now):
            rows = database.execute("SELECT * FROM requests WHERE sequence>? ORDER BY sequence LIMIT ?",
                                    (after_sequence, limit + 1)).fetchall()
            page = rows[:limit]
            return {"schema_version": SCHEMA_VERSION, "as_of_ms": now,
                    "live_enforcement": False,
                    "resources": [dict(row) for row in database.execute("SELECT * FROM resources ORDER BY name")],
                    "requests": [self._public(row) for row in page],
                    "next_sequence": page[-1]["sequence"] if len(rows) > limit else None}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, help="absolute path to the single shared local database")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--initialize", action="store_true")
    mode.add_argument("--request", type=Path, help="JSON operation/arguments file; keep tokens private")
    arguments = parser.parse_args(argv)
    try:
        if arguments.initialize:
            queue = AccessQueue(arguments.database, create=True)
            result = queue.status()
        else:
            with arguments.request.open("rb") as stream:
                raw = stream.read(65537)
            if len(raw) > 65536:
                raise QueueError("request exceeds 64 KiB")
            request = json.loads(raw, object_pairs_hook=_unique_object)
            if (not isinstance(request, dict) or set(request) != {"operation", "arguments"}
                    or not isinstance(request["arguments"], dict)):
                raise QueueError("request must contain operation and arguments")
            queue = AccessQueue(arguments.database)
            operations = {name: getattr(queue, name) for name in (
                "register", "submit", "dispatch", "check", "heartbeat", "finish", "cancel", "cleanup", "status")}
            if not isinstance(request["operation"], str) or request["operation"] not in operations:
                raise QueueError("unsupported queue operation")
            result = operations[request["operation"]](**request["arguments"])
        print(json.dumps({"ok": True, "result": result}, sort_keys=True, allow_nan=False))
        return 0
    except (QueueError, OSError, sqlite3.Error, json.JSONDecodeError, UnicodeError, TypeError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
