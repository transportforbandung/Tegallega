// Modified processAngkotStops function
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
      fractionalIndex: projection.fractionalIndex,
      distance: projection.distance
    };
  }).sort((a, b) => a.fractionalIndex - b.fractionalIndex);

  // Final cleanup - ensure no stops are too close together
  const finalStops = [];
  let lastStop = null;
  
  for (const stop of projectedStops) {
    if (!lastStop || 
        haversineDistance(lastStop.geometry.coordinates, stop.geometry.coordinates) >= MIN_DISTANCE * 1000 ||
        stop.properties.isReal) {
      finalStops.push(stop);
      lastStop = stop;
    }
  }

  return {
    type: 'FeatureCollection',
    features: finalStops
  };
}