const assert = require("assert");
const { pickDetour, minDistM } = require("../app/web/detour.js");
const avoid = { lat: 40.4, lon: 49.8, radius_m: 150 };
// düz yol tıxacın içindən keçir; 2-ci yol ~600 m şimaldan keçir
const through = { distance: 2000, duration: 200, geometry: { coordinates: [[49.79, 40.4], [49.81, 40.4]] } };
const around = { distance: 2600, duration: 300, geometry: { coordinates: [[49.79, 40.4054], [49.81, 40.4054]] } };
const nearMiss = { distance: 2100, duration: 210, geometry: { coordinates: [[49.79, 40.4008], [49.81, 40.4008]] } }; // ~89 m
assert(minDistM(through.geometry.coordinates, avoid) < 5);
assert(Math.abs(minDistM(around.geometry.coordinates, avoid) - 596) < 15);
let r = pickDetour([through, around], avoid);
assert.strictEqual(r.duration_s, 300); assert.strictEqual(r.fastest_distance_m, 2000);
assert.deepStrictEqual(r.coords[0], [40.4054, 49.79]);
r = pickDetour([through, nearMiss, around], avoid);
assert.strictEqual(r.duration_s, 300, "radiusdan yaxın yol seçilməməlidir");
assert.strictEqual(pickDetour([through, nearMiss], avoid), null);
assert.strictEqual(pickDetour([], avoid), null);
const { viaCandidates } = require("../app/web/detour.js");
const vs = viaCandidates({ lat: 40.4, lon: 49.78 }, { lat: 40.4, lon: 49.82 }, avoid, 450); // xətt şərq-qərb
assert(Math.abs(vs[0].lon - avoid.lon) < 1e-6 && Math.abs(vs[1].lon - avoid.lon) < 1e-6);
assert(vs[0].lat > avoid.lat && vs[1].lat < avoid.lat);
assert(Math.abs((vs[0].lat - avoid.lat) * 110540 - 450) < 1);
console.log("detour ok");
