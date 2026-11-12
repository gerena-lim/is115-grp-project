"""Deadline-aware greedy dispatch.

Sorts waiting parcels by earliest preferred delivery deadline, then inserts
each one at the position that minimises the route penalty. Parcels that cannot
possibly be delivered on-time (even by a direct trip) are skipped so their
capacity is not wasted.
"""

from typing import Dict, List

from simulator.models import Parcel, SimulationContext

from .helpers import available_parcels, is_hopeless, try_insert, urgency_key


def dispatch(parcel: Dict[str, Parcel], context: SimulationContext) -> List[str]:
    """Build one trip by urgency, skipping parcels that cannot make it on-time."""
    candidates = [pid for pid in available_parcels(parcel)
                  if not is_hopeless(pid, parcel, context)]
    candidates.sort(key=lambda pid: urgency_key(pid, parcel))

    route: List[str] = []
    for pid in candidates:
        result = try_insert(route, pid, parcel, context)
        if result is not None:
            route, _ = result
    return route