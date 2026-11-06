"""Small validated configuration seam for bounded live-reader launches."""
from __future__ import annotations

import json
from pathlib import Path


MIN_SCAN_BYTES = 1
MAX_SCAN_BYTES = 8 * 1024 * 1024 * 1024
DEFAULT_SCAN_BYTES = 4 * 1024 * 1024 * 1024
DEFAULT_SCAN_LIMITS = Path(__file__).resolve().parents[1] / "config" / "live-reader-scan-limits.json"
LABS = frozenset({"lab1", "lab2"})


def _scan_bytes(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not MIN_SCAN_BYTES <= value <= MAX_SCAN_BYTES:
        raise ValueError(f"{label} must be an integer from {MIN_SCAN_BYTES} through {MAX_SCAN_BYTES}")
    return value


def load_scan_limits(path: Path = DEFAULT_SCAN_LIMITS) -> tuple[int, dict[str, int]]:
    raw = path.read_bytes()
    if len(raw) > 16 * 1024:
        raise ValueError("live reader scan-limit configuration exceeds 16384 bytes")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid live reader scan-limit configuration") from error
    if not isinstance(value, dict) or set(value) != {"schemaVersion", "defaultMaxScanBytes", "labs"}:
        raise ValueError("unexpected live reader scan-limit configuration shape")
    if value["schemaVersion"] != 1 or not isinstance(value["labs"], dict):
        raise ValueError("unsupported live reader scan-limit configuration")
    unknown = set(value["labs"]) - LABS
    if unknown:
        raise ValueError("unknown live reader lab: " + ", ".join(sorted(unknown)))
    default = _scan_bytes(value["defaultMaxScanBytes"], "defaultMaxScanBytes")
    labs = {lab: _scan_bytes(limit, f"labs.{lab}") for lab, limit in value["labs"].items()}
    return default, labs


def resolve_max_scan_bytes(
    lab: str,
    *,
    config_path: Path = DEFAULT_SCAN_LIMITS,
    override: int | None = None,
) -> int:
    if lab not in LABS:
        raise ValueError("unknown live reader lab")
    if override is not None:
        return _scan_bytes(override, "maxScanBytes override")
    default, labs = load_scan_limits(config_path)
    return labs.get(lab, default)


def build_live_configuration(
    *,
    endpoint: str,
    token: str,
    output_path: str,
    duration_seconds: int,
    poll_interval_milliseconds: int,
    max_scan_bytes: int,
) -> dict[str, object]:
    """Return the exact configuration consumed by RiftReader2.Live."""
    return {
        "schemaVersion": 1,
        "processName": "rift_x64",
        "durationSeconds": duration_seconds,
        "pollIntervalMilliseconds": poll_interval_milliseconds,
        "maxScanBytes": _scan_bytes(max_scan_bytes, "maxScanBytes"),
        "maxScanSeconds": 10,
        "outputPath": output_path,
        "freshnessTimeoutSeconds": 5,
        "delivery": {"endpoint": endpoint, "token": token},
    }
