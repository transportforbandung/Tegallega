import json
import os
import geopandas as gpd
from shapely.geometry import shape

def sanitize_filename(name):
    return "".join([c if c.isalnum() or c in (' ', '-', '_') else '_' for c in name]).strip()

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base_dir, '..', 'route-data')
    route_data_dir = os.path.join(data_dir, 'geojson')
    routes_json_path = os.path.join(data_dir, 'routes.json')
    output_dir = os.path.join(data_dir, 'shp-named')
    os.makedirs(output_dir, exist_ok=True)

    with open(routes_json_path, 'r') as f:
        routes_data = json.load(f)

    for category in routes_data['categories']:
        for route in category['routes']:
            relation_id = route['relationId']
            route_name = route['name']
            color = route['color']
            route_dir = os.path.join(route_data_dir, relation_id)

            if not os.path.exists(route_dir):
                print(f"Skipping missing directory: {route_dir}")
                continue

            # Process GeoJSON files
            line_features = []
            point_features = []
            
            for filename in os.listdir(route_dir):
                if filename.endswith('.geojson'):
                    with open(os.path.join(route_dir, filename)) as f:
                        data = json.load(f)
                        features = data['features'] if data['type'] == 'FeatureCollection' else [data]
                        
                        for feature in features:
                            geom = feature['geometry']
                            feature['geometry'] = shape(geom)
                            props = feature['properties']
                            
                            # Add route metadata
                            props.update({
                                "route_name": route_name,
                                "color": color,
                                "source": "Transport for Bandung"
                            })
                            
                            if geom['type'] in ['LineString', 'MultiLineString']:
                                line_features.append(feature)
                            elif geom['type'] == 'Point':
                                point_features.append(feature)

            # Create output directory
            sanitized_name = sanitize_filename(route_name)
            route_output_dir = os.path.join(output_dir, sanitized_name)
            os.makedirs(route_output_dir, exist_ok=True)

            # Save LineString features
            if line_features:
                gdf = gpd.GeoDataFrame.from_features(line_features)
                gdf.crs = 'EPSG:4326'  # WGS84 coordinate system
                gdf.to_file(os.path.join(route_output_dir, 'route_lines.shp'))

            # Save Point features
            if point_features:
                gdf = gpd.GeoDataFrame.from_features(point_features)
                gdf.crs = 'EPSG:4326'
                gdf.to_file(os.path.join(route_output_dir, 'stops.shp'))

if __name__ == '__main__':
    main()