// BakuFlow: AYNA marşrutlarının xətt və dayanacaq ardıcıllığını brauzerdən yüklə (SSL problemi olmadan).
// İstifadə: https://map.ayna.gov.az/ saytını açın -> F12 -> Console -> bu kodu yapışdırıb Enter basın.
// Bitəndə "ayna_routes.json" faylı Downloads qovluğuna yüklənəcək; onu backend\data\ qovluğuna atın.
// (Chrome yapışdırmaya icazə istəsə: "allow pasting" yazıb Enter basın.)
(async () => {
  const BASE = "https://map-api.ayna.gov.az";
  const NUMBERS = []; // boş = hamısı; məs. ["62","5","88"]
  const EPS = 0.00007;
  const simplify = (pts) => {
    if (pts.length < 3) return pts;
    const keep = new Array(pts.length).fill(false); keep[0] = keep[pts.length - 1] = true;
    const st = [[0, pts.length - 1]];
    while (st.length) {
      const [a, b] = st.pop(); const [ax, ay] = pts[a], [bx, by] = pts[b];
      const dx = bx - ax, dy = by - ay, n = Math.hypot(dx, dy) || 1e-12; let md = 0, mi = -1;
      for (let i = a + 1; i < b; i++) { const d = Math.abs(dy * (pts[i][0] - ax) - dx * (pts[i][1] - ay)) / n; if (d > md) { md = d; mi = i; } }
      if (md > EPS && mi > 0) { keep[mi] = true; st.push([a, mi], [mi, b]); }
    }
    return pts.filter((_, i) => keep[i]);
  };
  const META = {};
  const transform = (d) => {
    const byDir = {};
    for (const r of d.routes || []) {
      const coords = (r.flowCoordinates || []).map(c => [Math.round(c.lat * 1e5) / 1e5, Math.round(c.lng * 1e5) / 1e5]);
      const dt = +(r.directionTypeId || 0);
      if (coords.length < 2 || byDir[dt]) continue;
      byDir[dt] = { ext_id: r.id, dir: dt, name: r.destination || "", coords: simplify(coords), stops: [] };
    }
    for (const s of d.stops || []) {
      const dt = +(s.directionTypeId || 0);
      if (s.stopCode && s.stop && !META[s.stopCode]) META[s.stopCode] = { n: s.stopName || s.stop.name, a: +s.stop.latitude, o: +s.stop.longitude };
      if (byDir[dt] && s.stopCode) byDir[dt].stops.push(String(s.stopCode));
    }
    const dirs = Object.keys(byDir).map(Number).sort().map(k => byDir[k]).filter(x => x.stops.length >= 2);
    if (!dirs.length) return null;
    return { ext_id: d.id, number: String(d.number), carrier: d.carrier, first: (d.firstPoint || "").trim(), last: (d.lastPoint || "").trim(),
             length_km: d.routLength, duration_min: d.durationMinuts, directions: dirs };
  };
  const getJson = async (u) => { for (let i = 0; i < 3; i++) { try { const r = await fetch(u); if (r.ok) return await r.json(); } catch (e) {} await new Promise(r => setTimeout(r, 800 * (i + 1))); } throw new Error(u); };

  const list = (await getJson(BASE + "/api/bus/getBusList")).filter(b => !NUMBERS.length || NUMBERS.includes(String(b.number)));
  console.log(list.length + " marşrut yüklənəcək...");
  const routes = [], failed = [], skipped = []; let done = 0, idx = 0;
  const worker = async () => {
    while (idx < list.length) {
      const b = list[idx++];
      try { const t = transform(await getJson(BASE + "/api/bus/getBusById?id=" + b.id)); t ? routes.push(t) : skipped.push(b.number); }
      catch (e) { failed.push(b.number); }
      if (++done % 20 === 0) console.log(done + "/" + list.length);
    }
  };
  await Promise.all([worker(), worker(), worker(), worker()]);
  routes.sort((a, b) => a.ext_id - b.ext_id);
  const doc = { source: "map-api.ayna.gov.az /api/bus/getBusById (map.ayna.gov.az saytının öz sorğusu)", fetched_at: new Date().toISOString().slice(0, 10),
    note: "Xətt koordinatları Douglas-Peucker ilə ~8 m dəqiqliyə sadələşdirilib; dayanacaq kodları AYNA-nın 'stopCode' sahəsidir; 'stops' = AYNA-nın dayanacaq adı/koordinatı.", stops: META, routes };
  const text = JSON.stringify(doc);
  window.__aynaDoc = doc;
  const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
  const a = document.createElement("a"); a.href = url; a.download = "ayna_routes.json"; document.body.appendChild(a); a.click(); a.remove();
  console.log(`Hazırdır: ${routes.length} marşrut, ${(text.length / 1e6).toFixed(1)} MB. Keçildi: ${skipped.join(",") || "-"}. Xəta: ${failed.join(",") || "-"}`);
  return { routes: routes.length, mb: +(text.length / 1e6).toFixed(2), skipped, failed };
})();
