"""Small local library of waypoint routes; no game access or input authority.

Context matches are candidate comparisons, never proof of a world instance.
"""
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
from uuid import uuid4

from scripts.waypoint_measurements import document_measurements, parse_projection_route
from scripts.waypoint_progress import _route, write_json_atomic

ROOT = Path(__file__).resolve().parents[1]
LIBRARY_DIR = ROOT / "artifacts" / "waypoint-routes"
MAX_ENTRY_BYTES = 1024 * 1024
MAX_ENTRIES = 200
_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}\Z")
_HASH = re.compile(r"[0-9a-fA-F]{64}\Z")
_ZONE = re.compile(r"z[0-9a-fA-F]{16}\Z")


def normalize_context(context):
    """Validate supplied provenance, keeping missing context unknown."""
    if context is None:
        return None
    if not isinstance(context, dict) or type(context.get("version")) is not int or context["version"] != 1:
        raise ValueError("invalid-route-context-version")
    allowed = {"version", "zoneIdCandidate", "rawZoneKey", "zoneName", "worldId", "worldName",
               "source", "observedAtUtc", "target", "playerKey"}
    if set(context) - allowed:
        raise ValueError("invalid-route-context-fields")
    result = deepcopy(context)
    for key in ("zoneName", "worldId", "worldName", "source", "playerKey"):
        if key in result and (not isinstance(result[key], str) or not result[key].strip()):
            raise ValueError("invalid-route-context-" + key)
    zone = result.get("zoneIdCandidate")
    if zone is not None:
        if not isinstance(zone, str) or not _ZONE.fullmatch(zone):
            raise ValueError("invalid-route-context-zone-id")
        result["zoneIdCandidate"] = "z" + zone[1:].upper()
    raw = result.get("rawZoneKey")
    if raw is not None and (type(raw) is not int or not 0 <= raw < 2**32 or
                            (zone is not None and int(zone[1:9], 16) != raw)):
        raise ValueError("invalid-route-context-zone-key")
    target = result.get("target")
    if target is not None:
        if (not isinstance(target, dict) or not {"hostName", "executableSha256"}.issubset(target)
                or set(target) - {"hostName", "executableSha256", "processId", "processStartUtcTicks", "executablePath", "hwnd"}
                or not isinstance(target["hostName"], str) or not target["hostName"].strip()
                or not isinstance(target["executableSha256"], str) or not _HASH.fullmatch(target["executableSha256"])):
            raise ValueError("invalid-route-context-target")
        for key in ("processId", "processStartUtcTicks", "hwnd"):
            if key in target and (isinstance(target[key], bool) or not str(target[key]).isdigit() or int(target[key]) <= 0):
                raise ValueError("invalid-route-context-target")
        if "executablePath" in target and (not isinstance(target["executablePath"], str) or not target["executablePath"].strip()):
            raise ValueError("invalid-route-context-target")
    timestamp = result.get("observedAtUtc")
    if timestamp is not None:
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise ValueError("invalid-route-context-time") from None
    if any(result.get(k) is not None for k in ("zoneIdCandidate", "rawZoneKey", "worldId")):
        if not result.get("source") or not timestamp or not target:
            raise ValueError("route-context-provenance-required")
    return result


def compare_context(route_context, current_context):
    """Return matching, mismatch or unknown; equality is only candidate evidence."""
    left, right = normalize_context(route_context), normalize_context(current_context)
    if not left or not right or not left.get("target") or not right.get("target"):
        return "unknown"
    a, b = left["target"], right["target"]
    if any(a[k].casefold() != b[k].casefold() for k in ("hostName", "executableSha256")):
        return "unknown"
    comparable = [k for k in ("zoneIdCandidate", "rawZoneKey", "worldId")
                  if left.get(k) is not None and right.get(k) is not None]
    if not comparable:
        return "unknown"
    if any(left[k] != right[k] for k in comparable):
        return "mismatch"
    if any(left.get(k) is not None and right.get(k) is None for k in ("zoneIdCandidate", "rawZoneKey", "worldId")):
        return "unknown"
    return "matching"


def _path(route_id, library_dir):
    if not isinstance(route_id, str) or not _ID.fullmatch(route_id):
        raise ValueError("invalid-route-id")
    return Path(library_dir) / (route_id + ".json")


def _existing_path(route_id, library_dir):
    """Resolve a saved ID case-insensitively so one library ID is unambiguous."""
    requested = _path(route_id, library_dir)
    directory = Path(library_dir)
    if not directory.is_dir():
        return requested
    matches = [path for path in directory.glob("*.json")
               if path.stem.casefold() == route_id.casefold() and _ID.fullmatch(path.stem)]
    if len(matches) > 1:
        raise ValueError("ambiguous-route-id-case")
    return matches[0] if matches else requested


