import json
from collections import defaultdict
import re

# Set defaults for each agency
AGENCY_METADATA = {
    "Angkot Kota Bandung": {
        "name": "Angkot Kota Bandung",
        "agencyId": "ABD",
        "mode": "angkot",
        "agencyUrl": "https://dishub.bandung.go.id/",
        "agencyTimezone": "Asia/Jakarta",
        "agencyLang": "id"
    }
    # Add more mappings if needed
}

def simplify_name(name):
    """Simplify name by removing prefixes and trimming whitespace."""
    name = re.sub(r"^(Commuter Line|Koridor \d+:?)\s*", "", name)
    return name.strip()

def detect_direction(name):
    """Infer directionId based on arrow direction or common patterns."""
    if "→" in name:
        return 0 if name.index("→") > 0 else 1
    if re.search(r"\bto\b|\b→\b", name, re.IGNORECASE):
        return 0
    return 1

def extract_full_route_code(name):
    """Extract full route code before the colon, e.g., '01A' from '01A: ...'."""
    match = re.match(r"([^\s:]+):", name)
    return match.group(1) if match else "00"

def group_bidirectional_routes(routes):
    """Group routes by color and full route code (e.g., 01A, 02B)."""
    groups = defaultdict(list)
    for route in routes:
        full_code = extract_full_route_code(route["name"])
        key = (route["color"], full_code)
        groups[key].append(route)
    return groups

def convert_old_to_new(old_data):
    new_data = {"categories": []}

    for category in old_data["categories"]:
        if "routes" not in category:
            print(f"⚠️  Skipping category '{category.get('name', 'Unknown')}' – missing 'routes' key.")
            continue

        agency_info = AGENCY_METADATA.get(category["name"], {
            "name": category["name"],
            "agencyId": category["name"][:3].upper(),
            "mode": "bus",
            "agencyUrl": "",
            "agencyTimezone": "Asia/Jakarta",
            "agencyLang": "id"
        })

        route_groups = []
        bidir_groups = group_bidirectional_routes(category["routes"])

        for (color, code), routes in bidir_groups.items():
            routes_sorted = sorted(routes, key=lambda r: detect_direction(r["name"]))
            route_objs = []
            for idx, r in enumerate(routes):
                route_objs.append({
                    "name": simplify_name(r["name"]),
                    "directionId": 0 if idx == 0 else 1,
                    "relationId": r["relationId"],
                    "first_departure": "04:00",  # placeholder
                    "last_departure": "18:00",  # placeholder
                    "trips": "85"  # placeholder
                })

            route_groups.append({
                "groupId": code,
                "name": f"{agency_info['name']} {code}",
                "color": color,
                "type": "fixed",
                "loop": "no",
                "routes": route_objs
            })

        new_data["categories"].append({
            "name": agency_info["name"],
            "agencyId": agency_info["agencyId"],
            "mode": agency_info["mode"],
            "agencyUrl": agency_info["agencyUrl"],
            "agencyTimezone": agency_info["agencyTimezone"],
            "agencyLang": agency_info["agencyLang"],
            "routeGroups": route_groups
        })

    return new_data

# === Run the conversion ===
if __name__ == "__main__":
    with open("convert-routes-json/routes.json", "r", encoding="utf-8") as f:
        old_routes = json.load(f)

    new_routes = convert_old_to_new(old_routes)

    with open("convert-routes-json/routes-new.json", "w", encoding="utf-8") as f:
        json.dump(new_routes, f, indent=2, ensure_ascii=False)

    print("✅ Converted routes.json saved as routes-new.json")
