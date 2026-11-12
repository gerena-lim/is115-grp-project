"""Cheapest-insertion dispatch with a time-window penalty.

At each step, every remaining candidate is evaluated at its best feasible
insertion position. The candidate producing the lowest total route penalty is
added. This continues until capacity, range, or the return cutoff blocks any
further insertion.
"""

from typing import Dict, List, Optional, Tuple

from simulator.models import Parcel, SimulationContext

from .helpers import (
    available_parcels,
    is_hopeless,
    route_penalty,
    try_insert,
)


def _best_for(route: List[str], pid: str,
              parcel: Dict[str, Parcel], context: SimulationContext
              ) -> Optional[Tuple[List[str], float]]:
    """Return the route with ``pid`` inserted at its best position, plus penalty."""
    result = try_insert(route, pid, parcel, context)
    if result is None:
        return None
    new_route, _ = result
    return new_route, route_penalty(new_route, parcel, context)


def dispatch(parcel: Dict[str, Parcel], context: SimulationContext) -> List[str]:
    """Repeatedly insert the candidate that yields the lowest route penalty."""
    remaining = [pid for pid in available_parcels(parcel)
                 if not is_hopeless(pid, parcel, context)]
    if not remaining:
        return []

    route: List[str] = []
    while remaining:
        best: Optional[Tuple[float, List[str], str]] = None
        for pid in remaining:
            evaluated = _best_for(route, pid, parcel, context)
            if evaluated is None:
                continue
            new_route, new_penalty = evaluated
            if best is None or new_penalty < best[0]:
                best = (new_penalty, new_route, pid)
        if best is None:
            break
        _, route, chosen = best
        remaining.remove(chosen)
    return route