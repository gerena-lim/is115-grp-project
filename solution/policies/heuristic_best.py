"""Hybrid dispatch: EDF selection + knapsack capacity + NN routing.

Three-stage combination:

  1. Selection (EDF heap).  Available parcels are pushed into a min-heap
     keyed by ``urgency_key`` so the most urgent are chosen first.

  2. Capacity fill (knapsack).  We pop from the heap and accept a parcel
     if it fits in the remaining capacity.  This fills the vehicle with
     an urgency-first, size-feasible subset.

  3. Routing (nearest neighbour).  The selected set is ordered by NN
     from the hub, which is near-optimal for distance.

  4. Feasibility fallback.  If the NN ordering violates range or the
     return cutoff (unlikely — NN is distance-minimising — but possible
     when deadlines are tight), we rebuild the route with penalty
     insertion on the same selected set.  Capacity is already
     guaranteed by the selection step.

Time complexity:  O(n log n)  for heapify + O(n) for selection
                + O(L^2)      for NN + O(L * L^2) for fallback
                = O(n log n + L^3)   where L = selected route length.
Space complexity: O(n)         for heap + selected set + route.
"""

import heapq
from typing import Dict, List

from simulator.models import Parcel, SimulationContext

from .helpers import (
    available_parcels,
    is_hopeless,
    route_feasible,
    try_insert,
    urgency_key,
    EPS,
    HUB,
)


def _nn_route(pids: List[str], parcel: Dict[str, Parcel],
              dist: Dict[str, Dict[str, float]]) -> List[str]:
    """Order ``pids`` by nearest-neighbour from the hub."""
    remaining = list(pids)
    route: List[str] = []
    current = HUB
    while remaining:
        best_pid = None
        best_d = float("inf")
        for pid in remaining:
            loc = parcel[pid]["delivery_location_id"]
            d = dist[current][loc]
            if d < best_d:
                best_d = d
                best_pid = pid
        route.append(best_pid)
        remaining.remove(best_pid)
        current = parcel[best_pid]["delivery_location_id"]
    return route


def dispatch(parcel: Dict[str, Parcel], context: SimulationContext) -> List[str]:
    capacity = context["capacity"]

    candidates = [
        pid for pid in available_parcels(parcel)
        if not is_hopeless(pid, parcel, context)
    ]
    if not candidates:
        return []

    # --- Stage 1: EDF heap ---
    heap = [(urgency_key(pid, parcel), pid) for pid in candidates]
    heapq.heapify(heap)

    # --- Stage 2: knapsack fill ---
    selected: List[str] = []
    load = 0.0
    while heap:
        _, pid = heapq.heappop(heap)
        size = parcel[pid]["size"]
        if load + size > capacity + EPS:
            continue
        selected.append(pid)
        load += size

    if not selected:
        return []

    # --- Stage 3: NN routing ---
    route = _nn_route(selected, parcel, context["travel_distance"])

    # --- Stage 4: feasibility check + fallback ---
    ok, _ = route_feasible(route, parcel, context)
    if ok:
        return route

    # NN ordering broke range/cutoff.  Rebuild with penalty insertion on
    # the same selected set (capacity already guaranteed).
    route = []
    for pid in selected:
        result = try_insert(route, pid, parcel, context)
        if result is not None:
            route, _ = result
    return route