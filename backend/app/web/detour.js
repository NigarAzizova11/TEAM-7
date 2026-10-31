/* Alternativ yol seçimi (OSRM cavabından). Brauzer və Node testi üçün ortaq. Real trafik bilmir:
   yalnız tıxac nöqtəsindən yan keçən yolu seçir. */
(function (root) {
  "use strict";
  function toXY(lat, lon, lat0) {
    const kx = Math.cos(lat0 * Math.PI / 180) * 111320, ky = 110540;
    return [lon * kx, lat * ky];
  }
  // nöqtənin (avoid) polyline-a (GeoJSON [lon,lat]) minimal məsafəsi, metrlə
  function minDistM(coords, avoid) {
    const [px, py] = toXY(avoid.lat, avoid.lon, avoid.lat);
    let best = Infinity;
    for (let i = 0; i < coords.length - 1; i++) {
      const [ax, ay] = toXY(coords[i][1], coords[i][0], avoid.lat);
      const [bx, by] = toXY(coords[i + 1][1], coords[i + 1][0], avoid.lat);
      const dx = bx - ax, dy = by - ay, l2 = dx * dx + dy * dy;
      const t = l2 === 0 ? 0 : Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / l2));
      best = Math.min(best, Math.hypot(px - (ax + t * dx), py - (ay + t * dy)));
    }
    return best;
  }
  // routes: OSRM routes[]; avoid: {lat, lon, radius_m}. Qaytarır {coords:[[lat,lon]], distance_m, duration_s, fastest_distance_m} və ya null
  function pickDetour(routes, avoid) {
    if (!routes || !routes.length) return null;
    const ok = routes.filter(r => r.geometry && r.geometry.coordinates && minDistM(r.geometry.coordinates, avoid) > avoid.radius_m);
    if (!ok.length) return null;
    ok.sort((a, b) => a.duration - b.duration);
    const r = ok[0];
    return {
      coords: r.geometry.coordinates.map(c => [c[1], c[0]]),
      distance_m: Math.round(r.distance),
      duration_s: Math.round(r.duration),
      fastest_distance_m: Math.round(routes[0].distance),
    };
  }
  // Alternativ tapılmadıqda: tıxac nöqtəsindən xəttə perpendikulyar ±offset_m kənarda iki ara nöqtə (via) təklif et
  function viaCandidates(from, to, avoid, offset_m) {
    offset_m = offset_m || 450;
    const [fx, fy] = toXY(from.lat, from.lon, avoid.lat), [tx, ty] = toXY(to.lat, to.lon, avoid.lat);
    const dx = tx - fx, dy = ty - fy, n = Math.hypot(dx, dy) || 1;
    const nx = -dy / n, ny = dx / n; // perpendikulyar
    const kx = Math.cos(avoid.lat * Math.PI / 180) * 111320, ky = 110540;
    return [1, -1].map(sg => ({ lat: avoid.lat + sg * ny * offset_m / ky, lon: avoid.lon + sg * nx * offset_m / kx }));
  }
  const api = { minDistM, pickDetour, viaCandidates };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.Detour = api;
})(typeof window !== "undefined" ? window : globalThis);
