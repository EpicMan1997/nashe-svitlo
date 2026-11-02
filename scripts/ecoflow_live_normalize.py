"""Read-only normalizer for EcoFlow Developer REST and MQTT telemetry.

This module does not connect to EcoFlow, publish data, control appliances,
store serial numbers, or guess missing SOC from sibling batteries.
It is used by a future private SSE gateway; the public GitHub Pages UI is
deliberately not switched out of demo mode until a gateway is available.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import isfinite
from typing import Any

FIELDS = {
    "delta_pro_3": {
        "socPercent": ("cmsBattSoc",),
        "inputW": ("powInSumW",),
        "outputW": ("powOutSumW",),
        "runtimeMinutes": ("cmsDsgRemTime",),
    },
    "delta_2": {
        "socPercent": ("pd.soc",),
        "inputW": ("pd.wattsInSum",),
        "outputW": ("pd.wattsOutSum",),
        "runtimeMinutes": ("pd.remainTime", "bms_emsStatus.dsgRemainTime"),
    },
}
FIELD_AGES_SECONDS = 30.0
VALID_KEYS = frozenset({
    "dacha:dp3", "dacha:d2", "solovky:d2", "naumenky:d2",
})
RANGES = {
    "socPercent": (0, 100),
    "inputW": (0, 20000),
    "outputW": (0, 20000),
    "runtimeMinutes": (1, 10080),
}


def nested_get(blob: dict, path: str) -> Any:
    """Read nested or flattened MQTT/REST properties without guessing."""
    if path in blob:
        return blob[path]
    value: Any = blob
    for segment in path.split("."):
        if not isinstance(value, dict) or segment not in value:
            return None
        value = value[segment]
    return value


def read_number(value: Any, kind: str) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        return None
    low, high = RANGES[kind]
    return float(value) if low <= value <= high else None


def extract_data(message: dict) -> dict:
    """Developer MQTT usually supplies params; REST quota returns direct keys."""
    if not isinstance(message, dict):
        return {}
    data = message.get("params")
    if isinstance(data, dict):
        return data
    data = message.get("data")
    if isinstance(data, dict):
        params = data.get("params")
        return params if isinstance(params, dict) else data
    return message


@dataclass
class StationReading:
    key: str
    model: str
    # Each field maintains its own timestamp. A heartbeat or unrelated MQTT
    # delta must never refresh old power readings.
    readings: dict[str, tuple[float, float]] = field(default_factory=dict)

    def update(self, payload: dict, now: float) -> bool:
        if self.key not in VALID_KEYS or self.model not in FIELDS:
            return False
        data = extract_data(payload)
        changed = False
        for target, paths in FIELDS[self.model].items():
            for path in paths:
                val = nested_get(data, path)
                reading = read_number(val, target)
                if reading is None:
                    continue
                if target in self.readings and self.readings[target][1] > now:
                    continue
                self.readings[target] = reading, now
                changed = True
                break
        return changed

    def snapshot(self, now: float) -> dict | None:
        fresh = {key: value for key, (value, observed) in self.readings.items()
                 if 0 <= now - observed <= FIELD_AGES_SECONDS}
        if not fresh:
            return None
        times = [t for k, (_, t) in self.readings.items()
                 if k in fresh]
        result = {
            "updatedAt": datetime.fromtimestamp(max(times), tz=timezone.utc).isoformat(),
            **fresh,
        }
        # A station charging AC while supplying a load can have nonzero
        # power in both directions, so do not infer operation in that case.
        watts_in, watts_out = fresh.get("inputW"), fresh.get("outputW")
        if watts_in is None or watts_out is None:
            result["operation"] = "unknown"
        elif watts_in == 0 and watts_out == 0:
            result["operation"] = "holding"
        elif watts_in > 0 and watts_out == 0:
            result["operation"] = "charging"
        elif watts_out > 0 and watts_in == 0:
            result["operation"] = "discharging"
        else:
            result["operation"] = "unknown"
        return result


class LocationTelemetry:
    """A private server supplies the serial-to-(key,model) map at startup."""
    def __init__(self, private_serial_map: dict[str, dict]):
        self._by_sn: dict[str, StationReading] = {}
        known_keys: set[str] = set()
        for sn, binding in private_serial_map.items():
            if not isinstance(sn, str) or not sn:
                raise ValueError("Serial mapping must contain nonempty private serials")
            key, model = binding.get("key"), binding.get("model")
            if key not in VALID_KEYS or model not in FIELDS or key in known_keys:
                raise ValueError("Invalid or duplicate canonical station mapping")
            self._by_sn[sn] = StationReading(key, model)
            known_keys.add(key)

    def ingest(self, serial: str, message: dict, now: float) -> bool:
        station = self._by_sn.get(serial)
        return station.update(message, now) if station else False

    def public_devices(self, now: float) -> dict:
        """No serials, credentials, user-chosen names or unsupported stations."""
        return {station.key: reading
                for station in self._by_sn.values()
                if (reading := station.snapshot(now)) is not None}
