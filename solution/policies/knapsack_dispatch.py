"""Location-grouped knapsack / bin-packing dispatch.

Groups waiting parcels by ``delivery_location_id``. Each location is a
"bin" whose items are its parcels; travelling to that location costs
the same regardless of how many parcels are delivered there. Locations
are sorted by (earliest deadline in group, round-trip distance per
parcel) — urgency first, then value density — and parcels are inserted
in that order until capacity, range, or the return cutoff blocks
further insertions.

Time complexity:  O(n log n)  for grouping + O(n * L^2) for insertions
Space complexity: O(n)         for the grouping dict + route
"""

from collections import defaultdict
from typing import Dict, List

from simulator.models import Parcel, SimulationContext

from .helpers import (
    available_parcels,
    is_hopeless,
    try_insert,
    urgency_key,
    HUB,
)


def dispatch(parcel: Dict[str, Parcel], context: SimulationContext) -> List[str]:
    dist = context["travel_distance"]

    candidates = [
        pid for pid in available_parcels(parcel)
        if not is_hopeless(pid, parcel, context)
    ]
    if not candidates:
        return []

    # Group by delivery location.
    by_loc: Dict[str, List[str]] = defaultdict(list)
    for pid in candidates:
        by_loc[parcel[pid]["delivery_location_id"]].append(pid)

    # Score every location group.  Lower sort key = higher priority.
    # Primary:    earliest deadline in the group (EDF-like urgency).
    # Secondary:  round-trip distance per parcel (value density).
    grouped = []
    for loc, pids in by_loc.items():
        min_deadline = min(parcel[pid]["delivery_window_end"] for pid in pids)
        round_trip = dist[HUB][loc] + dist[loc][HUB]
        dist_per_parcel = round_trip / max(len(pids), 1)
        grouped.append((min_deadline, dist_per_parcel, pids))

    grouped.sort(key=lambda item: (item[0], item[1]))

    # Fill capacity by walking through location groups.
    route: List[str] = []
    for _, _, pids in grouped:
        # Inside a group, insert urgent parcels first so they have priority
        # for the (now scarcer) remaining capacity.
        pids.sort(key=lambda pid: urgency_key(pid, parcel))
        for pid in pids:
            result = try_insert(route, pid, parcel, context)
            if result is not None:
                route, _ = result

    return route