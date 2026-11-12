"""Shared helper functions for dispatch policies.

All functions are read-only with respect to the ``parcel`` and ``context``
snapshots passed by the simulator. Times are minutes after midnight,
distances are kilometres, and at 60 km/h one kilometre equals one minute
of travel time.

Only the Python standard library and ``simulator.models`` types are used.
"""

from typing import Dict, List, Optional, Tuple

from simulator.models import Parcel, SimulationContext

HUB = "HUB"
EPS = 1e-9  # tolerance for float comparisons


# ---------------------------------------------------------------------------
# Basic accessors
# ---------------------------------------------------------------------------

def available_parcels(parcel: Dict[str, Parcel]) -> List[str]:
    """Return IDs of parcels that have not yet been assigned or delivered."""
    return [
        pid for pid, record in parcel.items()
        if record["vehicle_assigned"] is None and record["delivery_time"] is None
    ]


def route_load(route: List[str], parcel: Dict[str, Parcel]) -> float:
    """Total size of all parcels on the route."""
    return sum(parcel[pid]["size"] for pid in route)


# ---------------------------------------------------------------------------
# Route geometry and timing
# ---------------------------------------------------------------------------

def route_distance(route: List[str], parcel: Dict[str, Parcel],
                   dist: Dict[str, Dict[str, float]]) -> float:
    """Total distance HUB -> stop1 -> ... -> stopn -> HUB in km."""
    if not route:
        return 0.0
    total = 0.0
    current = HUB
    for pid in route:
        nxt = parcel[pid]["delivery_location_id"]
        total += dist[current][nxt]
        current = nxt
    total += dist[current][HUB]
    return total


def cumulative_arrivals(route: List[str], parcel: Dict[str, Parcel],
                        dist: Dict[str, Dict[str, float]],
                        departure_time: float) -> List[float]:
    """Arrival time at each stop. Same length as ``route``."""
    arrivals: List[float] = []
    current = HUB
    t = departure_time
    for pid in route:
        nxt = parcel[pid]["delivery_location_id"]
        t += dist[current][nxt]
        arrivals.append(t)
        current = nxt
    return arrivals


def on_time_predicted(route: List[str], parcel: Dict[str, Parcel],
                      dist: Dict[str, Dict[str, float]],
                      departure_time: float) -> int:
    """Count how many stops would be delivered within their window."""
    count = 0
    for pid, t in zip(route, cumulative_arrivals(route, parcel, dist, departure_time)):
        record = parcel[pid]
        if record["delivery_window_start"] - EPS <= t <= record["delivery_window_end"] + EPS:
            count += 1
    return count


# ---------------------------------------------------------------------------
# Hard-constraint checking (capacity, range, return cutoff)
# ---------------------------------------------------------------------------

def route_feasible(route: List[str], parcel: Dict[str, Parcel],
                   context: SimulationContext,
                   departure_time: Optional[float] = None) -> Tuple[bool, str]:
    """Check capacity, range, return cutoff, and parcel availability.

    Returns ``(True, "")`` if the route can be committed, otherwise
    ``(False, reason)``. ``departure_time`` defaults to
    ``current_time + departure_delay`` as the simulator uses.

    Capacity is ``context["capacity"]`` (30 units in this project). The
    load is the sum of parcel sizes on the route; a trip whose load
    exceeds capacity is rejected.
    """
    if not route:
        return True, ""
    if departure_time is None:
        departure_time = context["current_time"] + context["departure_delay"]
    dist = context["travel_distance"]
    capacity = context["capacity"]
    max_range = context["max_trip_distance_km"]
    cutoff = context["return_cutoff"]

    seen = set()
    load = 0.0
    for pid in route:
        if pid in seen:
            return False, f"duplicate parcel {pid}"
        seen.add(pid)
        record = parcel[pid]
        if record["vehicle_assigned"] is not None or record["delivery_time"] is not None:
            return False, f"parcel {pid} already assigned/delivered"
        load += record["size"]
    if load > capacity + EPS:
        return False, f"load {load:g} > capacity {capacity:g}"

    total = route_distance(route, parcel, dist)
    if total > max_range + EPS:
        return False, f"distance {total:g} > range {max_range:g}"
    if departure_time + total > cutoff + EPS:
        return False, (
            f"return {departure_time + total:g} > cutoff {cutoff:g}"
        )
    return True, ""


# ---------------------------------------------------------------------------
# Soft penalty (used by insertion and local-search policies)
# ---------------------------------------------------------------------------

def route_penalty(route: List[str], parcel: Dict[str, Parcel],
                  context: SimulationContext,
                  departure_time: Optional[float] = None,
                  late_weight: float = 10.0,
                  early_weight: float = 10.0,
                  distance_weight: float = 1.0) -> float:
    """Score a route; lower is better.

    Combines:
    * ``late_weight``  * minutes past ``delivery_window_end``
    * ``early_weight`` * minutes before ``delivery_window_start``
    * ``distance_weight`` * total route distance (km)

    This is a soft objective only; it does **not** enforce capacity, range
    or the return cutoff. Callers should check :func:`route_feasible` first.
    """
    if not route:
        return 0.0
    if departure_time is None:
        departure_time = context["current_time"] + context["departure_delay"]
    dist = context["travel_distance"]
    penalty = 0.0
    for pid, t in zip(route, cumulative_arrivals(route, parcel, dist, departure_time)):
        record = parcel[pid]
        if t > record["delivery_window_end"]:
            penalty += late_weight * (t - record["delivery_window_end"])
        elif t < record["delivery_window_start"]:
            penalty += early_weight * (record["delivery_window_start"] - t)
    penalty += distance_weight * route_distance(route, parcel, dist)
    return penalty


