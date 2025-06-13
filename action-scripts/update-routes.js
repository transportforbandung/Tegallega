// update-routes.js
const fs = require('fs');
const path = require('path');
const axios = require('axios');
const { mkdirp } = require('mkdirp');

function loadRouteData() {
  const routesPath = path.join(__dirname, '..', 'routes.json');

  try {
    const fileContent = fs.readFileSync(routesPath, 'utf-8');
    const routesData = JSON.parse(fileContent);

    const allRoutes = routesData.categories.flatMap(category =>
      category.routeGroups.flatMap(group =>
        group.routes.map(route => ({
          relationId: route.relationId.toString(),
          name: route.name,
          directionId: route.directionId,
          mode: category.mode // Capture mode here
        }))
      )
    );

    if (!Array.isArray(allRoutes)) {
      throw new Error('No routes found in routeGroups array');
    }

    const validatedRoutes = allRoutes.map((route, index) => {
      if (!route.relationId) {
        throw new Error(`Route at index ${index} is missing relationId`);
      }
      return route;
    });

    return [...new Map(validatedRoutes.map(route => [route.relationId, route])).values()];
  } catch (error) {
    console.error('Failed to load route data:', error.message);
    process.exit(1);
  }
}

const uniqueRoutes = loadRouteData();
console.log(`Loaded ${uniqueRoutes.length} valid routes`);

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

async function getRelationDetails(relationId) {
  const query = `[out:json];relation(${relationId});out body;`;
  const elements = await overpassQuery(query);
  const relation = elements.find(el => el.type === 'relation' && el.id == relationId);
  if (!relation) {
    throw new Error(`Relation ${relationId} not found in response`);
  }
  return relation;
}

async function getOrderedWays(relation) {
  const wayMembers = relation.members
    .filter(member => member.type === 'way')
    .map(member => ({ id: member.ref, role: member.role }));

  if (wayMembers.length === 0) {
    console.log(`No ways found for relation ${relation.id}`);
    return [];
  }

  const wayIds = wayMembers.map(m => m.id).join(',');
  const waysQuery = `[out:json];way(id:${wayIds});out geom;`;
  const wayElements = await overpassQuery(waysQuery);

  const wayMap = new Map(wayElements.map(way => [way.id, way]));
  return wayMembers.map(member => {
    const way = wayMap.get(member.id);
    if (!way) {
      console.warn(`Missing details for way ${member.id}`);
      return null;
    }
    return { ...way, role: member.role };
  }).filter(Boolean);
}

function areCoordsEqual(a, b, tolerance = 1e-6) {
  return Math.abs(a[0] - b[0]) < tolerance && Math.abs(a[1] - b[1]) < tolerance;
}

function stitchWays(ways) {
  const stitched = [];
  let lastCoord = null;

  for (let i = 0; i < ways.length; i++) {
    let coords = ways[i].geometry.map(coord => [coord.lon, coord.lat]);

    if (lastCoord) {
      const start = coords[0];
      const end = coords[coords.length - 1];

      const matchesStart = areCoordsEqual(start, lastCoord);
      const matchesEnd = areCoordsEqual(end, lastCoord);

      if (!matchesStart && matchesEnd) {
        coords.reverse();
      } else if (!matchesStart && !matchesEnd) {
        console.warn(`Way ${ways[i].id} does not connect to previous way at index ${i - 1}`);
      }
    }

    if (stitched.length > 0) {
      coords = coords.slice(1);
    }

    stitched.push(...coords);
    lastCoord = coords[coords.length - 1];
  }

  return stitched;
}

function processOrderedWays(ways) {
  const coordinates = stitchWays(ways);
  return {
    type: 'Feature',
    geometry: {
      type: 'LineString',
      coordinates
    },
    properties: {
      id: ways[0]?.id
    }
  };
}

async function getOrderedStops(relation) {
  const stopMembers = relation.members
    .filter(member =>
      member.type === 'node' &&
      ['stop', 'stop_entry_only', 'stop_exit_only'].includes(member.role)
    )
    .map(member => ({ id: member.ref, role: member.role }));

  if (stopMembers.length === 0) {
    console.log(`No stops found for relation ${relation.id}`);
    return [];
  }

  const nodeIds = stopMembers.map(m => m.id).join(',');
  const nodesQuery = `[out:json];node(id:${nodeIds});out geom;`;
  const nodeElements = await overpassQuery(nodesQuery);

  const nodeMap = new Map(nodeElements.map(node => [node.id, node]));
  return stopMembers.map(member => {
    const node = nodeMap.get(member.id);
    if (!node) {
      console.warn(`Missing details for stop node ${member.id}`);
      return null;
    }
    return { ...node, role: member.role };
  }).filter(Boolean);
}

async function processRoute(route) {
  const { relationId, mode } = route;
  const dir = path.join(__dirname, '..', 'route-data', 'geojson', relationId);

  try {
    await mkdirp(dir);
    console.log(`Processing route ${relationId}...`);

    const relation = await getRelationDetails(relationId);
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

    let stopsGeoJSON;

    if (mode === 'angkot') {
      console.log(`Generating virtual stops for angkot route ${relationId}`);

      const coordSet = new Set();
      const coordToName = new Map();

      // Build coordinate list with road names from ways
      for (const way of ways) {
        const coords = way.geometry.map(c => [c.lon, c.lat]);
        const name = way.tags?.name || 'Jalan terdekat';

        for (const coord of coords) {
          const key = coord.join(',');
          if (!coordSet.has(key)) {
            coordSet.add(key);
            coordToName.set(key, name);
          }
        }
      }

      const virtualStops = Array.from(coordSet).map((key, index) => {
        const [lon, lat] = key.split(',').map(Number);
        return {
          type: 'Feature',
          geometry: {
            type: 'Point',
            coordinates: [lon, lat]
          },
          properties: {
            id: `virtual_${relationId}_${index}`,
            name: coordToName.get(key),
            role: 'virtual',
            mode: 'bus'
          }
        };
      });

      stopsGeoJSON = {
        type: 'FeatureCollection',
        features: virtualStops
      };
    }

    else {
      // Fetch regular stop nodes
      const stopNodes = await getOrderedStops(relation);
      stopsGeoJSON = {
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
    }

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
