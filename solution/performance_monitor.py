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

    # Map each parcel to its preferred delivery window.
    windows = {}
    for row in parcels:
        pid = row["parcel_id"]
        windows[pid] = (
            parse_time(row["delivery_window_start"]),
            parse_time(row["delivery_window_end"])
        )

    # Collect actual delivery times and trip count from the log.
    delivered_at = {}
    number_of_trips = 0
    for event in events:
        if event["event_type"] == "delivery":
            delivered_at[event["parcel_id"]] = float(event["time"])
        elif event["event_type"] == "hub_departure":
            number_of_trips += 1

    total_parcels = len(windows)
    delivered_count = len(delivered_at)
    undelivered_count = total_parcels - delivered_count

    on_time_count = 0
    early_count = 0
    late_count = 0
    total_abs_deviation = 0.0
    max_late_minutes = 0.0

    for pid, (window_start, window_end) in windows.items():

        if pid not in delivered_at:
            continue
        t = delivered_at[pid]

        if window_start <= t <= window_end:
            on_time_count += 1

        elif t < window_start:
            early_count += 1
            total_abs_deviation += window_start - t

        else: 
            late_count += 1
            late_minutes = t - window_end
            total_abs_deviation += late_minutes
            max_late_minutes = max(max_late_minutes, late_minutes)

    on_time_delivery_rate = (
        on_time_count / total_parcels if total_parcels else 0.0
    )

    delivered_on_time_rate = (
        on_time_count / delivered_count if delivered_count else 0.0
    )

    average_abs_window_deviation_minutes = (
        total_abs_deviation / delivered_count if delivered_count else 0.0
    )

    return {
        "primary_metric": "on_time_delivery_rate",
        "on_time_delivery_rate": on_time_delivery_rate,
        "delivered_on_time_rate": delivered_on_time_rate,
        "total_parcels": total_parcels,
        "delivered_count": delivered_count,
        "undelivered_count": undelivered_count,
        "on_time_count": on_time_count,
        "early_count": early_count,
        "late_count": late_count,
        "average_abs_window_deviation_minutes": average_abs_window_deviation_minutes,
        "max_late_minutes": max_late_minutes,
        "number_of_trips": number_of_trips
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
