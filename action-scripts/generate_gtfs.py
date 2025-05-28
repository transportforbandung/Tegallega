import os
import json
import csv
from collections import defaultdict

# Configuration
ROUTES_JSON = 'routes.json'
ROUTE_DATA_DIR = 'route-data'
GTFS_DIR = 'gtfs'
TIMEZONE = 'Asia/Jakarta'
AGENCY_NAME = 'Metro Jabar Trans'
AGENCY_URL = 'https://instagram.com/brt.metrojabartrans'
AGENCY_LANG = 'id'

def process_routes():
    """Process routes.json and return enhanced route data"""
    with open(ROUTES_JSON) as f:
        data = json.load(f)
    
    route_groups = []
    all_routes = []
    
    for category in data['categories']:
        # Focus only on Metro Jabar Trans
        if category['name'] != "Metro Jabar Trans":
            continue
            
        for group in category['routeGroups']:
            # Skip non-fixed routes (for future GTFS-flex)
            if group.get('type') != 'fixed':
                continue
                
            # Create route group entry
            route_groups.append({
                'group_id': group['groupId'],
                'name': group['name'],
                'color': group['color'],
                'route_type': 3  # Bus
            })
            
            # Process each route direction
            for route in group['routes']:
                route['group_id'] = group['groupId']
                route['group_name'] = group['name']
                route['color'] = group['color']
                all_routes.append(route)
    
    return all_routes, route_groups

def process_stops(routes):
    """Collect all stops from all routes with deduplication"""
    all_stops = {}
    stop_counter = 1
    
    for route in routes:
        route_id = route['relationId']
        stop_file = os.path.join(ROUTE_DATA_DIR, route_id, 'stops.geojson')
        
        if not os.path.exists(stop_file):
            print(f"Stop file not found for route {route_id}: {stop_file}")
            continue
            
        with open(stop_file) as f:
            data = json.load(f)
        
        for feature in data['features']:
            props = feature['properties']
            geom = feature['geometry']
            coords = geom['coordinates']
            
            # Create unique stop ID using OSM ID or generate new
            stop_id = props.get('id', f"stop_{stop_counter}")
            stop_counter += 1
            
            if stop_id not in all_stops:
                all_stops[stop_id] = {
                    'stop_id': stop_id,
                    'stop_name': props.get('name', f"Stop {stop_id}"),
                    'stop_lat': coords[1],
                    'stop_lon': coords[0],
                    'location_type': 0,
                    'wheelchair_boarding': 1 if props.get('wheelchair') == 'yes' else 0
                }
    
    return all_stops

def process_shapes(routes):
    """Process route geometries into GTFS shapes"""
    shapes = []
    
    for route in routes:
        route_id = route['relationId']
        # CORRECTED FILENAME: ways.geojson instead of route_ways.geojson
        ways_file = os.path.join(ROUTE_DATA_DIR, route_id, 'ways.geojson')
        
        if not os.path.exists(ways_file):
            print(f"Ways file not found for route {route_id}: {ways_file}")
            continue
            
        with open(ways_file) as f:
            data = json.load(f)
        
        # Extract coordinates from GeoJSON
        coords = []
        for feature in data['features']:
            geom_type = feature['geometry']['type']
            if geom_type == 'LineString':
                coords.extend(feature['geometry']['coordinates'])
            elif geom_type == 'MultiLineString':
                for line in feature['geometry']['coordinates']:
                    coords.extend(line)
        
        # Create shape records
        shape_id = f"shape_{route_id}"
        
        for seq, coord in enumerate(coords):
            shapes.append({
                'shape_id': shape_id,
                'shape_pt_lon': coord[0],
                'shape_pt_lat': coord[1],
                'shape_pt_sequence': seq + 1,
                'shape_dist_traveled': None
            })
        
        # Store shape ID for trip assignment
        route['shape_id'] = shape_id
    
    return shapes

def generate_trips(routes):
    """Generate trips and stop times with placeholder times"""
    trips = []
    stop_times = []
    trip_counter = 1
    
    for route in routes:
        route_id = route['relationId']
        stop_file = os.path.join(ROUTE_DATA_DIR, route_id, 'stops.geojson')
        
        if not os.path.exists(stop_file):
            print(f"Stop file not found for trip generation: {stop_file}")
            continue
            
        with open(stop_file) as f:
            data = json.load(f)
        
        # Create trip
        trip_id = f"trip_{trip_counter}"
        trip_counter += 1
        
        trips.append({
            'route_id': route['group_id'],
            'trip_id': trip_id,
            'service_id': 'weekday',
            'trip_headsign': route['name'],
            'direction_id': route['directionId'],
            'shape_id': route.get('shape_id', '')  # Will be empty if shape not processed
        })
        
        # Create stop times with placeholder times
        for seq, feature in enumerate(data['features']):
            props = feature['properties']
            stop_id = props.get('id', f"stop_{seq}")
            
            stop_times.append({
                'trip_id': trip_id,
                'stop_id': stop_id,
                'stop_sequence': seq + 1,
                'arrival_time': '08:00:00',  # Placeholder
                'departure_time': '08:00:00',  # Placeholder
                'pickup_type': 0,
                'drop_off_type': 0
            })
    
    return trips, stop_times

# ... [Rest of the functions remain unchanged: create_calendar, create_agency, write_gtfs, main] ...

if __name__ == "__main__":
    main()
