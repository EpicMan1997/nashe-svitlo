#!/usr/bin/env python3
"""Validate published artifacts *after* refresh and before GitHub Pages upload.

No network dependencies. Missing data is legitimate ("unknown"); structurally
incorrect, dated or contradictory payloads must fail deployment.
"""
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
KYIV = ZoneInfo("Europe/Kyiv")
LOCATIONS = {"dacha": "3.1", "home": "4.1", "solovky": "4.1", "naumenky": "10.1"}
STATUSES = {"normal", "preliminary", "stale", "unknown", "suspended"}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def minutes(value):
    require(isinstance(value, str) and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d|24:00", value),
            "Invalid time: " + repr(value))
    h, m = map(int, value.split(":"))
    return h * 60 + m


def check_intervals(intervals, context):
    require(isinstance(intervals, list), context + ": outages must be a list")
    end = 0
    for row in intervals:
        require(isinstance(row, list) and len(row) == 2,
                context + ": invalid interval " + repr(row))
        start, stop = [minutes(x) for x in row]
        require(start >= end and stop > start and stop <= 1440,
                context + ": overlapping, reversed or out-of-order intervals " + repr(row))
        end = stop


def check_emergency(alert, context, now):
    if alert is None:
        return
    require(isinstance(alert, dict), context + ": emergency must be object or null")
    require(alert.get("level") in ("active", "partial"), context + ": invalid emergency level")
    require(isinstance(alert.get("source_checked"), bool), context + ": source_checked missing")
    require(re.fullmatch(r"https://t\.me/dtek_ua/\d+", str(alert.get("url", ""))),
            context + ": emergency URL must be an official DTEK post")
    try:
        issued = datetime.fromisoformat(alert["published_at"]).astimezone(KYIV)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(context + ": invalid emergency timestamp") from exc
    age = now - issued
    limit = timedelta(hours=36) if alert["source_checked"] else timedelta(hours=8)
    require(-timedelta(minutes=5) <= age <= limit,
            context + ": emergency alert too old or in future")


def check_payload(payload, season, config, site, now):
    today = now.date()
    require(isinstance(payload, dict), "Schedule payload must be an object")
    try:
        updated = datetime.fromisoformat(payload["updated_at"]).astimezone(KYIV)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Updated timestamp missing/invalid") from exc
    require(-timedelta(minutes=5) <= now - updated <= timedelta(minutes=20),
            "Schedule content is stale or timestamp is in the future")
    require(payload.get("today_date") == today.isoformat(), "Wrong local today date")
    require(payload.get("tomorrow_date") == (today + timedelta(days=1)).isoformat(),
            "Wrong local tomorrow date")
    require(isinstance(payload.get("days"), dict) and isinstance(payload.get("logs"), list),
            "Top-level day and history keys missing")
    all_locations = payload.get("locations", {})
    require(set(all_locations) == set(LOCATIONS), "Missing/unknown public locations")
    counts = {}
    for loc, group in LOCATIONS.items():
        place = all_locations[loc]
        require(place.get("group") == group, loc + ": incorrect outage queue")
        require(isinstance(place.get("logs"), list), loc + ": no history array")
        require(isinstance(place.get("days"), dict), loc + ": no day data")
        check_emergency(place.get("emergency"), loc, now)
        counts[loc] = {}
        for day in (today, today + timedelta(days=1)):
            date = day.isoformat()
            entry = place["days"].get(date)
            require(isinstance(entry, dict), loc + "/" + date + ": missing day")
            status = entry.get("status")
            require(status in STATUSES, loc + "/" + date + ": invalid status")
            outages = entry.get("outages")
            check_intervals(outages, loc + "/" + date)
            sources = entry.get("sources", [])
            require(isinstance(sources, list), loc + ": malformed sources")
            reports = entry.get("source_reports", {})
            require(isinstance(reports, dict) and len(reports) >= 3,
                    loc + "/" + date + ": missing source monitoring")
            for source, report in reports.items():
                require(isinstance(report, dict) and report.get("status") in
                        ("match", "preliminary", "diff", "old", "unavailable", "partial"),
                        loc + "/" + date + ": invalid source " + source)
                if report.get("outages") is not None:
                    check_intervals(report["outages"], loc + "/" + source)
            if status == "normal":
                require(len(set(sources)) >= 2, loc + "/" + date + ": unverified confirmed schedule")
                require(sum(r["status"] == "match" for r in reports.values()) >= 2,
                        loc + "/" + date + ": fewer than 2 independent confirming sources")
            if status == "unknown":
                require(not outages, loc + "/" + date + ": unknown must not contain a schedule")
            counts[loc][date] = {"status": status, "matching": sum(
                r["status"] == "match" for r in reports.values())}
    require(isinstance(payload.get("source_health", {}).get("issues"), list),
            "Source-health issues must be included")
    require(isinstance(season, dict) and season.get("basis") == "confirmed_schedules_not_actual_outages",
            "Season data basis is missing")
    require(set(season.get("locations", {})) == set(LOCATIONS), "Season locations do not match")
    for key, location in season["locations"].items():
        require(isinstance(location.get("recorded_days"), int) and location["recorded_days"] >= 0,
                "Invalid season recorded days for " + key)
    require(config == {"enabled": False, "snapshotUrl": "", "streamUrl": ""} or (
        config.get("enabled") is True
        and isinstance(config.get("snapshotUrl"), str)
        and isinstance(config.get("streamUrl"), str)),
        "EcoFlow live configuration is malformed")
    manifest = json.loads((site / "manifest.webmanifest").read_text(encoding="utf-8"))
    require(manifest.get("display") == "standalone" and all(
        manifest.get(k) == "./" for k in ("scope", "id", "start_url")),
        "PWA identity/path changed unexpectedly")
    for icon in manifest.get("icons", []):
        require((site / icon["src"]).is_file(), "Missing PWA icon " + icon["src"])
    require((site / "sw.js").is_file() and (site / "ecoflow-live.js").is_file(),
            "Missing client scripts")
    return counts


def main():
    site = ROOT / "site"
    result = check_payload(
        json.loads((site / "data.json").read_text(encoding="utf-8")),
        json.loads((site / "season.json").read_text(encoding="utf-8")),
        json.loads((site / "ecoflow-live-config.json").read_text(encoding="utf-8")),
        site, datetime.now(KYIV))
    print("Validated release: 4 locations, 2 dates, source reports, "
          "emergencies, season, EcoFlow config, PWA assets")
    for loc, periods in result.items():
        print(" ", loc, periods)


if __name__ == "__main__":
    main()
