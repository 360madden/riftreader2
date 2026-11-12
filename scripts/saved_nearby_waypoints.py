"""Offline fixed waypoint candidates from already retained nearby-unit evidence.

No process access, selection, capture, route writing or freshness inference.
"""
from copy import deepcopy

from scripts.export_physical_rerun import prepare_unit_samples
from scripts import waypoint_measurements as measurements


def load_saved_nearby_waypoints(wrapper_path, observer_identity):
    """Return the admitted nearest subset with original observer epoch and times.

    The caller's observer must match host/build/player, but its current process
    epoch never replaces the historical source epoch in these stored receipts.
    """
    try:
        current = measurements._identity(observer_identity)
        scan = prepare_unit_samples([wrapper_path], {"identity": current}, frames=[])[0]
        target = scan["target"]
        original = dict(machine=target["hostName"], gameBuildSha256=target["executableSha256"],
                        unitKey=scan["selfKey"], processId=target["processId"],
                        processStartUtcTicks=target["processStartUtcTicks"])
        result = []
        for number, unit in enumerate(scan["units"], 1):
            position = deepcopy(unit["positionXYZCandidate"])
            receipt = measurements.loaded_unit_measurement(position, original, scan["nativeSource"]["path"],
                unit["sampledAtUtc"], unit_key=unit["unitKey"], entity_address=unit["entityAddressDecimal"],
                source_sha256=scan["nativeSource"]["sha256"])
            label = "Loaded unit " + unit["unitKey"][-6:]
            name = unit.get("nameCandidate")
            if name is not None:
                label = " ".join(name["baseNameCandidate"].split())[:80]
                receipt["nameCandidate"] = dict(text=label, baseNameCandidate=name["baseNameCandidate"],
                    source=scan["names"]["nativeSource"]["path"],
                    sourceSha256=scan["names"]["nativeSource"]["sha256"],
                    wrapperSource=deepcopy(scan["names"]["wrapperSource"]),
                    startedAtUtc=name["startedAtUtc"], sampledAtUtc=name["sampledAtUtc"],
                    qualification=name["qualification"], unitKey=unit["unitKey"],
                    entityAddressDecimal=unit["entityAddressDecimal"], observerKey=scan["selfKey"],
                    processIdentity=deepcopy(target))
            result.append(dict(number=number, label=label, unitKey=unit["unitKey"],
                entityAddressDecimal=unit["entityAddressDecimal"], position=position,
                observedAtUtc=unit["sampledAtUtc"], distance=unit["horizontalDistanceCandidate"],
                measurement=receipt))
        return result
    except (OSError, KeyError, TypeError, AttributeError) as error:
        raise ValueError("saved-nearby-source-invalid: " + str(error)) from error
