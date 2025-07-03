import json
import re
from collections import defaultdict

# === Agency metadata defaults ===
AGENCY_METADATA = {
    "Metro Jabar Trans": {
        "name": "Metro Jabar Trans",
        "agencyId": "MJT",
        "mode": "bus",
        "agencyUrl": "https://instagram.com/brt.metrojabartrans",
        "agencyTimezone": "Asia/Jakarta",
        "agencyLang": "id"
    },
    "Trans Metro Bandung": {
        "name": "Trans Metro Bandung",
        "agencyId": "TMB",
        "mode": "bus",
        "agencyUrl": "https://uptangkutan-bandung.id/",
        "agencyTimezone": "Asia/Jakarta",
        "agencyLang": "id"
    },
    "Bus Kota Damri": {
        "name": "Bus Kota Damri",
        "agencyId": "Damri",
        "mode": "bus",
        "agencyUrl": "https://damri.co.id/",
        "agencyTimezone": "Asia/Jakarta",
        "agencyLang": "id"
    },
    "Angkot Kota Bandung": {
        "name": "Angkot Kota Bandung",
        "agencyId": "ABD",
        "mode": "angkot",
        "agencyUrl": "https://dishub.bandung.go.id/",
        "agencyTimezone": "Asia/Jakarta",
        "agencyLang": "id"
    },
    "Angkot Kota Cimahi": {
        "name": "Angkot Kota Cimahi",
        "agencyId": "AC",
        "mode": "angkot",
        "agencyUrl": "",
        "agencyTimezone": "Asia/Jakarta",
        "agencyLang": "id"
    },
    "Angkot Kabupaten Bandung Barat": {
        "name": "Angkot Kabupaten Bandung Barat",
        "agencyId": "AKBB",
        "mode": "angkot",
        "agencyUrl": "",
        "agencyTimezone": "Asia/Jakarta",
        "agencyLang": "id"
    },
    "Angkot Kabupaten Bandung": {
        "name": "Angkot Kabupaten Bandung",
        "agencyId": "AKB",
        "mode": "angkot",
        "agencyUrl": "",
        "agencyTimezone": "Asia/Jakarta",
        "agencyLang": "id"
    },
    "Angkot Lintas Wilayah (AKDP)": {
        "name": "Angkot Lintas Wilayah (AKDP)",
        "agencyId": "AKDP",
        "mode": "angkot",
        "agencyUrl": "",
        "agencyTimezone": "Asia/Jakarta",
        "agencyLang": "id"
    }
}

# === Helper functions ===

def simplify_name(name):
    name = re.sub(r"^(Commuter Line|Koridor \d+:?)\s*", "", name)
    return name.strip()

def detect_direction(name):
    if "→" in name:
        return 0 if name.index("→") > 0 else 1
    return 1

def extract_code(name):
    """Extract route code before colon. If it has a space, use the last word."""
    if ":" in name:
        prefix = name.split(":")[0].strip()
        return prefix.split()[-1]  # Only keep last word
    return None

def strip_via(name):
    return re.sub(r"\s+via\s+.*", "", name)

def get_origin_dest_via(name):
    """Extract origin, destination, and via (if any)"""
    via_match = re.search(r"\s+via\s+(.*)", name)
    via = via_match.group(1).strip() if via_match else None

    name_wo_via = strip_via(name)
    parts = name_wo_via.split("→")
    if len(parts) == 2:
        origin = parts[0].strip()
        dest = parts[1].strip()
        return origin, dest, via
    return None, None, via

def group_routes(routes):
    code_groups = defaultdict(list)
    custom_groups = []
    used = set()

    for i, route in enumerate(routes):
        name = route["name"]
        code = extract_code(name)

        if code:
            key = (route["color"], code)
            code_groups[key].append(route)
        else:
            if i in used:
                continue
            origin_i, dest_i, via_i = get_origin_dest_via(name)
            if not origin_i or not dest_i:
                continue

            for j, other in enumerate(routes):
                if i == j or j in used:
                    continue
                origin_j, dest_j, via_j = get_origin_dest_via(other["name"])

                if origin_j == dest_i and dest_j == origin_i:
                    # Match only if both have same 'via' or both None
                    if via_i == via_j:
                        custom_groups.append(([route, other], route["color"], name.strip()))
                        used.add(i)
                        used.add(j)
                        break

    return code_groups, custom_groups

# === Main conversion function ===

def convert_old_to_new(old_data):
    new_data = {"categories": []}

    for category in old_data["categories"]:
        if "routes" not in category:
            continue

        agency_info = {
            **{
                "agencyUrl": "",
                "agencyTimezone": "Asia/Jakarta",
                "agencyLang": "id",
                "mode": "bus"
            },
            **AGENCY_METADATA.get(category["name"], {
                "name": category["name"],
                "agencyId": category["name"][:3].upper()
            })
        }

        route_groups = []
        code_groups, custom_groups = group_routes(category["routes"])

        for (color, code), group in code_groups.items():
            sorted_group = sorted(group, key=lambda r: detect_direction(r["name"]))
            route_objs = []
            for idx, r in enumerate(sorted_group):
                route_objs.append({
                    "name": simplify_name(r["name"]),
                    "directionId": 0 if idx == 0 else 1,
                    "relationId": r["relationId"],
                    "first_departure": "04:00",
                    "last_departure": "18:00",
                    "trips": "85"
                })
            route_groups.append({
                "groupId": code,
                "name": f"{agency_info['name']} {code}",
                "color": color,
                "type": "fixed",
                "loop": "no",
                "routes": route_objs
            })

        for group, color, base_name in custom_groups:
            route_objs = []
            for idx, r in enumerate(group):
                route_objs.append({
                    "name": simplify_name(r["name"]),
                    "directionId": 0 if idx == 0 else 1,
                    "relationId": r["relationId"],
                    "first_departure": "04:00",
                    "last_departure": "18:00",
                    "trips": "85"
                })
            route_groups.append({
                "groupId": base_name,
                "name": base_name,
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

# === Execute the script ===

if __name__ == "__main__":
    with open("convert-routes-json/routes.json", "r", encoding="utf-8") as f:
        old_routes = json.load(f)

    new_routes = convert_old_to_new(old_routes)

    with open("convert-routes-json/routes-new.json", "w", encoding="utf-8") as f:
        json.dump(new_routes, f, indent=2, ensure_ascii=False)

    print("✅ Converted routes.json saved as routes-new.json")
