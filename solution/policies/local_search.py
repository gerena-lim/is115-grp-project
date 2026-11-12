"""Local-search dispatch seeded by penalty insertion.

Starting from the penalty-insertion route, alternate 2-opt (reverse a
sub-segment) and relocate (move a parcel to another position) moves until no
move lowers the route penalty. A final insertion pass tries to add any
candidates that only became feasible after reordering.
"""

from typing import Dict, List

from simulator.models import Parcel, SimulationContext

from .helpers import (
    available_parcels,
    is_hopeless,
    route_feasible,
    route_penalty,
    try_insert,
)
from .penalty_insertion import dispatch as seed_dispatch

EPS = 1e-9
MAX_ITERATIONS = 20


def _try_2opt(route: List[str], parcel: Dict[str, Parcel],
              context: SimulationContext) -> List[str]:
    """Return the best route found by reversing a single sub-segment."""
    best = route
    best_penalty = route_penalty(route, parcel, context)
    n = len(route)
    for i in range(n - 1):
        for j in range(i + 1, n):
            candidate = route[:i] + route[i:j + 1][::-1] + route[j + 1:]
            ok, _ = route_feasible(candidate, parcel, context)
            if not ok:
                continue
            penalty = route_penalty(candidate, parcel, context)
            if penalty < best_penalty - EPS:
                best = candidate
                best_penalty = penalty
    return best


def _try_relocate(route: List[str], parcel: Dict[str, Parcel],
                  context: SimulationContext) -> List[str]:
    """Return the best route found by moving one parcel to another position."""
    best = route
    best_penalty = route_penalty(route, parcel, context)
    n = len(route)
    for i in range(n):
        reduced = route[:i] + route[i + 1:]
        for j in range(len(reduced) + 1):
            candidate = reduced[:j] + [route[i]] + reduced[j:]
            ok, _ = route_feasible(candidate, parcel, context)
            if not ok:
                continue
            penalty = route_penalty(candidate, parcel, context)
            if penalty < best_penalty - EPS:
                best = candidate
                best_penalty = penalty
    return best


def dispatch(parcel: Dict[str, Parcel], context: SimulationContext) -> List[str]:
    """Seed with penalty insertion, then improve by 2-opt and relocate."""
    route = seed_dispatch(parcel, context)
    if len(route) < 2:
        return route

    improved = True
    iterations = 0
    while improved and iterations < MAX_ITERATIONS:
        improved = False
        iterations += 1
        new_route = _try_2opt(route, parcel, context)
        if new_route != route:
            route = new_route
            improved = True
        new_route = _try_relocate(route, parcel, context)
        if new_route != route:
            route = new_route
            improved = True

    # Final pass: try any remaining candidates that now fit.
    remaining = [pid for pid in available_parcels(parcel)
                 if not is_hopeless(pid, parcel, context) and pid not in route]
    for pid in remaining:
        result = try_insert(route, pid, parcel, context)
        if result is not None:
            route, _ = result
    return route