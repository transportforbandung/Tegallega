import json
import os
import simplekml

def sanitize_filename(name):
    return "".join([c if c.isalnum() or c in (' ', '-', '_') else '_' for c in name]).strip()

def convert_hex_to_kml_color(hex_color):
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 3:
        hex_color = ''.join([c * 2 for c in hex_color])
    elif len(hex_color) != 6:
        hex_color = '000000'
    rr, gg, bb = hex_color[0:2], hex_color[2:4], hex_color[4:6]
    return f'ff{bb}{gg}{rr}'

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base_dir, '..', 'route-data')
    route_data_dir = os.path.join(data_dir, 'geojson')
    routes_json_path = os.path.join(data_dir, 'routes.json')
    output_dir = os.path.join(data_dir, 'kml-named')
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

            merged_features = []
            for filename in os.listdir(route_dir):
                if filename.endswith('.geojson'):
                    with open(os.path.join(route_dir, filename), 'r') as geojson_file:
                        data = json.load(geojson_file)
                        if data['type'] == 'FeatureCollection':
                            merged_features.extend(data['features'])
                        elif data['type'] == 'Feature':
                            merged_features.append(data)

            if not merged_features:
                print(f"No features for {route_name}")
                continue

            kml = simplekml.Kml()
            kml_color = convert_hex_to_kml_color(color)

            # Add ExtendedData to the KML document
            kml.document.extendeddata = simplekml.ExtendedData()
            kml.document.extendeddata.newdata(name="route-name", value=route_name)
            kml.document.extendeddata.newdata(name="source", value="Transport for Bandung")

            for feature in merged_features:
                geom = feature.get('geometry', {})
                props = feature.get('properties', {})
                geom_type = geom.get('type')
                coords = geom.get('coordinates', [])

                if geom_type in ['LineString', 'MultiLineString']:
                    name = props.get('name', 'Route Segment')
                    if geom_type == 'LineString':
                        ls = kml.newlinestring(name=name)
                        ls.coords = [(lon, lat) for lon, lat in coords]
                    else:
                        feature_kml = kml.newfeature(name=name)
                        multi = feature_kml.newmultigeometry()
                        for line in coords:
                            multi.newlinestring(coords=[(lon, lat) for lon, lat in line])
                    kml_feature = ls if geom_type == 'LineString' else feature_kml
                    kml_feature.style.linestyle.color = kml_color
                    kml_feature.style.linestyle.width = 4

                elif geom_type == 'Point':
                    pt = kml.newpoint(name=props.get('name', 'Stop'))
                    pt.coords = [(coords[0], coords[1])]
                    pt.style.iconstyle.icon.href = 'http://maps.google.com/mapfiles/kml/pushpin/ylw-pushpin.png'

            safe_name = f"{sanitize_filename(route_name)}.kml"
            kml.save(os.path.join(output_dir, safe_name))

if __name__ == '__main__':
    main()
