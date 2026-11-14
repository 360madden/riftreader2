"""Shared route limits; local pulse, freshness and movement checks stay separate."""

# Room for useful taught paths without allowing unbounded recordings or trips.
MAX_ROUTE_DISTANCE = 1000.0
MAX_WAYPOINTS = 500
MAX_RECORDING_SAMPLES = 30000
MAX_TRIP_SECONDS = 1800
MAX_TRIP_PULSES = 8192
MAX_TRIP_HOLD_MS = 600000
