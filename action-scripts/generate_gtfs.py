import os
import json
import csv
import math
from collections import defaultdict

# Get the absolute path to the repository root
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Configuration (using absolute paths)
ROUTES_JSON = os.path.join(REPO_ROOT, 'routes.json')
ROUTE_DATA_DIR = os.path.join(REPO_ROOT, 'route-data', 'geojson')
GTFS_DIR = os.path.join(REPO_ROOT, 'gtfs')
TIMEZONE = 'Asia/Jakarta'
AGENCY_NAME = 'Metro Jabar Trans'
AGENCY_URL = 'https://instagram.com/brt.metrojabartrans'
AGENCY_LANG = 'id'

# Helper functions for distance and time calculations
def haversine(lon1, lat1, lon2, lat2):
    """Calculate distance between two geo-coordinates (in km)"""
    lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    return 6371 * 2 * math.asin(math.sqrt(a))  # Earth radius=6371km

def time_str_to_seconds(time_str):
    """Convert HH:MM string to seconds since midnight"""
    h, m = map(int, time_str.split(':'))
    return h * 3600 + m * 60

def seconds_to_time_str(total_seconds):
    """Convert seconds to HH:MM:SS format"""
    # Round to nearest second before conversion
    total_seconds = round(total_seconds)
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d}"

def process_routes():
    """Process routes.json and return enhanced route data"""
    with open(ROUTES_JSON) as f:
        data = json.load(f)
    
    route_groups = []
    all_routes = []
    
    for category in data['categories']:
        if category['name'] != "Metro Jabar Trans":
            continue
            
        for group in category['routeGroups']:
            if group.get('type') != 'fixed':
                continue
                
            route_groups.append({
                'group_id': group['groupId'],
                'name': group['name'],
                'color': group['color'],
                'route_type': 3,  # Bus
                'loop': group.get('loop', 'no')  # Capture loop attribute
            })
            
            for route in group['routes']:
                route['group_id'] = group['groupId']
                route['group_name'] = group['name']
                route['color'] = group['color']
                route['loop'] = group.get('loop', 'no')  # Add to route
                all_routes.append(route)
    
    return all_routes, route_groups

def process_stops(routes):
    """Collect all stops from all routes with deduplication"""
    all_stops = {}
    stop_counter = 1
    
    for route in routes:
        route_id = route['relationId']
        stop_file = os.path.join(ROUTE_DATA_DIR, str(route_id), 'stops.geojson')
        
        if not os.path.exists(stop_file):
            print(f"Stop file not found for route {route_id}: {stop_file}")
            # Print parent directory contents for debugging
            parent_dir = os.path.dirname(stop_file)
            if os.path.exists(parent_dir):
                print(f"Directory contents: {os.listdir(parent_dir)}")
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
        ways_file = os.path.join(ROUTE_DATA_DIR, str(route_id), 'ways.geojson')
        
        if not os.path.exists(ways_file):
            print(f"Ways file not found for route {route_id}: {ways_file}")
            # Print parent directory contents for debugging
            parent_dir = os.path.dirname(ways_file)
            if os.path.exists(parent_dir):
                print(f"Directory contents: {os.listdir(parent_dir)}")
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
    """Generate trips and stop times with block_id support"""
    trips = []
    stop_times = []
    
    # Track last trip index per group for block pairing
    group_trip_counts = defaultdict(int)
    
    for route in routes:
        route_id = route['relationId']
        stop_file = os.path.join(ROUTE_DATA_DIR, str(route_id), 'stops.geojson')
        
        if not os.path.exists(stop_file):
            print(f"Stop file not found for trip generation: {stop_file}")
            continue
            
        with open(stop_file) as f:
            stop_data = json.load(f)
        
        # Extract stop sequence with coordinates
        stops = []
        for feature in stop_data['features']:
            props = feature['properties']
            coords = feature['geometry']['coordinates']
            stops.append({
                'stop_id': props.get('id', f"stop_{len(stops)+1}"),
                'lon': coords[0],
                'lat': coords[1]
            })
        
        # Precompute segment times between stops
        segment_times = [0]  # Start with 0 for first stop
        for i in range(1, len(stops)):
            dist = haversine(
                stops[i-1]['lon'], stops[i-1]['lat'],
                stops[i]['lon'], stops[i]['lat']
            )
            # Add minimum distance to avoid division by zero
            dist = max(dist, 0.01)  # At least 10 meters
            speed = 30 if dist <= 5 else 55
            segment_times.append((dist / speed) * 3600)  # in seconds
        
        # Calculate cumulative travel times (excluding dwell)
        cumulative_travel = [0]
        for i in range(1, len(stops)):
            cumulative_travel.append(cumulative_travel[-1] + segment_times[i])
        
        # Get number of trips from route configuration
        try:
            num_trips = int(route.get('trips', '0'))
        except ValueError:
            num_trips = 0
        
        if num_trips < 1:
            continue
            
        # Parse operational times
        start_sec = time_str_to_seconds(route['first_departure'])
        end_sec = time_str_to_seconds(route['last_departure'])
        headway_sec = (end_sec - start_sec) / (num_trips - 1) if num_trips > 1 else 0

        # Generate trips
        for idx in range(num_trips):
            trip_index = group_trip_counts[route['group_id']] + 1
            group_trip_counts[route['group_id']] = trip_index
            
            trip_id = f"t-MJT{route['group_id']}{route['directionId']}{trip_index}"
            
            # Create block_id for loop routes
            block_id = ""
            if route['loop'] == 'yes':
                # Format: MJT{group_id}{trip_index}
                block_id = f"MJT{route['group_id']}{trip_index}"
            
            trips.append({
                'route_id': route['group_id'],
                'trip_id': trip_id,
                'service_id': 'everyday',
                'trip_headsign': route['name'],
                'direction_id': route['directionId'],
                'shape_id': route.get('shape_id', ''),
                'block_id': block_id  # Add block_id field
            })
            
            # Calculate stop times
            for seq in range(len(stops)):
                # Arrival time = trip start + travel to stop + dwell from previous stops
                arrival_sec = trip_start + cumulative_travel[seq] + (seq * 10)
                # Departure time adds 10 seconds dwell time
                departure_sec = arrival_sec + 10
                
                stop_times.append({
                    'trip_id': trip_id,
                    'stop_id': stops[seq]['stop_id'],
                    'stop_sequence': seq + 1,
                    'arrival_time': seconds_to_time_str(arrival_sec),
                    'departure_time': seconds_to_time_str(departure_sec),
                    'pickup_type': 0,
                    'drop_off_type': 0
                })
    
    return trips, stop_times

