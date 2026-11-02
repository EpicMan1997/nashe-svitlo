#!/usr/bin/env python3
"""Publish a minimal, read-only EcoFlow API snapshot for GitHub Pages.

Refresh is run on GitHub Actions every ~10 minutes, NOT a realtime feed.
Serial numbers, API keys, private names, raw quota records and history are
never persisted to the public site. Only a uniquely identified DELTA Pro 3 is
location-bound; the three DELTA 2 are deliberately shown as *unassigned*
until a private owner-verified mapping exists.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from ecoflow_probe import (
    DEVICE_LIST, DEVICE_QUOTA, ProbeError, extract_devices,
    request_api, safe_model
)
from ecoflow_live_normalize import StationReading

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site" / "ecoflow-snapshot.json"
UNASSIGNED = ("unassigned:delta2-1", "unassigned:delta2-2", "unassigned:delta2-3")


def build_snapshot(access, secret, now=None):
    now = now or datetime.now(timezone.utc)
    timestamp = now.isoformat(timespec="seconds")
    result = {"version": 1, "emittedAt": timestamp, "mode": "scheduled",
              "devices": {}, "availability": {
                  "dacha:dp3": "unavailable",
                  "dacha:dp3eb": "unavailable",
                  "dacha:d3p": "unsupported",
                  "dacha:d2": "unassigned",
                  "dacha:r3pw": "unsupported",
                  "home:po": "unsupported",
                  "solovky:d2": "unassigned",
                  "solovky:d2eb": "unassigned",
                  "solovky:r2": "unsupported",
                  "naumenky:d2": "unassigned",
              },
              "unassigned": [], "connection": "ok"}
    devices = extract_devices(request_api(DEVICE_LIST, access, secret))
    delta2_index = 0
    dp3_count = sum(safe_model(d) == "DELTA Pro 3" for d in devices if isinstance(d, dict))
    for entry in devices:
        if not isinstance(entry, dict):
            continue
        model = safe_model(entry)
        if model == "DELTA Pro 3" and dp3_count == 1:
            key, model_type = "dacha:dp3", "delta_pro_3"
        elif model == "DELTA 2":
            if delta2_index >= len(UNASSIGNED):
                continue
            key, model_type = UNASSIGNED[delta2_index], "delta_2"
            delta2_index += 1
            result["unassigned"].append(key)
        else:
            continue
        sn = entry.get("sn")
        if not isinstance(sn, str) or not sn:
            continue
        try:
            quota = request_api(DEVICE_QUOTA, access, secret, {"sn": sn})
        except ProbeError:
            continue
        if not isinstance(quota, dict):
            continue
        # Deliberately allow an unassigned key in the private mapping step.
        station = StationReading("dacha:dp3" if model_type == "delta_pro_3" else "dacha:d2", model_type)
        if not station.update(quota, now.timestamp()):
            continue
        reading = station.snapshot(now.timestamp())
        if reading:
            # The API snapshot request establishes measurement time here; it does
            # not claim the underlying station sampled its sensors at this instant.
            result["devices"][key] = reading
            if key == "dacha:dp3":
                result["availability"][key] = "readable"
    return result


def main():
    access = os.getenv("ECOFLOW_ACCESS_KEY", "").strip()
    secret = os.getenv("ECOFLOW_SECRET_KEY", "").strip()
    if not access or not secret:
        state = {"version": 1, "mode": "scheduled",
                 "emittedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "devices": {}, "unassigned": [], "connection": "unavailable"}
    else:
        try:
            state = build_snapshot(access, secret)
        except Exception:
            # Do not fail outage publishing or disclose provider error strings.
            state = {"version": 1, "mode": "scheduled",
                     "emittedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     "devices": {}, "unassigned": [], "connection": "unavailable"}
    OUT.write_text(json.dumps(state, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print("EcoFlow read-only snapshot: " + str(len(state["devices"])) +
          " stations, " + str(len(state["unassigned"])) +
          " unassigned DELTA 2, provider " + state["connection"] +
          " (no secrets, serials or private labels published)")


if __name__ == "__main__":
    main()
