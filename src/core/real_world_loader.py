import json
import math
import numpy as np

def load_osm_buildings(filepath: str, origin_lat: float, origin_lon: float, scale_factor: float = 1.0):
    """
    Parses OSM JSON format for buildings and converts them into 
    circular obstacles for the CARES simulator.
    
    Args:
        filepath: path to the JSON file
        origin_lat, origin_lon: Reference point for (0,0) in local coordinates
        scale_factor: To fit real lat/lon distances into the simulator's grid
        
    Returns:
        List of dicts: [{'x': float, 'y': float, 'radius': float}]
    """
    with open(filepath, 'r') as f:
        data = json.load(f)
        
    nodes = {}
    ways = []
    
    # First pass: collect nodes and ways
    for element in data.get('elements', []):
        if element['type'] == 'node':
            nodes[element['id']] = (element['lat'], element['lon'])
        elif element['type'] == 'way':
            if 'tags' in element and 'building' in element['tags']:
                ways.append(element['nodes'])
                
    obstacles = []
    
    # Earth radius in meters
    R = 6378137
    
    for way_nodes in ways:
        way_coords = []
        for nid in way_nodes:
            if nid in nodes:
                lat, lon = nodes[nid]
                # Equirectangular approximation
                x = (lon - origin_lon) * math.pi / 180.0 * R * math.cos(origin_lat * math.pi / 180.0)
                y = (lat - origin_lat) * math.pi / 180.0 * R
                way_coords.append((x * scale_factor, y * scale_factor))
                
        if not way_coords:
            continue
            
        # Compute bounding circle (centroid and max distance to vertex)
        cx = sum(p[0] for p in way_coords) / len(way_coords)
        cy = sum(p[1] for p in way_coords) / len(way_coords)
        
        max_dist = max(math.hypot(p[0]-cx, p[1]-cy) for p in way_coords)
        
        # Inflate slightly for safety margin
        radius = max(5.0, max_dist * 1.1)
        
        obstacles.append({
            'x': cx,
            'y': cy,
            'radius': radius
        })
        
    return obstacles