def _validate(document):
    _route(document)
    if "routeName" in document and (not isinstance(document["routeName"], str)
            or not document["routeName"].strip() or len(document["routeName"]) > 120):
        raise ValueError("invalid-route-name")
    normalize_context(document.get("routeContext"))
    if "pointMeasurements" in document and (not isinstance(document["pointMeasurements"], list)
            or len(document["pointMeasurements"]) != len(document["waypoints"])):
        raise ValueError("route-measurements-alignment-required")
    if "recording" in document:
        parse_projection_route(document)
    if "pointMeasurements" in document:
        receipt_document = dict(document)
        receipt_document.pop("recording", None)
        validated = document_measurements(receipt_document)
        if any(raw is not None and valid is None for raw, valid in zip(document["pointMeasurements"], validated)):
            raise ValueError("invalid-route-measurement")
    return document


def _read_document(path):
    if path.is_symlink():
        raise ValueError("library-entry-symlink-disallowed")
    with path.open("rb") as stream:
        data = stream.read(MAX_ENTRY_BYTES + 1)
    if len(data) > MAX_ENTRY_BYTES:
        raise ValueError("route-entry-too-large")
    return json.loads(data.decode("utf-8-sig"))


def load_route(route_id, library_dir=LIBRARY_DIR):
    return _validate(_read_document(_existing_path(route_id, library_dir)))


def save_route(document, name, route_id=None, *, overwrite=False, library_dir=LIBRARY_DIR):
    """Save a copy with an explicit display name; IDs are safe filenames."""
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120:
        raise ValueError("route-name-required")
    route_id = route_id or uuid4().hex
    path = _existing_path(route_id, library_dir)
    value = deepcopy(_validate(document))
    value["routeName"] = name.strip()
    if "routeContext" in value:
        value["routeContext"] = normalize_context(value["routeContext"])
    if len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_ENTRY_BYTES:
        raise ValueError("route-entry-too-large")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("library-entry-symlink-disallowed")
    reserved = False
    if not overwrite:
        with path.open("x", encoding="utf-8"):
            reserved = True
    try:
        write_json_atomic(path, value)
    except BaseException:
        if reserved:
            path.unlink(missing_ok=True)
        raise
    return route_id


def import_route(source, name=None, route_id=None, *, overwrite=False, library_dir=LIBRARY_DIR):
    """Import a copy from an explicitly named file, retaining the original."""
    source = Path(source)
    document = _read_document(source)
    if name is None:
        name = document.get("routeName") or source.stem
    return save_route(document, name, route_id, overwrite=overwrite, library_dir=library_dir)


def filter_routes(rows, filter_status=None, *, search=None):
    """Filter already-read metadata without reparsing files or changing row order."""
    if filter_status not in (None, "matching", "mismatch", "unknown"):
        raise ValueError("invalid-context-filter")
    if search is not None and (not isinstance(search, str) or len(search) > 200):
        raise ValueError("invalid-library-search")
    query = (search or "").strip().casefold()
    result = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("invalid-library-row")
        context = row.get("routeContext") or {}
        searchable = " ".join(str(value) for value in (
            row.get("name"), row.get("id"), row.get("contextStatus"), row.get("error"),
            context.get("zoneName"), context.get("zoneIdCandidate"),
            context.get("worldName"), context.get("worldId")) if value is not None).casefold()
        if ((filter_status is None or row.get("contextStatus") == filter_status)
                and (not query or query in searchable)):
            result.append(row)
    return result


def list_routes(current_context=None, filter_status=None, *, search=None, library_dir=LIBRARY_DIR):
    """List only this directory; malformed entries are reported rather than hidden."""
    normalize_context(current_context)
    # Validate filters before returning early for an absent library directory.
    filter_routes((), filter_status, search=search)
    directory = Path(library_dir)
    if not directory.exists():
        return []
    result = []
    paths = []
    for path in directory.glob("*.json"):
        paths.append(path)
        if len(paths) > MAX_ENTRIES:
            raise ValueError("library-entry-limit-exceeded")
    for path in sorted(paths, key=lambda p: p.name.casefold()):
        if not _ID.fullmatch(path.stem) or (not path.is_file() and not path.is_symlink()):
            continue
        try:
            doc = load_route(path.stem, directory)
            status = compare_context(doc.get("routeContext"), current_context)
            points, _ = _route(doc)
            count = len(points)
            measured = sum(value is not None for value in document_measurements(doc))
            distance = sum(math.hypot(b[1] - a[1], b[2] - a[2])
                           for a, b in zip(points, points[1:]))
            row = {"id": path.stem, "name": doc.get("routeName") or path.stem,
                   "waypointCount": count, "measuredHeightCount": measured,
                   "estimatedHeightCount": count - measured, "contextStatus": status,
                   "planarDistance": distance,
                   "routeContext": deepcopy(doc.get("routeContext"))}
        except (ValueError, OSError, TypeError, UnicodeError) as error:
            row = {"id": path.stem, "name": path.stem, "contextStatus": "unknown", "error": str(error)}
        row["path"] = str(path.absolute())
        try:
            row["modifiedAtUtc"] = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat().replace("+00:00", "Z")
        except OSError:
            row["modifiedAtUtc"] = None
        result.append(row)
    ordered = sorted(result, key=lambda row: ("error" in row, row["name"].casefold(), row["id"].casefold()))
    return filter_routes(ordered, filter_status, search=search)
