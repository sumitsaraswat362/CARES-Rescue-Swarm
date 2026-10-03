"""Received-beacon path validation; no simulator graph access."""
import math


def valid_route(route, source, receiver, stamp, now, timeout):
    return (isinstance(route, (list, tuple)) and 0 < len(route) <= 256
            and all(type(i) is int and i >= -1 for i in route)
            and route[0] == source and route[-1] == -1
            and len(set(route)) == len(route) and receiver not in route
            and isinstance(stamp, (int, float)) and math.isfinite(stamp)
            and 0 <= now - stamp <= timeout)


def choose_route(neighbors, receiver, now, timeout):
    options = []
    retiring={source for source,data in neighbors.items() if 0<=now-data['seen']<=timeout
              and (data.get('retiring') or (data.get('request') and data['request'].get('candidate') is not None))}
    for source, data in neighbors.items():
        route, stamp = data.get('route', ()), data.get('route_at', -math.inf)
        if 0 <= now - data['seen'] <= timeout and valid_route(route, source, receiver, stamp, now, timeout):
            options.append(((receiver,) + tuple(route), stamp))
    # Equal-length paths have a total ordering independent of packet arrival order.
    return min(options, key=lambda pair: (len(set(pair[0]) & retiring), len(pair[0]), pair[0])) if options else ((), -1e9)
