const fs = require('fs');
const path = require('path');
const axios = require('axios');
const { mkdirp } = require('mkdirp');

// Load and validate route data
function loadRouteData() {
  const routesPath = path.join(__dirname, '..', 'routes.json');
  try {
    const fileContent = fs.readFileSync(routesPath, 'utf-8');
    const routesData = JSON.parse(fileContent);

    return routesData.categories.flatMap(category =>
      category.routeGroups.flatMap(group =>
        group.routes.map(route => ({
          relationId: route.relationId.toString(),
          name: route.name,
          directionId: route.directionId
        }))
      )
    );
  } catch (error) {
    console.error('Failed to load route data:', error.message);
    process.exit(1);
  }
}

const uniqueRoutes = loadRouteData();

// Overpass API query with retry
async function overpassQuery(query, retries = 3, delay = 2000) {
  const url = `https://overpass-api.de/api/interpreter?data=${encodeURIComponent(query)}`;
  for (let i = 0; i < retries; i++) {
    try {
      const response = await axios.get(url, { timeout: 15000 });
      return response.data.elements;
    } catch (error) {
      if (i === retries - 1) throw error;
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }
}

// Get relation with members
async function getRelationDetails(relationId) {
  const query = `[out:json];relation(${relationId});out body;`;
  const elements = await overpassQuery(query);
  const relation = elements.find(el => el.type === 'relation' && el.id == relationId);
  if (!relation) throw new Error(`Relation ${relationId} not found`);
  return relation;
}

// Get all ways with geometry and map by ID
async function getWayDetails(wayIds) {
  const query = `[out:json];way(id:${wayIds.join(',')});out geom;`;
  const elements = await overpassQuery(query);
  const map = new Map(elements.map(w => [w.id, w]));
  return map;
}

// Build graph: node ID -> connected ways
function buildGraph(ways) {
  const graph = new Map();
  for (const way of ways) {
    const first = way.geometry[0];
    const last = way.geometry[way.geometry.length - 1];
    const addEdge = (a, b, w) => {
      if (!graph.has(a)) graph.set(a, []);
      graph.get(a).push({ node: b, way: w });
    };
    addEdge(first.lat + ',' + first.lon, last.lat + ',' + last.lon, way);
    addEdge(last.lat + ',' + last.lon, first.lat + ',' + first.lon, way);
  }
  return graph;
}

// Find path through all ways by connecting endpoints
function orderWays(ways) {
  const graph = buildGraph(ways);
  const usedWays = new Set();
  let path = [];

  const start = ways[0].geometry[0];
  const startKey = start.lat + ',' + start.lon;

  function dfs(nodeKey, chain) {
    const neighbors = graph.get(nodeKey) || [];
    for (const { node: neighbor, way } of neighbors) {
      if (usedWays.has(way.id)) continue;
      usedWays.add(way.id);
      const forward = way.geometry[0].lat + ',' + way.geometry[0].lon === nodeKey;
      const coords = forward ? way.geometry : [...way.geometry].reverse();
      dfs(neighbor, chain.concat(coords.slice(1)));
      return;
    }
    path = chain;
  }

  dfs(startKey, [start]);
  return path;
}

// Get ordered stops
async function getOrderedStops(relation) {
  const stopMembers = relation.members.filter(m =>
    m.type === 'node' && ['stop', 'stop_entry_only', 'stop_exit_only'].includes(m.role)
  );
  if (stopMembers.length === 0) return [];
  const ids = stopMembers.map(m => m.ref).join(',');
  const query = `[out:json];node(id:${ids});out body;`;
  const elements = await overpassQuery(query);
  const map = new Map(elements.map(n => [n.id, n]));
  return stopMembers.map(m => map.get(m.ref)).filter(Boolean);
}

// Process single route
async function processRoute(route) {
  const dir = path.join(__dirname, '..', 'route-data', 'geojson', route.relationId);
  await mkdirp(dir);
  const relation = await getRelationDetails(route.relationId);

  const wayMembers = relation.members.filter(m => m.type === 'way');
  if (!wayMembers.length) throw new Error('No way members in relation');

  const wayIds = wayMembers.map(m => m.ref);
  const wayMap = await getWayDetails(wayIds);
  const ways = wayMembers.map(m => wayMap.get(m.ref)).filter(Boolean);
  const orderedCoords = orderWays(ways);

  const wayFeature = {
    type: 'Feature',
    geometry: {
      type: 'LineString',
      coordinates: orderedCoords.map(c => [c.lon, c.lat])
    },
    properties: { relationId: route.relationId }
  };

  const waysGeoJSON = {
    type: 'FeatureCollection',
    features: [wayFeature]
  };

  fs.writeFileSync(path.join(dir, 'ways.geojson'), JSON.stringify(waysGeoJSON, null, 2));

  const stopNodes = await getOrderedStops(relation);
  const stopsGeoJSON = {
    type: 'FeatureCollection',
    features: stopNodes.map(n => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [n.lon, n.lat] },
      properties: { id: n.id, ...n.tags }
    }))
  };

  fs.writeFileSync(path.join(dir, 'stops.geojson'), JSON.stringify(stopsGeoJSON, null, 2));
  console.log(`Processed route ${route.relationId}`);
}

// Main
(async () => {
  for (const route of uniqueRoutes) {
    try {
      await processRoute(route);
    } catch (error) {
      console.error(`Error processing route ${route.relationId}:`, error.message);
    }
  }
})();
