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
SCHEDULE_DIR = os.path.join(REPO_ROOT, 'route-data', 'schedule')  # Directory for schedule CSVs
GTFS_DIR = os.path.join(REPO_ROOT, 'gtfs')
TIMEZONE = 'Asia/Jakarta'

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
    
    agencies = []
    route_groups = []
    all_routes = []
    
    for category in data['categories']:
        agency_id = category['agencyId']
        # Determine route type based on mode
        route_type = 2 if category['mode'] == 'train' else 3  # 2: Train, 3: Bus
            
        agencies.append({
            'agency_id': agency_id,
            'agency_name': category['name'],
            'agency_url': category['agencyUrl'],
            'agency_timezone': category['agencyTimezone'],
            'agency_lang': category['agencyLang']
        })
            
        for group in category['routeGroups']:
            if group.get('type') != 'fixed':
                continue
                
            route_groups.append({
                'agency_id': agency_id,
                'group_id': group['groupId'],
                'name': group['name'],
                'color': group['color'],
                'route_type': route_type,  # Set based on mode
                'loop': group.get('loop', 'no')  # Capture loop attribute
            })
            
            for route in group['routes']:
                route['agency_id'] = agency_id
                route['group_id'] = group['groupId']
                route['group_name'] = group['name']
                route['color'] = group['color']
                route['loop'] = group.get('loop', 'no')  # Add to route
                route['mode'] = category['mode']  # Add mode for later use
                all_routes.append(route)
    
    return agencies, route_groups, all_routes

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
    """Process route geometries into GTFS shapes with correct sequencing"""
    shapes = []
    
    for route in routes:
        route_id = route['relationId']
        ways_file = os.path.join(ROUTE_DATA_DIR, str(route_id), 'ways.geojson')
        
        if not os.path.exists(ways_file):
            print(f"Ways file not found for route {route_id}: {ways_file}")
            continue
            
        with open(ways_file) as f:
            data = json.load(f)
        
        # Extract coordinates while preserving feature order
        all_coords = []
        for feature in data['features']:
            geom = feature['geometry']
            geom_type = geom['type']
            
            if geom_type == 'LineString':
                # Preserve original coordinate order
                all_coords.append(geom['coordinates'])
            elif geom_type == 'MultiLineString':
                # Preserve order of linestrings and their coordinates
                for line in geom['coordinates']:
                    all_coords.append(line)
        
        # Flatten while maintaining sequence
        coords = []
        for feature_coords in all_coords:
            coords.extend(feature_coords)
        
        # Create shape records with cumulative distance
        shape_id = f"shape_{route_id}"
        cumulative_dist = 0.0
        prev_lon, prev_lat = None, None
        
        for seq, coord in enumerate(coords):
            lon, lat = coord[0], coord[1]
            
            if prev_lon is not None:
                segment_dist = haversine(prev_lon, prev_lat, lon, lat)
                cumulative_dist += segment_dist
            
            shapes.append({
                'shape_id': shape_id,
                'shape_pt_lon': lon,
                'shape_pt_lat': lat,
                'shape_pt_sequence': seq + 1,
                'shape_dist_traveled': round(cumulative_dist, 6)
            })
            
            prev_lon, prev_lat = lon, lat
        
        # Store shape ID for trip assignment
        route['shape_id'] = shape_id
    
    return shapes

