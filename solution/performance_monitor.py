"""Calculate performance metrics from one simulation run's event log."""

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

# import function parse_time from simulator.loaders
from simulator.loaders import parse_time

from simulator.loaders import day_input_paths

def calculate_metrics(
    parcels: List[Dict[str, str]],
    distances: List[Dict[str, str]],
    config: Dict[str, Any],
    events: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Return a JSON-serializable dictionary for the chosen performance metric.

    parcels and distances are the rows of the day's CSV files, config is the
    contents of config.json, and events are the records from the run's log.
    CSV values are strings, so convert them before calculating. In particular,
    parcel times are "HH:MM" strings while event times are minutes after
    midnight: "17:00" is 17 * 60 = 1020.
    """

      # ---------- lookups ----------------------------------------------------
    windows = {}
    location_of = {}
    size_of = {}
    for row in parcels:
        pid = row["parcel_id"]
        windows[pid] = (
            parse_time(row["delivery_window_start"]),
            parse_time(row["delivery_window_end"]),
        )
        location_of[pid] = row["delivery_location_id"]
        size_of[pid] = float(row["size"])

    dlookup = {
        (row["location_1"], row["location_2"]): float(row["dist"])
        for row in distances
    }

    capacity = float(config["capacity"])

    # ---------- parse the log ---------------------------------------------
    delivered_at = {}
    trips = {}                       # (vehicle_id, trip_id) -> [parcel_ids]
    number_of_trips = 0
    for ev in events:
        et = ev["event_type"]
        if et == "delivery":
            delivered_at[ev["parcel_id"]] = float(ev["time"])
            trips.setdefault((ev["vehicle_id"], ev["trip_id"]), []).append(
                ev["parcel_id"]
            )
        elif et == "hub_departure":
            number_of_trips += 1

    total_parcels = len(windows)
    delivered_count = len(delivered_at)

    # ---------- primary metric + window classification --------------------
    on_time_count = 0
    early_count = 0
    late_count = 0
    total_late_minutes = 0.0

    for pid, (start, end) in windows.items():
        t = delivered_at.get(pid)
        if t is None:
            continue  # undelivered — neither early, on-time, nor late
        if start <= t <= end:
            on_time_count += 1
        elif t < start:
            early_count += 1
        else:
            late_count += 1
            total_late_minutes += t - end

    on_time_delivery_rate = (
        on_time_count / total_parcels if total_parcels else 0.0
    )

    # ---------- cost / utilisation ----------------------------------------
    total_distance_km = 0.0
    loads = []
    for pids in trips.values():
        prev = "HUB"
        for pid in pids:
            loc = location_of[pid]
            total_distance_km += dlookup[(prev, loc)]
            prev = loc
        total_distance_km += dlookup[(prev, "HUB")]
        loads.append(sum(size_of[pid] for pid in pids))

    n_trips = len(trips)
    avg_vehicle_utilisation = (
        sum(loads) / (n_trips * capacity) if n_trips and capacity else 0.0
    )

    return {
        "primary_metric": "on_time_delivery_rate",
        "on_time_delivery_rate": on_time_delivery_rate,
        "on_time_count": on_time_count,
        "early_count": early_count,
        "late_count": late_count,
        "number_of_trips": number_of_trips,
        "total_distance_km": total_distance_km,
        "avg_vehicle_utilisation": avg_vehicle_utilisation,
        "total_late_minutes": total_late_minutes,
        "delivered_count": delivered_count,
        "undelivered_count": total_parcels - delivered_count,
    }

def main(argv: Optional[List[str]] = None) -> int:
    """Load one day's inputs and event log, then write the metrics report."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"),
                        help="directory containing dist.csv, config.json and demand/")
    parser.add_argument("--day", required=True, help="day identifier, for example day_001")
    parser.add_argument("--log", type=Path, required=True,
                        help="event log from a simulator run")
    parser.add_argument("--output", type=Path,
                        help="JSON report (default: metrics.json beside the selected log)")
    args = parser.parse_args(argv)
    try:
        parcel_path, distance_path, config_path = day_input_paths(args.data, args.day)
        output = args.output if args.output is not None else args.log.with_name("metrics.json")
        # The input files all live in the data directory, so this also protects them.
        if output.resolve() == args.data.resolve() or args.data.resolve() in output.resolve().parents:
            raise ValueError("report output must be outside the input data directory")
        if output.resolve() == args.log.resolve():
            raise ValueError("report output must not overwrite the log")
        with parcel_path.open(newline="", encoding="utf-8-sig") as stream:
            parcels = list(csv.DictReader(stream))
        with distance_path.open(newline="", encoding="utf-8-sig") as stream:
            distances = list(csv.DictReader(stream))
        config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        with args.log.open(encoding="utf-8") as stream:
            events = [json.loads(line) for line in stream if line.strip()]
        metrics = calculate_metrics(parcels, distances, config, events)
        report = json.dumps(metrics, indent=2, allow_nan=False) + "\n"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report, encoding="utf-8")
    except (OSError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(f"Metrics report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
