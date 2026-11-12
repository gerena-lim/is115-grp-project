"""Earliest-Deadline-First dispatch using a min-heap.

Parcels are held in a min-heap keyed by ``(window_end, window_start,
arrival_time, parcel_id)`` so the most urgent parcel is popped first.
Each popped parcel is then inserted at the position that minimises the
route penalty (lateness + distance), subject to capacity, range, and
the return cutoff.

Time complexity:  O(n log n)  for heapify + O(n * L^2) for insertions
Space complexity: O(n)         for the heap and route
"""

import heapq
from typing import Dict, List

from simulator.models import Parcel, SimulationContext

from .helpers import (
    available_parcels,
    is_hopeless,
    try_insert,
    urgency_key,
)


def dispatch(parcel: Dict[str, Parcel], context: SimulationContext) -> List[str]:
    candidates = [
        pid for pid in available_parcels(parcel)
        if not is_hopeless(pid, parcel, context)
    ]
    if not candidates:
        return []

    # Build the min-heap keyed by urgency.
    heap = [(urgency_key(pid, parcel), pid) for pid in candidates]
    heapq.heapify(heap)

    route: List[str] = []
    while heap:
        _, pid = heapq.heappop(heap)
        result = try_insert(route, pid, parcel, context)
        if result is not None:
            route, _ = result

    return route