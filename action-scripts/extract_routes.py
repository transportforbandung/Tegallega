from bs4 import BeautifulSoup
import json
import os
import sys

def extract_routes(html_file, output_file):
    with open(html_file, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')

    categories = []
    
    # Find all collapsible route sections
    for collapsible in soup.select('.route-map-collapsible'):
        category_name = collapsible.select_one('.route-map-collapsible-bar span').text.strip()
        
        routes = []
        for checkbox in collapsible.select('.route-option input[type="checkbox"]'):
            route_data = {
                'name': checkbox.next_sibling.strip(),
                'relationId': checkbox['data-relation-id'],
                'color': checkbox['data-route-color'],
                'type': checkbox['data-display-type']
            }
            routes.append(route_data)
        
        if routes:
            categories.append({
                'name': category_name,
                'routes': routes
            })
    
    # Create output directory if not exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({'categories': categories}, f, indent=2, ensure_ascii=False)

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python extract_routes.py <input_html> <output_json>")
        sys.exit(1)
        
    extract_routes(sys.argv[1], sys.argv[2])
