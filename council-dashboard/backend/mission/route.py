"""Hazard-aware rover route across the segmented HiRISE scene (decision D13).

SAM 3.1 boulder and crater boxes (image pixels) are grown by the clearance (half the rover width, rover.width_m) and
rasterized onto a grid, so the rover centre keeps that distance from every detection. An 8-connected A* route crosses
the scene from the west edge to the east edge along the middle row; a diagonal step is allowed only when both cells it
passes between are free (no corner cutting). The detour factor (route length / straight length) scales the survey drive.
Limits: the route crosses the segmented window; it does not join equipment positions to work sites (the package has no
surveyed layout coordinates), no safety margin beyond the rover footprint is applied (none is published), and hazards
smaller than the image resolution are not detected.
"""
import heapq
import math

MAX_CELLS = 400  # grid resolution cap on the long side, to bound A* work


def grid(width, height, objects, grow_px=0.0):
    cell = max(1, math.ceil(max(width, height) / MAX_CELLS))
    cols, rows = math.ceil(width / cell), math.ceil(height / cell)
    blocked = [[False] * cols for _ in range(rows)]
    for o in objects:
        c0, c1 = max(0, int((o['left'] - grow_px) // cell)), min(cols - 1, int((o['right'] + grow_px) // cell))
        r0, r1 = max(0, int((o['top'] - grow_px) // cell)), min(rows - 1, int((o['bottom'] + grow_px) // cell))
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                blocked[r][c] = True
    return cell, blocked


def _nearest_free(blocked, r, c):
    for d in range(len(blocked)):
        for rr in (r - d, r + d):
            if 0 <= rr < len(blocked) and not blocked[rr][c]:
                return rr
    return None


def astar(blocked, start, goal):
    rows, cols = len(blocked), len(blocked[0])
    h = lambda p: math.hypot(p[0] - goal[0], p[1] - goal[1])
    best = {start: 0.0}
    came = {}
    frontier = [(h(start), start)]
    steps = [(dr, dc, math.hypot(dr, dc)) for dr in (-1, 0, 1) for dc in (-1, 0, 1) if dr or dc]
    while frontier:
        _, p = heapq.heappop(frontier)
        if p == goal:
            path = [p]
            while p in came:
                p = came[p]
                path.append(p)
            return best[goal], path[::-1]
        for dr, dc, w in steps:
            q = (p[0] + dr, p[1] + dc)
            if not (0 <= q[0] < rows and 0 <= q[1] < cols) or blocked[q[0]][q[1]]:
                continue
            if dr and dc and (blocked[p[0] + dr][p[1]] or blocked[p[0]][p[1] + dc]):
                continue  # no corner cutting between touching blocked cells
            g = best[p] + w
            if g < best.get(q, math.inf):
                best[q] = g
                came[q] = p
                heapq.heappush(frontier, (g + h(q), q))
    return None, None


def plan(width, height, m_per_px, segmentations, clearance_m):
    objects = [o for seg in segmentations for o in seg['objects']]
    cell, blocked = grid(width, height, objects, clearance_m / m_per_px)
    rows, cols = len(blocked), len(blocked[0])
    mid = rows // 2
    r0, r1 = _nearest_free([[row[0]] for row in blocked], mid, 0), _nearest_free([[row[-1]] for row in blocked], mid, 0)
    if r0 is None or r1 is None:
        return {'status': 'no traversable edge cell', 'detour_factor': None, 'clearance_m': clearance_m}
    length, path = astar(blocked, (r0, 0), (r1, cols - 1))
    straight = math.hypot(r1 - r0, cols - 1)
    blocked_fraction = sum(map(sum, blocked)) / (rows * cols)
    if path is None:
        return {'status': 'no hazard-free route across the scene', 'detour_factor': None, 'blocked_fraction': round(blocked_fraction, 4), 'clearance_m': clearance_m}
    step = max(1, len(path) // 200)
    return {'status': 'route found', 'detour_factor': round(length / straight, 4), 'route_m': round(length * cell * m_per_px, 1),
            'straight_m': round(straight * cell * m_per_px, 1), 'grid_cell_m': round(cell * m_per_px, 2), 'obstacles': len(objects),
            'blocked_fraction': round(blocked_fraction, 4), 'clearance_m': clearance_m,
            'path_px': [[(c + 0.5) * cell, (r + 0.5) * cell] for r, c in path[::step] + [path[-1]]],
            'method': f'A* (8-connected, no corner cutting) over SAM 3.1 boulder and crater boxes grown by {clearance_m} m (half the rover width)'}