# ---------------------------------------------------------------------------
# Insertion support
# ---------------------------------------------------------------------------

def best_insertion_index(route: List[str], pid: str,
                         parcel: Dict[str, Parcel],
                         dist: Dict[str, Dict[str, float]]) -> Tuple[int, float]:
    """Return ``(index, delta_distance_km)`` of the cheapest insertion.

    .. warning::
        This is a **pure distance** heuristic and does **not** check
        capacity, range, or time-window feasibility. It is provided for
        distance-only analysis / reporting and for callers that have
        already pre-filtered candidates by size. For a dispatch policy,
        use :func:`try_insert` instead, which enforces capacity, range
        and the return cutoff.
    """
    loc = parcel[pid]["delivery_location_id"]
    best_index = 0
    best_delta = float("inf")
    for i in range(len(route) + 1):
        prev = HUB if i == 0 else parcel[route[i - 1]]["delivery_location_id"]
        nxt = HUB if i == len(route) else parcel[route[i]]["delivery_location_id"]
        delta = dist[prev][loc] + dist[loc][nxt] - dist[prev][nxt]
        if delta < best_delta:
            best_delta = delta
            best_index = i
    return best_index, best_delta


def try_insert(route: List[str], pid: str, parcel: Dict[str, Parcel],
               context: SimulationContext,
               late_weight: float = 10.0,
               early_weight: float = 10.0,
               distance_weight: float = 1.0) -> Optional[Tuple[List[str], int]]:
    """Attempt to add ``pid`` to ``route``.

    Picks the best insertion position that keeps the route feasible and
    returns ``(new_route, insertion_index)``, or ``None`` if capacity,
    range, or the return cutoff would be violated.

    The function performs two complementary capacity checks:

    1. An O(1) pre-check using :func:`route_load`; if even one insertion
       cannot fit, we return ``None`` without scanning positions.
    2. A full :func:`route_feasible` call on each trial route, which
       re-validates capacity, range and the return cutoff for the whole
       route.
    """
    # Capacity pre-check: if the parcel cannot possibly fit, skip the scan.
    if route_load(route, parcel) + parcel[pid]["size"] > context["capacity"] + EPS:
        return None

    dist = context["travel_distance"]
    best_score = float("inf")
    best_route: Optional[List[str]] = None
    best_index = -1

    for i in range(len(route) + 1):
        trial = route[:i] + [pid] + route[i:]
        ok, _ = route_feasible(trial, parcel, context)
        if not ok:
            continue
        score = route_penalty(trial, parcel, context,
                              late_weight=late_weight,
                              early_weight=early_weight,
                              distance_weight=distance_weight)
        if score < best_score:
            best_score = score
            best_route = trial
            best_index = i

    if best_route is None:
        return None
    return best_route, best_index


# ---------------------------------------------------------------------------
# Deadline-aware candidate filtering
# ---------------------------------------------------------------------------

def urgency_key(pid: str, parcel: Dict[str, Parcel]
                ) -> Tuple[float, float, float, str]:
    """Sort key for deadline-aware greedy: earliest deadline first."""
    record = parcel[pid]
    return (
        record["delivery_window_end"],
        record["delivery_window_start"],
        record["arrival_time"],
        pid,
    )


def earliest_direct_arrival(pid: str, parcel: Dict[str, Parcel],
                            context: SimulationContext) -> float:
    """Earliest possible arrival if the parcel is the only stop.

    Useful as a lower bound on delivery time when filtering candidates.
    """
    record = parcel[pid]
    departure = context["current_time"] + context["departure_delay"]
    return departure + context["travel_distance"][HUB][record["delivery_location_id"]]


def is_hopeless(pid: str, parcel: Dict[str, Parcel],
                context: SimulationContext) -> bool:
    """Return True if the parcel cannot possibly be delivered on-time.

    A direct HUB -> location -> HUB trip is the fastest way to reach the
    destination and uses the minimum round-trip distance, so if that trip
    is infeasible or already too late for the parcel's window, no longer
    route can make the parcel on-time.

    The check also covers two edge cases:

    * ``size > capacity`` -- the parcel cannot fit on any vehicle, so it
      is hopeless regardless of location or timing.
    * Direct trip exceeds the vehicle range or the return cutoff.
    """
    record = parcel[pid]
    dist = context["travel_distance"]
    loc = record["delivery_location_id"]
    departure = context["current_time"] + context["departure_delay"]

    # Size check: a parcel larger than vehicle capacity can never be sent.
    if record["size"] > context["capacity"] + EPS:
        return True

    one_way = dist[HUB][loc]
    round_trip = one_way + dist[loc][HUB]
    if round_trip > context["max_trip_distance_km"] + EPS:
        return True
    if departure + round_trip > context["return_cutoff"] + EPS:
        return True
    if departure + one_way > record["delivery_window_end"] + EPS:
        return True
    return False