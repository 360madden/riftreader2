"""Read-only collision preflight for multiple existing control-host configs."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import sys

from control_host import ControlHostError, HostConfig, decode_json


MAX_MANIFEST_BYTES = 64 * 1024
MAX_HOSTS = 32
MAX_RESERVED = 128
HOST_FIELDS = {"lab", "configPath"}
RESERVED_FIELDS = {"address", "port", "purpose"}


class FleetError(RuntimeError):
    """One sanitized preflight failure; never includes config contents."""


def _path_key(path: Path) -> str:
    return str(path.resolve()).replace("/", "\\").casefold()


def _label(value, name: str, maximum: int = 64) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= maximum \
            or any(ord(char) < 32 or ord(char) > 126 for char in value):
        raise FleetError(f"invalid-{name}")
    return value


def _port(value) -> int:
    if type(value) is not int or not 1 <= value <= 65535:
        raise FleetError("invalid-reserved-port")
    return value


def _claim(claims: dict[tuple[str, int], str], address: str, port: int, owner: str) -> None:
    endpoint = (str(ipaddress.IPv4Address(address)), port)
    overlapping = [((claimed_address, claimed_port), claimed_owner)
                   for (claimed_address, claimed_port), claimed_owner in claims.items()
                   if claimed_port == port and (claimed_address == endpoint[0]
                                                or claimed_address == "0.0.0.0"
                                                or endpoint[0] == "0.0.0.0")]
    if overlapping:
        _, prior = overlapping[0]
        raise FleetError(f"listener-collision:{endpoint[0]}:{port}:{prior}:{owner}")
    claims[endpoint] = owner


def load_manifest(path: Path) -> tuple[Path, dict]:
    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_file() or resolved.is_symlink():
            raise FleetError("manifest-unavailable")
        data = resolved.read_bytes()
    except OSError as error:
        raise FleetError("manifest-unavailable") from error
    if not 0 < len(data) <= MAX_MANIFEST_BYTES:
        raise FleetError("manifest-size-invalid")
    try:
        value = decode_json(data)
    except ControlHostError as error:
        raise FleetError("manifest-json-invalid") from error
    if not isinstance(value, dict) or set(value) != {"schemaVersion", "hosts", "reservedEndpoints"} \
            or type(value.get("schemaVersion")) is not int or value["schemaVersion"] != 1:
        raise FleetError("manifest-schema-invalid")
    if not isinstance(value["hosts"], list) or not 1 <= len(value["hosts"]) <= MAX_HOSTS:
        raise FleetError("manifest-host-count-invalid")
    if not isinstance(value["reservedEndpoints"], list) \
            or len(value["reservedEndpoints"]) > MAX_RESERVED:
        raise FleetError("manifest-reserved-count-invalid")
    return resolved, value


def validate_fleet(manifest_path: Path) -> dict:
    manifest, value = load_manifest(manifest_path)
    base = manifest.parent
    claims: dict[tuple[str, int], str] = {}
    labs: set[str] = set()
    config_paths: set[str] = set()
    vmx_paths: set[str] = set()
    output_paths: set[str] = set()
    vnc_ports: set[int] = set()
    guest_addresses: set[str] = set()
    machines: set[str] = set()
    guest_secret_hashes: set[str] = set()
    operator_secret_hashes: set[str] = set()
    assignments = []

    for entry in value["reservedEndpoints"]:
        if not isinstance(entry, dict) or set(entry) != RESERVED_FIELDS:
            raise FleetError("reserved-endpoint-fields-invalid")
        try:
            address = str(ipaddress.IPv4Address(_label(entry["address"], "reserved-address")))
        except ipaddress.AddressValueError as error:
            raise FleetError("invalid-reserved-address") from error
        port = _port(entry["port"])
        purpose = _label(entry["purpose"], "reserved-purpose", 128)
        _claim(claims, address, port, f"reserved:{purpose}")

    for index, entry in enumerate(value["hosts"]):
        if not isinstance(entry, dict) or set(entry) != HOST_FIELDS:
            raise FleetError("host-entry-fields-invalid")
        lab = _label(entry["lab"], "lab")
        lab_key = lab.casefold()
        if lab_key in labs:
            raise FleetError("duplicate-lab")
        labs.add(lab_key)
        raw_path = Path(_label(entry["configPath"], "config-path", 32768))
        config_path = raw_path if raw_path.is_absolute() else base / raw_path
        try:
            config_path = config_path.resolve(strict=True)
        except OSError as error:
            raise FleetError(f"host-config-unavailable:{lab}") from error
        config_key = _path_key(config_path)
        if config_key in config_paths:
            raise FleetError("duplicate-config-path")
        config_paths.add(config_key)
        try:
            config = HostConfig.load(config_path)
        except (OSError, ControlHostError) as error:
            raise FleetError(f"host-config-invalid:{lab}") from error
        if config.vmx is None or config.vmrun is None or config.vnc_port is None:
            raise FleetError(f"incomplete-vm-guard:{lab}")
        if (not config.vmx.is_file() or config.vmx.suffix.casefold() != ".vmx"
                or not config.vmrun.is_file() or config.vmrun.name.casefold() != "vmrun.exe"):
            raise FleetError(f"invalid-vm-guard-files:{lab}")
        guest_secret = hashlib.sha256(config.token.encode("utf-8")).hexdigest()
        operator_secret = hashlib.sha256(config.operator_token.encode("utf-8")).hexdigest()
        if guest_secret in guest_secret_hashes:
            raise FleetError("duplicate-guest-secret")
        if operator_secret in operator_secret_hashes:
            raise FleetError("duplicate-operator-secret")
        guest_secret_hashes.add(guest_secret)
        operator_secret_hashes.add(operator_secret)

        unique_values = (
            (vmx_paths, _path_key(config.vmx), "vmx"),
            (output_paths, _path_key(config.output_directory), "output-directory"),
            (vnc_ports, config.vnc_port, "vnc-port"),
            (guest_addresses, config.guest_address, "guest-address"),
            (machines, config.expected_machine_name.casefold(), "machine-identity"),
        )
        for collection, item, label in unique_values:
            if item in collection:
                raise FleetError(f"duplicate-{label}")
            collection.add(item)

        _claim(claims, config.bind_address, config.agent_port, f"{lab}:agent")
        _claim(claims, "127.0.0.1", config.ui_port, f"{lab}:ui")
        _claim(claims, "127.0.0.1", config.vnc_port, f"{lab}:vnc")
        if config.bootstrap_port is not None:
            _claim(claims, config.bind_address, config.bootstrap_port, f"{lab}:bootstrap")
        assignments.append({
            "lab": lab,
            "configPath": str(config_path),
            "vmx": str(config.vmx),
            "vncPort": config.vnc_port,
            "guestAddress": config.guest_address,
            "expectedMachineName": config.expected_machine_name,
            "outputDirectory": str(config.output_directory),
            "listeners": {
                "agent": f"{config.bind_address}:{config.agent_port}",
                "ui": f"127.0.0.1:{config.ui_port}",
                "bootstrap": (f"{config.bind_address}:{config.bootstrap_port}"
                              if config.bootstrap_port is not None else None),
            },
            "launchArgs": [sys.executable, str(Path(__file__).resolve().with_name("control_host.py")),
                           "--config", str(config_path)],
        })
    return {"schemaVersion": 1, "status": "configuration-valid", "scope": "static-only",
            "hostCount": len(assignments),
            "assignments": assignments}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(validate_fleet(args.manifest), indent=2))
        return 0
    except (FleetError, ValueError):
        print(json.dumps({"status": "blocked", "reason": "fleet-preflight-failed"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
