const fs = require('fs');
const path = require('path');
const axios = require('axios');
const { mkdirp } = require('mkdirp');

// Enhanced file loading with validation
function loadRouteData() {
  const routesPath = path.join(__dirname, '..', 'route-data', 'routes.json');
  
  try {
    const fileContent = fs.readFileSync(routesPath, 'utf-8');
    const routesData = JSON.parse(fileContent);

    // Extract routes from categories
    const allRoutes = routesData.categories.flatMap(category => category.routes);

    if (!Array.isArray(allRoutes)) {
      throw new Error('No routes found in categories array');
    }

    // Validate each route object
    const validatedRoutes = allRoutes.map((route, index) => {
      if (!route.relationId) {
        throw new Error(`Route at index ${index} is missing relationId`);
      }
      if (!route.type) {
        throw new Error(`Route at index ${index} is missing type`);
      }
      if (!['ways_with_points', 'ways'].includes(route.type)) {
        throw new Error(`Route at index ${index} has invalid type: ${route.type}`);
      }
      return {
        relationId: route.relationId.toString(),
        type: route.type
      };
    });

    // Remove duplicate entries
    return [...new Map(validatedRoutes.map(route => [route.relationId, route])).values()];
  } catch (error) {
    console.error('Failed to load route data:', error.message);
    process.exit(1);
  }
}

// Load and validate routes
const uniqueRoutes = loadRouteData();
console.log(`Loaded ${uniqueRoutes.length} valid routes`);

// Overpass API query with retry logic
async function overpassQuery(query, retries = 3, delay = 2000) {
  const url = `https://overpass-api.de/api/interpreter?data=${encodeURIComponent(query)}`;
  
  for (let attempt = 1; attempt <= retries; attempt++) {
    try {
      if (attempt > 1) {
        console.log(`Retrying query (attempt ${attempt}/${retries})...`);
        await new Promise(resolve => setTimeout(resolve, delay * (attempt - 1)));
      }

      const response = await axios.get(url, { timeout: 15000 });
      return response.data.elements;
    } catch (error) {
      if (attempt === retries) {
        throw new Error(`Overpass query failed after ${retries} attempts: ${error.message}`);
      }
    }
  }
}

// Process OSM ways into GeoJSON
function processWays(elements) {
  const features = elements
    .filter(el => el.type === 'way')
    .map(way => ({
      type: 'Feature',
      geometry: {
        type: 'LineString',
        coordinates: way.geometry.map(coord => [coord.lon, coord.lat])
      },
      properties: {
        id: way.id,
        ...way.tags
      }
    }));

  return {
    type: 'FeatureCollection',
    features
  };
}

// Process OSM nodes into GeoJSON
function processNodes(elements) {
  const features = elements
    .filter(el => el.type === 'node')
    .map(node => ({
      type: 'Feature',
      geometry: {
        type: 'Point',
        coordinates: [node.lon, node.lat]
      },
      properties: {
        id: node.id,
        ...node.tags
      }
    }));

  return {
    type: 'FeatureCollection',
    features
  };
}

// Process a single route
async function processRoute(route) {
  const { relationId, type } = route;
  const dir = path.join(__dirname, '..', 'route-data', 'geojson', relationId);
  
  try {
    await mkdirp(dir);
    console.log(`Processing route ${relationId} (${type})...`);

    // Process ways data
    const waysQuery = `[out:json]; relation(${relationId}); way(r); out geom;`;
    const waysData = await overpassQuery(waysQuery);
    const waysGeoJSON = processWays(waysData);
    fs.writeFileSync(
      path.join(dir, 'ways.geojson'),
      JSON.stringify(waysGeoJSON, null, 2) // Pretty print JSON
    );

    // Process stops data based on route type
    const stopsQuery = type === 'ways_with_points'
      ? `[out:json];relation(${relationId});node(r:"stop");out geom;relation(${relationId});node(r:"stop_entry_only");out geom;relation(${relationId});node(r:"stop_exit_only");out geom;`
      : `[out:json];relation(${relationId});node(r:"stop_entry_only");out geom;relation(${relationId});node(r:"stop_exit_only");out geom;`;
    
    const stopsData = await overpassQuery(stopsQuery);
    const stopsGeoJSON = processNodes(stopsData);
    const fileName = type === 'ways_with_points' ? 'stops.geojson' : 'endstops.geojson';
    fs.writeFileSync(
      path.join(dir, fileName),
      JSON.stringify(stopsGeoJSON, null, 2) // Pretty print JSON
    );

    console.log(`Successfully processed route ${relationId}`);
  } catch (error) {
    console.error(`Failed to process route ${relationId}:`, error.message);
    throw error; // Re-throw for retry logic
  }
}

// Main execution
(async () => {
  try {
    for (const route of uniqueRoutes) {
      let attempts = 3;
      let success = false;

      while (attempts > 0 && !success) {
        try {
          await processRoute(route);
          success = true;
        } catch (error) {
          attempts--;
          if (attempts === 0) {
            console.error(`Giving up on route ${route.relationId} after 3 attempts`);
          } else {
            console.log(`Will retry route ${route.relationId} (${attempts} attempts remaining)`);
          }
        }
      }
    }

    console.log('All routes processed successfully!');
  } catch (error) {
    console.error('Fatal error in main execution:', error.message);
    process.exit(1);
  }
})();