def generate_trips(routes):
    """Generate trips and stop times with block_id support"""
    trips = []
    stop_times = []
    
    # Track trip counts per direction per group (for bus only)
    group_direction_counts = defaultdict(lambda: defaultdict(int))
    
    for route in routes:
        route_id = route['relationId']
        agency_id = route['agency_id']
        group_id = route['group_id']
        direction = route['directionId']
        
        # Process train routes differently using schedule CSV
        if route.get('mode') == 'train':
            # Build CSV path: route-data/schedule/{agencyId}_{direction}.csv
            csv_file = os.path.join(SCHEDULE_DIR, f"{agency_id}_{direction}.csv")
            
            if not os.path.exists(csv_file):
                print(f"Schedule CSV not found for {agency_id} direction {direction}: {csv_file}")
                continue
            
            # Read CSV data
            with open(csv_file, 'r', newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                # FIRST row is stop IDs, SECOND row is A/D indicators
                stop_ids = next(reader)     # First row: stop IDs
                event_types = next(reader)   # Second row: A/D indicators
                
                # Validate header rows
                if len(event_types) < 2 or len(stop_ids) < 2:
                    print(f"Invalid header rows in {csv_file}")
                    continue
                
                # Process each trip row
                for row in reader:
                    if not row or row[0].strip() == '':
                        continue
                    
                    # Check if this row belongs to the current route
                    if row[0] != str(route_id):
                        continue
                    
                    trip_num = row[1]
                    trip_id = f"t-{agency_id}{group_id}{trip_num}"
                    
                    # Block ID for looped routes
                    block_id = ""
                    if route.get('loop', 'no') == 'yes':
                        block_id = f"{agency_id}{group_id}{trip_num}"
                    
                    # Add trip
                    trips.append({
                        'route_id': group_id,
                        'trip_id': trip_id,
                        'service_id': 'everyday',
                        'trip_headsign': route['name'],
                        'direction_id': direction,
                        'shape_id': route.get('shape_id', ''),
                        'block_id': block_id
                    })
                    
                    # Process stop times for this trip
                    stop_seq = 1
                    # Process columns in pairs (each stop has two columns: arrival and departure)
                    for col_idx in range(2, len(row), 2):
                        # Ensure we have a pair of columns
                        if col_idx + 1 >= len(row):
                            break
                        
                        # Get stop ID from header (both columns should have same stop ID)
                        stop_id = stop_ids[col_idx] if col_idx < len(stop_ids) else None
                        if not stop_id:
                            continue
                            
                        # Get times for arrival and departure
                        arrival_str = row[col_idx].strip()
                        departure_str = row[col_idx + 1].strip()
                        
                        # Skip if both times are empty
                        if not arrival_str and not departure_str:
                            continue
                            
                        # If one time is missing, use the available one for both
                        if not arrival_str:
                            arrival_str = departure_str
                        if not departure_str:
                            departure_str = arrival_str
                            
                        # Convert to HH:MM:SS format
                        arrival_time = f"{arrival_str}:00"
                        departure_time = f"{departure_str}:00"
                        
                        stop_times.append({
                            'trip_id': trip_id,
                            'stop_id': stop_id,
                            'stop_sequence': stop_seq,
                            'arrival_time': arrival_time,
                            'departure_time': departure_time,
                            'pickup_type': 0,
                            'drop_off_type': 0
                        })
                        stop_seq += 1
        
        # Process bus routes normally
        else:
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
                dist = max(dist, 0.01)  # At least 10 meters
                speed = 30 if dist <= 5 else 55
                segment_times.append((dist / speed) * 3600)  # in seconds
            
            # Calculate cumulative travel times
            cumulative_travel = [0]
            for i in range(1, len(stops)):
                cumulative_travel.append(cumulative_travel[-1] + segment_times[i])
            
            # Get number of trips
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

            # Get current trip count for this direction
            current_count = group_direction_counts[group_id][direction]
            
            # Generate trips
            for idx in range(num_trips):
                # Calculate the trip number within this direction
                trip_num = current_count + idx + 1
                trip_start = start_sec + idx * headway_sec
                
                # Format trip ID: t-{agency_id}{group_id}{direction}{trip_num}
                trip_id = f"t-{agency_id}{group_id}{direction}{trip_num}"
                
                # Create block ID: {agency_id}{group_id}{trip_num} (without direction)
                block_id = ""
                if route['loop'] == 'yes':
                    block_id = f"{agency_id}{group_id}{trip_num}"
                
                trips.append({
                    'route_id': group_id,
                    'trip_id': trip_id,
                    'service_id': 'everyday',
                    'trip_headsign': route['name'],
                    'direction_id': direction,
                    'shape_id': route.get('shape_id', ''),
                    'block_id': block_id
                })
                
                # Calculate stop times
                for seq in range(len(stops)):
                    arrival_sec = trip_start + cumulative_travel[seq] + (seq * 10)
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
            
            # Update the trip count for this direction
            group_direction_counts[group_id][direction] += num_trips
    
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
    print("Starting GTFS generation...")
    print(f"Repository root: {REPO_ROOT}")
    print(f"Routes JSON path: {ROUTES_JSON}")
    
    # Process data
    agencies, route_groups, routes = process_routes()
    stops = process_stops(routes)
    shapes = process_shapes(routes)
    trips, stop_times = generate_trips(routes)
    
    # Generate GTFS files
    write_gtfs(agencies, 'agency.txt', 
               ['agency_id', 'agency_name', 'agency_url', 'agency_timezone', 'agency_lang'])
    
    write_gtfs([
        {
            'route_id': group['group_id'],
            'agency_id': group['agency_id'],
            'route_short_name': group['group_id'],  # Koridor number
            'route_long_name': group['name'],
            'route_type': group['route_type'],
            'route_color': group['color'].lstrip('#')
        } for group in route_groups
    ], 'routes.txt', 
    ['route_id', 'agency_id', 'route_short_name', 'route_long_name', 'route_type', 'route_color'])
    
    write_gtfs(trips, 'trips.txt', 
               ['route_id', 'trip_id', 'service_id', 'trip_headsign', 'direction_id', 'shape_id', 'block_id'])
    
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
    