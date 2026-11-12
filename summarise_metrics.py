"""Aggregate per-day metrics.json files into a single summarised file.

For each policy, reads:
    results/<policy>/day_001/metrics.json
    ...
    results/<policy>/day_020/metrics.json

and writes one entry to:
    results/algorithms_summarised_metrics.json

in the form:

    {
      "<policy>": {
        "total_parcel":          <int>,
        "on_time_delivery_rate": <float in [0, 1]>,
        "early_rate":            <float in [0, 1]>,
        "late_rate":             <float in [0, 1]>,
        "completion_rate":       <float in [0, 1]>,
        "late_per_delivered":    <float>            # avg minutes late per delivered parcel
      },
      ...
    }

Aggregation is done on SUMS (not averages of daily rates), so the rates
are the correct weighted figures across all 20 days.
"""

import json
from pathlib import Path
from typing import Optional

POLICIES = [
    "baseline",
    "earliest_deadline",
    "heuristic_best",
    "knapsack_dispatch",
    "nearest_neighbour",
]

DAYS = [f"day_{d:03d}" for d in range(1, 21)]

RESULTS_ROOT = Path("results")
OUTPUT_JSON = RESULTS_ROOT / "algorithms_summarised_metrics.json"
OUTPUT_TXT  = RESULTS_ROOT / "algorithms_summarised_metrics.txt"


def load_metrics(policy: str, day: str) -> Optional[dict]:
    path = RESULTS_ROOT / policy / day / "metrics.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def summarise_policy(policy: str) -> dict:
    days_found = 0
    days_missing = []

    total_delivered = 0
    total_undelivered = 0
    total_on_time = 0
    total_early = 0
    total_late = 0
    total_late_minutes = 0.0
    total_distance_km = 0.0
    total_trips = 0

    for day in DAYS:
        m = load_metrics(policy, day)
        if m is None:
            days_missing.append(day)
            continue
        days_found += 1
        total_delivered += int(m.get("delivered_count", 0))
        total_undelivered += int(m.get("undelivered_count", 0))
        total_on_time += int(m.get("on_time_count", 0))
        total_early += int(m.get("early_count", 0))
        total_late += int(m.get("late_count", 0))
        total_late_minutes += float(m.get("total_late_minutes", 0.0))
        total_distance_km += float(m.get("total_distance_km", 0.0))
        total_trips += int(m.get("number_of_trips", 0))

    total_parcels = total_delivered + total_undelivered

    on_time_rate = total_on_time / total_parcels if total_parcels else 0.0
    early_rate = total_early / total_parcels if total_parcels else 0.0
    late_rate = total_late / total_parcels if total_parcels else 0.0
    completion_rate = (
        total_delivered / total_parcels if total_parcels else 0.0
    )
    late_per_delivered = (
        total_late_minutes / total_delivered if total_delivered else 0.0
    )

    return {
        "days_found": days_found,
        "days_missing": days_missing,
        "total_parcel": total_parcels,
        "on_time_delivery_rate": round(on_time_rate, 4),
        "early_rate": round(early_rate, 4),
        "late_rate": round(late_rate, 4),
        "completion_rate": round(completion_rate, 4),
        "late_per_delivered": round(late_per_delivered, 2),
        "total_on_time": total_on_time,
        "total_early": total_early,
        "total_late": total_late,
        "total_delivered": total_delivered,
        "total_undelivered": total_undelivered,
        "total_late_minutes": round(total_late_minutes, 2),
        "total_trips": total_trips,
        "total_distance_km": round(total_distance_km, 2),
    }


def main() -> None:
    summary = {}
    for policy in POLICIES:
        print(f"Processing {policy}...")
        summary[policy] = summarise_policy(policy)

    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )

    # Human-readable table
    header = (
        f"{'Policy':<22}{'Total':>8}{'On-Time%':>11}"
        f"{'Early%':>9}{'Late%':>8}{'Complete%':>12}{'Late/Deliv':>13}{'Trips':>8}"
    )
    lines = [
        "=" * len(header),
        header,
        "=" * len(header),
    ]
    for policy, s in summary.items():
        if s["days_found"] == 0:
            lines.append(f"{policy:<22}  (no results found)")
            continue
        lines.append(
            f"{policy:<22}"
            f"{s['total_parcel']:>8}"
            f"{s['on_time_delivery_rate']:>10.2%}"
            f"{s['early_rate']:>9.2%}"
            f"{s['late_rate']:>8.2%}"
            f"{s['completion_rate']:>11.2%}"
            f"{s['late_per_delivered']:>13.2f}"
            f"{s['total_trips']:>8}"
        )
        if s["days_missing"]:
            lines.append(
                f"  ! missing {len(s['days_missing'])} day(s): "
                f"{', '.join(s['days_missing'])}"
            )
    lines.append("=" * len(header))

    table = "\n".join(lines)
    OUTPUT_TXT.write_text(table + "\n", encoding="utf-8")

    print("\n" + table)
    print(f"\nWrote {OUTPUT_JSON}")
    print(f"Wrote {OUTPUT_TXT}")


if __name__ == "__main__":
    main()