def create_calendar():
    """Calendar for everyday service with unlimited end date"""
    return [{
        'service_id': 'everyday',
        'monday': 1,
        'tuesday': 1,
        'wednesday': 1,
        'thursday': 1,
        'friday': 1,
        'saturday': 1,
        'sunday': 1,
        'start_date': '20250101',  # Start from Jan 1, 2025
        'end_date': '20991231'     # End on Dec 31, 2099 (far future)
    }]

def create_agency():
    return [{
        'agency_id': 'MJT',
        'agency_name': AGENCY_NAME,
        'agency_url': AGENCY_URL,
        'agency_timezone': TIMEZONE,
        'agency_lang': AGENCY_LANG
    }]

def write_gtfs(data, filename, fieldnames):
    """Write GTFS CSV file"""
    os.makedirs(GTFS_DIR, exist_ok=True)
    output_path = os.path.join(GTFS_DIR, filename)
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        if not isinstance(data, list):
            data = list(data)
        writer.writerows(data)
    print(f"Created: {output_path}")

def main():
    print("Starting GTFS generation for Metro Jabar Trans...")
    print(f"Repository root: {REPO_ROOT}")
    print(f"Routes JSON path: {ROUTES_JSON}")
    
    # Process data
    routes, route_groups = process_routes()
    stops = process_stops(routes)
    shapes = process_shapes(routes)
    trips, stop_times = generate_trips(routes)
    
    # Generate GTFS files
    write_gtfs(create_agency(), 'agency.txt', 
               ['agency_id', 'agency_name', 'agency_url', 'agency_timezone', 'agency_lang'])
    
    write_gtfs([
        {
            'route_id': group['group_id'],
            'agency_id': 'MJT',
            'route_short_name': group['group_id'],  # Koridor number
            'route_long_name': group['name'],
            'route_type': group['route_type'],
            'route_color': group['color'].lstrip('#')
        } for group in route_groups
    ], 'routes.txt', 
    ['route_id', 'agency_id', 'route_short_name', 'route_long_name', 'route_type', 'route_color'])
    
    write_gtfs(trips, 'trips.txt', 
               ['route_id', 'trip_id', 'service_id', 'trip_headsign', 'direction_id', 'shape_id', 'block_id'])  # Added block_id
    
    write_gtfs(list(stops.values()), 'stops.txt', 
               ['stop_id', 'stop_name', 'stop_lat', 'stop_lon', 'location_type', 'wheelchair_boarding'])
    
    write_gtfs(stop_times, 'stop_times.txt', 
               ['trip_id', 'stop_id', 'stop_sequence', 'arrival_time', 'departure_time', 'pickup_type', 'drop_off_type'])
    
    write_gtfs(shapes, 'shapes.txt', 
               ['shape_id', 'shape_pt_lon', 'shape_pt_lat', 'shape_pt_sequence', 'shape_dist_traveled'])
    
    write_gtfs(create_calendar(), 'calendar.txt', 
               ['service_id', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday', 'start_date', 'end_date'])
    
    print(f"GTFS generated successfully in {GTFS_DIR}/ directory")
    print(f"Processed {len(route_groups)} route groups and {len(routes)} directions")
    print(f"Generated {len(trips)} trips and {len(stop_times)} stop times")

if __name__ == "__main__":
    main()
    
