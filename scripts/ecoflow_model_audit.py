#!/usr/bin/env python3
"""Read-only model identification from private EcoFlow serials, never printing them.

Community mappings are advisory, not EcoFlow-official. No commands or quota requests.
"""
import os
from ecoflow_probe import DEVICE_LIST, extract_devices, request_api, safe_model

# Distinct known families from EcoFlow IoT / ioBroker community documentation.
# Compare privately; never print a serial number or its prefix.
FAMILIES = [
    ("D362", "DELTA 3 Plus"), ("P351", "DELTA 3 Plus"),
    ("D381", "DELTA 3 Max"), ("D3N", "DELTA 3 Max"),
    ("D3M", "DELTA 3 Max / Plus"),
    ("D361", "DELTA 3 1500"), ("P231", "DELTA 3 1500"),
    ("R65", "RIVER 3"), ("R64", "RIVER 3"),
    ("R63", "RIVER 3 Plus"),
    ("R62", "RIVER 2 Pro"), ("R61", "RIVER 2 Max"),
    ("R60", "RIVER 2"), ("MR5", "DELTA Pro 3"),
    ("R35", "DELTA 2 Max"), ("R33", "DELTA 2"),
    ("J32", "PowerOcean"), ("HJ3", "PowerOcean"),
    ("HW52", "EcoFlow Smart Plug"), ("HW51", "PowerStream"),
    ("BK", "STREAM product line"), ("ES22", "STREAM AC 5000"),
    ("ES21", "STREAM 5000"),
]

def identify(item):
    sn=item.get("sn")
    if not isinstance(sn, str):
        return "Serial unavailable"
    for prefix, label in sorted(FAMILIES, key=lambda p: len(p[0]), reverse=True):
        if sn.upper().startswith(prefix):
            return label
    return "Unknown family (no reliable reference)"

def main():
    access=os.environ["ECOFLOW_ACCESS_KEY"]
    secret=os.environ["ECOFLOW_SECRET_KEY"]
    data=extract_devices(request_api(DEVICE_LIST,access,secret))
    print(f"Device models found: {len(data)}")
    print("Serials, keys, private names and prefixes are not printed.")
    for index, entry in enumerate(data,1):
        print(f"#{index}: API label={safe_model(entry)} | family mapping={identify(entry)}")
    print("Mapping is based on community public prefix tables and is not official EcoFlow identification.")

if __name__=="__main__":
    main()
