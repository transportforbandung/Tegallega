const fs = require('fs');
const path = require('path');
const { mkdirp } = require('mkdirp');
const axios = require('axios');

// Load route-index.geojson
const routeIndexPath = path.join(__dirname, '..', 'data', 'route-index.geojson');

// Validate if the file exists and is readable
if (!fs.existsSync(routeIndexPath)) {
  console.error(`Error: File not found at ${routeIndexPath}`);
  process.exit(1);
}

let routeData;
try {
  routeData = JSON.parse(fs.readFileSync(routeIndexPath, 'utf-8'));
} catch (error) {
  console.error(`Error: Failed to parse route-index.geojson.`, error.message);
  process.exit(1);
}

// Validate if the routes array exists
if (!routeData.routes || !Array.isArray(routeData.routes)) {
  console.error(`Error: Invalid route-index.geojson format. Expected a "routes" array.`);
  process.exit(1);
}

// Collect all unique routes by relation_id
const routes = routeData.routes.map(route => ({
  relationId: route.relation_id,
  displayType: route.display_type,
  routeColor: route.route_color,
  routeName: route.route_name
}));

const uniqueRoutes = [...new Map(routes.map(route => [route.relationId, route])).values()];

// Overpass API query function with retry logic
async function overpassQuery(query, retries = 3, delay = 2000) {
  const url = `https://overpass-api.de/api/interpreter?data=${encodeURIComponent(query)}`;
  for (let i = 0; i < retries; i++) {
    try {
      console.log(`Executing Overpass query (attempt ${i + 1}/${retries}): ${query}`);
      await new Promise(resolve => setTimeout(resolve, delay));
      const response = await axios.get(url, { timeout: 10000 });
      return response.data.elements;
    } catch (error) {
      console.error(`Overpass query failed (attempt ${i + 1}/${retries}):`, error.message);
      if (i === retries - 1) throw error;
    }
  }
}

// Process ways into GeoJSON
function processWays(elements) {
  return {
    type: 'FeatureCollection',
    features: elements.filter(el => el.type === 'way').map(way => ({
      type: 'Feature',
      geometry: {
        type: 'LineString',
        coordinates: way.geometry.map(coord => [coord.lon, coord.lat])
      },
      properties: { 
        id: way.id,
        ...way.tags
      }
    }))
  };
}

// Process nodes into GeoJSON with deduplication
function processNodes(elements) {
  const uniqueNodes = new Map();
  elements.filter(el => el.type === 'node').forEach(node => {
    if (!uniqueNodes.has(node.id)) {
      uniqueNodes.set(node.id, node);
    }
  });
  return {
    type: 'FeatureCollection',
    features: Array.from(uniqueNodes.values()).map(node => ({
      type: 'Feature',
      geometry: {
        type: 'Point',
        coordinates: [node.lon, node.lat]
      },
      properties: { 
        id: node.id,
        ...node.tags
      }
    }))
  };
}

// Main processing function
async function processRoute(route) {
  const dir = path.join(__dirname, '..', 'data', route.relationId);
  await mkdirp(dir);

  try {
    // Save route metadata
    fs.writeFileSync(
      path.join(dir, 'metadata.json'),
      JSON.stringify({
        route_color: route.routeColor,
        route_name: route.routeName,
        display_type: route.displayType
      }, null, 2)
    );

    // Fetch and save ways
    const waysQuery = `[out:json];relation(${route.relationId});way(r);out geom;`;
    const waysData = await overpassQuery(waysQuery);
    fs.writeFileSync(
      path.join(dir, 'ways.geojson'),
      JSON.stringify(processWays(waysData))
    );

    // Fetch and save platforms
    const platformsQuery = `[out:json];relation(${route.relationId});node(r:"platform");out geom;relation(${route.relationId});node(r:"platform_entry_only");out geom;relation(${route.relationId});node(r:"platform_exit_only");out geom;`;
    const platformsData = await overpassQuery(platformsQuery);
    fs.writeFileSync(
      path.join(dir, 'stops.geojson'),
      JSON.stringify(processNodes(platformsData))
    );

    console.log(`Processed relation ${route.relationId} successfully`);
  } catch (error) {
    console.error(`Failed to process relation ${route.relationId}:`, error.message);
    throw error;
  }
}

// Execute for all routes with retries
(async () => {
  for (const route of uniqueRoutes) {
    let attempts = 3;
    while (attempts > 0) {
      try {
        console.log(`Processing relation ${route.relationId}...`);
        await processRoute(route);
        break;
      } catch (error) {
        attempts--;
        if (attempts === 0) {
          console.error(`Failed to process relation ${route.relationId} after 3 attempts`);
        } else {
          console.log(`Retrying relation ${route.relationId} (${attempts} attempts remaining)...`);
        }
      }
    }
  }
  console.log('All routes processed!');
})();
