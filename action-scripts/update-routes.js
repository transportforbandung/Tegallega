// update-routes.js
const fs = require('fs');
const path = require('path');
const axios = require('axios');
const { mkdirp } = require('mkdirp');

// Load route data from routes.json
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
          mode: category.mode
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

// Query Overpass API
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

// Get relation details from Overpass
async function getRelationDetails(relationId) {
  const query = `[out:json];relation(${relationId});out body;`;
  const elements = await overpassQuery(query);
  const relation = elements.find(el => el.type === 'relation' && el.id == relationId);
  if (!relation) {
    throw new Error(`Relation ${relationId} not found in response`);
  }
  return relation;
}

// Get ordered ways for a relation
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

// Check if coordinates are equal within tolerance
function areCoordsEqual(a, b, tolerance = 1e-6) {
  return Math.abs(a[0] - b[0]) < tolerance && Math.abs(a[1] - b[1]) < tolerance;
}

// Stitch ways together into continuous linestring
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

// Process ordered ways into GeoJSON feature
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

// Get ordered stops from relation
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

// Calculate distance between coordinates using Haversine formula
function haversineDistance(coord1, coord2) {
  const [lon1, lat1] = coord1;
  const [lon2, lat2] = coord2;
  const R = 6371e3; // Earth radius in meters
  const φ1 = lat1 * Math.PI / 180;
  const φ2 = lat2 * Math.PI / 180;
  const Δφ = (lat2 - lat1) * Math.PI / 180;
  const Δλ = (lon2 - lon1) * Math.PI / 180;

  const a = Math.sin(Δφ / 2) * Math.sin(Δφ / 2) +
            Math.cos(φ1) * Math.cos(φ2) *
            Math.sin(Δλ / 2) * Math.sin(Δλ / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

  return R * c;
}

// Project point onto linestring to get fractional index
function projectPointToLineString(point, line) {
  let minDist = Infinity;
  let minIndex = -1;
  let minT = 0;

  for (let i = 0; i < line.length - 1; i++) {
    const p1 = line[i];
    const p2 = line[i + 1];
    
    const dx = p2[0] - p1[0];
    const dy = p2[1] - p1[1];
    const lenSq = dx * dx + dy * dy;

    if (lenSq === 0) {
      const dist = haversineDistance(point, p1);
      if (dist < minDist) {
        minDist = dist;
        minIndex = i;
        minT = 0;
      }
      continue;
    }

    let t = ((point[0] - p1[0]) * dx + (point[1] - p1[1]) * dy) / lenSq;
    t = Math.max(0, Math.min(1, t));

    const proj = [p1[0] + t * dx, p1[1] + t * dy];
    const dist = haversineDistance(point, proj);

    if (dist < minDist) {
      minDist = dist;
      minIndex = i;
      minT = t;
    }
  }

  return {
    fractionalIndex: minIndex + minT,
    distance: minDist
  };
}

// Process angkot stops with real and virtual stops
async function processAngkotStops(relation, fullCoords) {
  // Precompute coordinate-to-name mapping
  const coordToName = new Map();
  const ways = await getOrderedWays(relation);
  for (const way of ways) {
    const name = way.tags?.name || 'Jalan terdekat';
    for (const coord of way.geometry) {
      const key = `${coord.lon},${coord.lat}`;
      if (!coordToName.has(key)) {
        coordToName.set(key, name);
      }
    }
  }

  // 1. Get real stops first
  const realStopNodes = await getOrderedStops(relation);
  const realStops = realStopNodes.map(node => ({
    type: 'Feature',
    geometry: {
      type: 'Point',
      coordinates: [node.lon, node.lat]
    },
    properties: {
      id: node.id.toString(),
      name: node.tags?.name || 'Unknown',
      role: node.role,
      isReal: true,
      mode: 'bus'
    }
  }));

  // 2. Generate virtual stops only between real stops
  const virtualStops = [];
  const MAX_DISTANCE = 1.0; // Maximum distance between stops in km
  const MIN_DISTANCE = 0.25; // Minimum distance between stops in km
  
  // Function to generate virtual stops between two real stops
  const generateBetweenStops = (start, end) => {
    const startIdx = projectPointToLineString(start.geometry.coordinates, fullCoords).fractionalIndex;
    const endIdx = projectPointToLineString(end.geometry.coordinates, fullCoords).fractionalIndex;
    
    const distance = haversineDistance(start.geometry.coordinates, end.geometry.coordinates) / 1000; // in km
    if (distance <= MAX_DISTANCE) return [];
    
    const numVirtual = Math.floor(distance / MAX_DISTANCE);
    const step = (endIdx - startIdx) / (numVirtual + 1);
    
    const generated = [];
    for (let i = 1; i <= numVirtual; i++) {
      const idx = startIdx + i * step;
      const coordIdx = Math.floor(idx);
      const t = idx - coordIdx;
      
      if (coordIdx < 0 || coordIdx >= fullCoords.length - 1) continue;
      
      const coord1 = fullCoords[coordIdx];
      const coord2 = fullCoords[coordIdx + 1];
      const lon = coord1[0] + t * (coord2[0] - coord1[0]);
      const lat = coord1[1] + t * (coord2[1] - coord1[1]);
      const key = `${lon},${lat}`;
      
      // Only add if not too close to real stops
      const tooClose = realStops.some(realStop => 
        haversineDistance([lon, lat], realStop.geometry.coordinates) < MIN_DISTANCE * 1000
      );
      
      if (!tooClose) {
        generated.push({
          type: 'Feature',
          geometry: {
            type: 'Point',
            coordinates: [lon, lat]
          },
          properties: {
            id: `virtual_${lon.toFixed(4)}_${lat.toFixed(4)}`,
            name: coordToName.get(key) || 'Jalan terdekat',
            role: 'virtual',
            isReal: false,
            mode: 'bus'
          }
        });
      }
    }
    return generated;
  };

  // Generate virtual stops between consecutive real stops
  for (let i = 0; i < realStops.length - 1; i++) {
    virtualStops.push(...generateBetweenStops(realStops[i], realStops[i + 1]));
  }

  // Combine all stops and sort by position along route
  const allStops = [...realStops, ...virtualStops];
  
  // Project all stops onto the route and sort
  const projectedStops = allStops.map(stop => {
    const projection = projectPointToLineString(stop.geometry.coordinates, fullCoords);
    return {
      ...stop,
      _projection: projection // Store projection data separately
    };
  }).sort((a, b) => a._projection.fractionalIndex - b._projection.fractionalIndex);

  // Final cleanup - ensure no stops are too close together
  const finalStops = [];
  let lastStop = null;
  
  for (const stop of projectedStops) {
    const shouldAdd = !lastStop || 
      haversineDistance(
        lastStop.geometry.coordinates, 
        stop.geometry.coordinates
      ) >= MIN_DISTANCE * 1000 ||
      stop.properties.isReal;
    
    if (shouldAdd) {
      // Create clean stop object without projection data
      finalStops.push({
        type: 'Feature',
        geometry: stop.geometry,
        properties: stop.properties
      });
      lastStop = stop;
    }
  }

  return finalStops;
}

// Main route processing function
async function processRoute(route) {
  const { relationId, mode } = route;
  const dir = path.join(__dirname, '..', 'route-data', 'geojson', relationId);

  try {
    // Create output directory
    await mkdirp(dir);
    console.log(`Processing route ${relationId} (${mode})...`);

    // Fetch relation data from Overpass
    const relation = await getRelationDetails(relationId);
    const ways = await getOrderedWays(relation);
    
    if (ways.length === 0) {
      throw new Error(`No ways found for relation ${relationId}`);
    }

    // Process route geometry
    const fullCoords = stitchWays(ways);
    const waysGeoJSON = {
      type: 'FeatureCollection',
      features: [{
        type: 'Feature',
        geometry: {
          type: 'LineString',
          coordinates: fullCoords
        },
        properties: {
          id: ways[0]?.id,
          relationId: relationId.toString()
        }
      }]
    };

    // Write ways file
    fs.writeFileSync(
      path.join(dir, 'ways.geojson'),
      JSON.stringify(waysGeoJSON, null, 2)
    );

    // Process stops based on route type
    let stopsGeoJSON;
    if (mode === 'angkot') {
      console.log(`Processing angkot route ${relationId} with real + virtual stops`);
      
      const stops = await processAngkotStops(relation, fullCoords);
      
      stopsGeoJSON = {
        type: 'FeatureCollection',
        features: stops.map(stop => ({
          type: 'Feature',
          geometry: stop.geometry,
          properties: {
            id: stop.properties.id,
            name: stop.properties.name,
            role: stop.properties.role,
            isReal: stop.properties.isReal,
            mode: 'bus'
          }
        }))
      };
    } else {
      // For non-angkot routes (trains, etc.)
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
            id: node.id.toString(),
            name: node.tags?.name || 'Unknown',
            role: node.role,
            ...node.tags
          }
        }))
      };
    }

    // Write stops file
    fs.writeFileSync(
      path.join(dir, 'stops.geojson'),
      JSON.stringify(stopsGeoJSON, null, 2)
    );

    console.log(`Successfully processed route ${relationId}`);
    return true;
  } catch (error) {
    console.error(`Error processing route ${relationId}:`, error.message);
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
