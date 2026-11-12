"""Nearest-feasible-neighbour dispatch.

Builds one trip by repeatedly appending the closest unassigned parcel
(from the current location) that keeps capacity, range, and the return
cutoff intact. Pure distance heuristic: delivery windows are ignored,
so on-time performance is typically worse than deadline-aware policies
while trip distance is usually the shortest.

Time complexity:  O(n^2)   (n iterations, each scans n candidates)
Space complexity: O(n)     (candidates set + route list)
"""

from typing import Dict, List

from simulator.models import Parcel, SimulationContext

from .helpers import available_parcels, is_hopeless, EPS

HUB = "HUB"


def dispatch(parcel: Dict[str, Parcel], context: SimulationContext) -> List[str]:
    dist = context["travel_distance"]
    capacity = context["capacity"]
    max_range = context["max_trip_distance_km"]
    departure = context["current_time"] + context["departure_delay"]
    cutoff = context["return_cutoff"]

    candidates = {
        pid for pid in available_parcels(parcel)
        if not is_hopeless(pid, parcel, context)
    }
    if not candidates:
        return []

    route: List[str] = []
    load = 0.0
    current_loc = HUB
    # Running distance of the partial route, INCLUDING the return to HUB.
    current_distance = 0.0

    while True:
        best_pid = None
        best_dist = float("inf")
        best_new_distance = 0.0

        for pid in candidates:
            record = parcel[pid]
            if load + record["size"] > capacity + EPS:
                continue

            new_loc = record["delivery_location_id"]
            # Append cost = new leg + new return - old return.
            append_cost = (
                dist[current_loc][new_loc]
                + dist[new_loc][HUB]
                - dist[current_loc][HUB]
            )
            new_distance = current_distance + append_cost

            if new_distance > max_range + EPS:
                continue
            if departure + new_distance > cutoff + EPS:
                continue

            d = dist[current_loc][new_loc]
            if d < best_dist:
                best_dist = d
                best_pid = pid
                best_new_distance = new_distance

        if best_pid is None:
            break

        route.append(best_pid)
        candidates.remove(best_pid)
        load += parcel[best_pid]["size"]
        current_loc = parcel[best_pid]["delivery_location_id"]
        current_distance = best_new_distance

    return route