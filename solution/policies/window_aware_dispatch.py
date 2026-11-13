"""Window-safe location grouping with short trips and controlled dispatch delay.

Evaluated against gerena-lim/is115-grp-project commit 2abb07b.
Uses only the standard library and the bundled policy helpers.

All policy decisions use only the supplied parcel/context snapshots. This
module does not read demand files or change the supplied simulator or data.
Parameters were explored on the supplied 20 days, rather than a held-out set.
"""

import math
from collections import defaultdict

from .helpers import EPS, available_parcels, is_hopeless, urgency_key

# Heuristic preferences. The actual fleet configuration remains unchanged.
PREFERRED_MAX_TRIP_KM = 120.0
MIN_DISPATCH_LOAD = 24.0
URGENCY_BAND_MINUTES = 30.0
PLANNING_INTERVAL_MINUTES = 10.0
RECONSIDER_PASSES = 2
HUB = 'HUB'


def _insert_within_windows(route, parcel_id, parcels, context):
    """Return the shortest feasible insertion that keeps every parcel on time."""
    distances = context['travel_distance']
    departure = context['current_time'] + context['departure_delay']
    load = sum(parcels[pid]['size'] for pid in route) + parcels[parcel_id]['size']
    if load > context['capacity'] + EPS:
        return None

    best_key = None
    best_route = None
    for index in range(len(route) + 1):
        trial = route[:index] + [parcel_id] + route[index:]
        predicted_time = departure
        location = HUB
        valid = True
        for pid in trial:
            record = parcels[pid]
            destination = record['delivery_location_id']
            predicted_time += distances[location][destination]
            location = destination
            if not (record['delivery_window_start'] - EPS <= predicted_time
                    <= record['delivery_window_end'] + EPS):
                valid = False
                break
        if not valid:
            continue

        return_time = predicted_time + distances[location][HUB]
        trip_distance = return_time - departure  # 60 km/h in the supplied model.
        if return_time > context['return_cutoff'] + EPS:
            continue
        if trip_distance > context['max_trip_distance_km'] + EPS:
            continue

        key = (trip_distance, index)
        if best_key is None or key < best_key:
            best_key = key
            best_route = trial
    return best_route


def dispatch(parcel, context):
    """Plan a trip for the current vehicle, or defer it one planning round."""
    # The copy holds a routing preference; the caller's snapshot is read-only.
    planning = dict(context)
    planning['max_trip_distance_km'] = min(
        context['max_trip_distance_km'], PREFERRED_MAX_TRIP_KM
    )
    distances = planning['travel_distance']
    departure = planning['current_time'] + planning['departure_delay']

    candidates = [pid for pid in available_parcels(parcel)
                  if not is_hopeless(pid, parcel, planning)]
    by_location = defaultdict(list)
    for pid in candidates:
        by_location[parcel[pid]['delivery_location_id']].append(pid)

    def location_priority(item):
        location, parcel_ids = item
        outward = distances[HUB][location]
        inward = distances[location][HUB]
        earliest_deadline = min(parcel[pid]['delivery_window_end']
                                for pid in parcel_ids)
        # Latest departure for a direct trip, also allowing a return by 18:00.
        latest_departure = min(
            earliest_deadline - outward,
            planning['return_cutoff'] - outward - inward,
        )
        band = math.floor((latest_departure - departure) / URGENCY_BAND_MINUTES)
        distance_per_parcel = (outward + inward) / len(parcel_ids)
        return band, distance_per_parcel, location

    candidates = [pid
                  for _, parcel_ids in sorted(by_location.items(), key=location_priority)
                  for pid in sorted(parcel_ids, key=lambda x: urgency_key(x, parcel))]
    route = []
    for _ in range(RECONSIDER_PASSES):
        remaining = []
        for pid in candidates:
            trial = _insert_within_windows(route, pid, parcel, planning)
            if trial is None:
                remaining.append(pid)
            else:
                route = trial
        if not remaining or len(remaining) == len(candidates):
            break
        # Other insertions can add enough travel to fit a later window.
        candidates = remaining

    if not route:
        return []

    load = sum(parcel[pid]['size'] for pid in route)
    predicted_time = departure
    location = HUB
    slack = float('inf')
    for pid in route:
        record = parcel[pid]
        predicted_time += distances[location][record['delivery_location_id']]
        location = record['delivery_location_id']
        slack = min(slack, record['delivery_window_end'] - predicted_time)
    slack = min(slack, planning['return_cutoff']
                - predicted_time - distances[location][HUB])

    # Waiting is allowed only when this route can still leave next round.
    # The next planning round rebuilds the route using the new snapshot.
    if (load < MIN_DISPATCH_LOAD
            and slack >= PLANNING_INTERVAL_MINUTES + EPS):
        return []
    return route
