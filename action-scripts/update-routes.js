const fs = require('fs');
const path = require('path');
const axios = require('axios');
const { mkdirp } = require('mkdirp');

// Enhanced file loading with validation for new structure
function loadRouteData() {
  const routesPath = path.join(__dirname, '..', 'routes.json');
  
  try {
    const fileContent = fs.readFileSync(routesPath, 'utf-8');
    const routesData = JSON.parse(fileContent);

    // Extract routes from new structure: categories → routeGroups → routes
    const allRoutes = routesData.categories.flatMap(category => 
      category.routeGroups.flatMap(group => 
        group.routes.map(route => ({
          relationId: route.relationId.toString(),
          name: route.name,
          directionId: route.directionId
        }))
      )
    );

    if (!Array.isArray(allRoutes)) {
      throw new Error('No routes found in routeGroups array');
    }

    // Validate each route object
    const validatedRoutes = allRoutes.map((route, index) => {
      if (!route.relationId) {
        throw new Error(`Route at index ${index} is missing relationId`);
      }
      return route;
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

// Get relation details with members
async function getRelationDetails(relationId) {
  const query = `[out:json];relation(${relationId});out body;`;
  const elements = await overpassQuery(query);
  
  // Find our specific relation
  const relation = elements.find(el => el.type === 'relation' && el.id == relationId);
  if (!relation) {
    throw new Error(`Relation ${relationId} not found in response`);
  }
  return relation;
}

// Get ordered ways from relation
async function getOrderedWays(relation) {
  // Collect way members in order of appearance
  const wayMembers = relation.members
    .filter(member => member.type === 'way')
    .map(member => ({
      id: member.ref,
      role: member.role
    }));

  // Get details for each way
  if (wayMembers.length === 0) {
    console.log(`No ways found for relation ${relation.id}`);
    return [];
  }

  const wayIds = wayMembers.map(m => m.id).join(',');
  const waysQuery = `[out:json];way(id:${wayIds});out geom;`;
  const wayElements = await overpassQuery(waysQuery);
  
  // Map way details while preserving order
  const wayMap = new Map(wayElements.map(way => [way.id, way]));
  return wayMembers.map(member => {
    const way = wayMap.get(member.id);
    if (!way) {
      console.warn(`Missing details for way ${member.id}`);
      return null;
    }
    return {
      ...way,
      role: member.role
    };
  }).filter(Boolean);
}

// Process ordered ways into a single LineString
function processOrderedWays(ways) {
  let coordinates = [];
  
  ways.forEach((way, index) => {
    let wayCoords = way.geometry.map(coord => [coord.lon, coord.lat]);
    
    // Reverse way if needed
    if (way.role === 'backward') {
      wayCoords = wayCoords.reverse();
    }
    
    // Connect ways without duplicating nodes
    if (index === 0) {
      coordinates = wayCoords;
    } else {
      // Skip first point to connect to previous way
      coordinates = coordinates.concat(wayCoords.slice(1));
    }
  });

  return {
    type: 'Feature',
    geometry: {
      type: 'LineString',
      coordinates
    },
    properties: {
      id: ways[0].id
    }
  };
}

// Get ordered stops from relation
async function getOrderedStops(relation) {
  // Collect stop nodes in order of appearance
  const stopMembers = relation.members
    .filter(member => 
      member.type === 'node' && 
      ['stop', 'stop_entry_only', 'stop_exit_only'].includes(member.role)
    )
    .map(member => ({
      id: member.ref,
      role: member.role
    }));

  // Get details for each stop node
  if (stopMembers.length === 0) {
    console.log(`No stops found for relation ${relation.id}`);
    return [];
  }

  const nodeIds = stopMembers.map(m => m.id).join(',');
  const nodesQuery = `[out:json];node(id:${nodeIds});out geom;`;
  const nodeElements = await overpassQuery(nodesQuery);
  
  // Map node details while preserving order
  const nodeMap = new Map(nodeElements.map(node => [node.id, node]));
  return stopMembers.map(member => {
    const node = nodeMap.get(member.id);
    if (!node) {
      console.warn(`Missing details for stop node ${member.id}`);
      return null;
    }
    return {
      ...node,
      role: member.role
    };
  }).filter(Boolean);
}

// Process a single route with ordered stops and ways
async function processRoute(route) {
  const { relationId } = route;
  const dir = path.join(__dirname, '..', 'route-data', 'geojson', relationId);
  
  try {
    await mkdirp(dir);
    console.log(`Processing route ${relationId}...`);

    // Get relation details
    const relation = await getRelationDetails(relationId);
    
    // Process ways data in order
    const ways = await getOrderedWays(relation);
    const wayFeature = processOrderedWays(ways);
    const waysGeoJSON = {
      type: 'FeatureCollection',
      features: [wayFeature]
    };
    
    fs.writeFileSync(
      path.join(dir, 'ways.geojson'),
      JSON.stringify(waysGeoJSON, null, 2)
    );

    // Process stops in correct order
    const stopNodes = await getOrderedStops(relation);
    const stopsGeoJSON = {
      type: 'FeatureCollection',
      features: stopNodes.map(node => ({
        type: 'Feature',
        geometry: {
          type: 'Point',
          coordinates: [node.lon, node.lat]
        },
        properties: {
          id: node.id,
          role: node.role,
          ...node.tags
        }
      }))
    };

    fs.writeFileSync(
      path.join(dir, 'stops.geojson'),
      JSON.stringify(stopsGeoJSON, null, 2)
    );

    console.log(`Successfully processed route ${relationId}`);
  } catch (error) {
    console.error(`Failed to process route ${relationId}:`, error.message);
    throw error;
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
