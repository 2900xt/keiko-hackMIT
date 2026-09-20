"use client";
import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { ageOpacity, RANGE_M, type Detection } from "@/lib/detections";
import type { Buoy, Track } from "@/lib/feed";

interface Props {
  buoyId: string;
  position: { lat: number; lon: number };
  detections: Detection[];
  hoveredId: string | null;
  focus: { id: string; n: number } | null; // "show on map": pan to this detection
  active: boolean;
  now: number | null;
  buoys: Buoy[];    // the array; the first is the physical one, the rest may be simulated
  tracks: Track[];
}

const ACCENT = "#57b8ec", INK = "#e6eef5";

// Imperative Leaflet map. Created once; markers are keyed by detection id and
// added as new rows arrive, so the React tree never re-renders the map itself.
export default function MapView({ buoyId, position, detections, hoveredId, focus, active, now, buoys, tracks }: Props) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const buoy = useRef<L.Marker | null>(null);
  const range = useRef<L.Circle | null>(null);
  const sightings = useRef<L.LayerGroup | null>(null);
  const markers = useRef(new Map<string, L.Marker>());
  const array = useRef<L.LayerGroup | null>(null);      // the other buoys
  const fixes = useRef<L.LayerGroup | null>(null);      // error circles, keyed by detection id
  const circles = useRef(new Map<string, L.Circle>());
  const rays = useRef<L.LayerGroup | null>(null);       // buoy -> latest fix lines
  const trackLayer = useRef<L.LayerGroup | null>(null);
  const polylines = useRef(new Map<string, L.Polyline>());
  const fitted = useRef(false);

  useEffect(() => {
    if (!el.current || map.current) return;
    const m = L.map(el.current, { zoomControl: false, maxZoom: 18 }).setView([position.lat, position.lon], 15);
    L.control.zoom({ position: "topleft" }).addTo(m);
    L.control.scale({ position: "topleft", imperial: false }).addTo(m);
    // Esri Dark Gray Canvas (keyless), split so the base can be tinted to the
    // site's navy in CSS (.tiles-base) while the labels stay crisp above it.
    // Native tiles stop at zoom 16; Leaflet upscales them beyond that.
    const esri = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/";
    L.tileLayer(esri + "World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}", {
      maxNativeZoom: 16, maxZoom: 18, className: "tiles-base",
      attribution: "Tiles &copy; Esri &mdash; Esri, HERE, Garmin, OpenStreetMap contributors",
    }).addTo(m);
    L.tileLayer(esri + "World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}", {
      maxNativeZoom: 16, maxZoom: 18, pane: "overlayPane", className: "tiles-labels",
    }).addTo(m);
    range.current = L.circle([position.lat, position.lon], { radius: RANGE_M, color: "#e6eef5", weight: 1.5, dashArray: "5 5", fillColor: "#e6eef5", fillOpacity: 0.06, interactive: false }).addTo(m);
    array.current = L.layerGroup().addTo(m);
    trackLayer.current = L.layerGroup().addTo(m);
    fixes.current = L.layerGroup().addTo(m);
    rays.current = L.layerGroup().addTo(m);
    sightings.current = L.layerGroup().addTo(m);
    buoy.current = L.marker([position.lat, position.lon], {
      icon: L.divIcon({ className: "", html: '<div class="buoy"></div>', iconSize: [16, 16], iconAnchor: [8, 8] }), zIndexOffset: 1000,
    }).addTo(m).bindTooltip(buoyId, { permanent: true, direction: "right", offset: [12, 0], className: "buoy-label" });
    map.current = m;
    const markersAtMount = markers.current;
    return () => { m.remove(); map.current = null; markersAtMount.clear(); };
  }, []);

  useEffect(() => {
    buoy.current?.setLatLng([position.lat, position.lon]);
    range.current?.setLatLng([position.lat, position.lon]);
  }, [position.lat, position.lon]);

  // The rest of the array. Simulated buoys are drawn hollow and say so; the
  // view widens once to take the whole array in.
  useEffect(() => {
    const layer = array.current, m = map.current;
    if (!layer || !m) return;
    layer.clearLayers();
    const others = buoys.filter((b) => b.id !== buoyId);
    for (const b of others) {
      L.marker([b.lat, b.lon], {
        icon: L.divIcon({ className: "", html: '<div class="buoy' + (b.simulated ? " sim" : "") + '"></div>', iconSize: [16, 16], iconAnchor: [8, 8] }), zIndexOffset: 900,
      }).addTo(layer).bindTooltip(b.id + (b.simulated ? " · simulated" : ""), { permanent: true, direction: "right", offset: [12, 0], className: "buoy-label" + (b.simulated ? " sim" : "") });
    }
    if (others.length && !fitted.current) {
      fitted.current = true;
      m.fitBounds(L.latLngBounds(buoys.map((b) => [b.lat, b.lon] as [number, number])).pad(0.25));
    }
  }, [buoys, buoyId]);

  // Localized calls: an error circle each, and for the newest one a ray from
  // every buoy that heard it (dashed when that arrival is simulated).
  useEffect(() => {
    const fl = fixes.current, rl = rays.current;
    if (!fl || !rl) return;
    const seen = new Set<string>();
    let newest: Detection | null = null;
    for (const d of detections) {
      if (!d.fix) continue;
      seen.add(d.id);
      if (!newest || d.t >= newest.t) newest = d;
      if (circles.current.has(d.id)) continue;
      const c = L.circle([d.fix.lat, d.fix.lon], { radius: d.fix.err_m, color: ACCENT, weight: 1, opacity: 0.7, fillColor: ACCENT, fillOpacity: 0.12, interactive: false }).addTo(fl);
      circles.current.set(d.id, c);
    }
    for (const [id, c] of circles.current) if (!seen.has(id)) { fl.removeLayer(c); circles.current.delete(id); }
    rl.clearLayers();
    if (newest?.fix) {
      for (const a of newest.fix.arrivals) {
        const b = buoys.find((x) => x.id === a.buoy_id);
        if (!b) continue;
        L.polyline([[b.lat, b.lon], [newest.fix.lat, newest.fix.lon]], { color: INK, weight: 1, opacity: 0.55, dashArray: a.simulated ? "3 6" : undefined, interactive: false, className: "ray" }).addTo(rl);
      }
    }
  }, [detections, buoys]);

  useEffect(() => {
    const layer = trackLayer.current;
    if (!layer) return;
    const seen = new Set<string>();
    for (const t of tracks) {
      seen.add(t.id);
      const pts = t.points.map((p) => [p.lat, p.lon] as [number, number]);
      const pl = polylines.current.get(t.id);
      if (pl) { pl.setLatLngs(pts); continue; }
      polylines.current.set(t.id, L.polyline(pts, { color: ACCENT, weight: 2.5, opacity: 0.85, lineJoin: "round", interactive: false, className: "track" }).addTo(layer)
        .bindTooltip(t.species + " · track " + t.id, { sticky: true, className: "sight-tip" }));
    }
    for (const [id, pl] of polylines.current) if (!seen.has(id)) { layer.removeLayer(pl); polylines.current.delete(id); }
  }, [tracks]);

  useEffect(() => {
    const layer = sightings.current;
    if (!layer) return;
    const seen = new Set<string>();
    for (const d of detections) {
      seen.add(d.id);
      if (markers.current.has(d.id)) continue;
      const when = new Date(d.t);
      const mk = L.marker([d.lat, d.lon], {
        icon: L.divIcon({ className: "", html: '<div class="sighting' + (d.live ? " hot" : "") + '"></div>', iconSize: [10, 10], iconAnchor: [5, 5] }),
        opacity: ageOpacity(d.t),
      })
        .bindTooltip((d.species ? d.species + " · " : "") + Math.round(d.confidence * 100) + "% · " + when.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) + (d.fix ? " · ±" + Math.round(d.fix.err_m) + " m" : ""), { direction: "top", offset: [0, -6], className: "sight-tip" })
        .addTo(layer);
      markers.current.set(d.id, mk);
    }
    for (const [id, mk] of markers.current) if (!seen.has(id)) { layer.removeLayer(mk); markers.current.delete(id); }
  }, [detections]);

  // sightings fade with age; refresh once a minute
  const minute = now ? Math.floor(now / 60000) : 0;
  useEffect(() => {
    if (!minute) return;
    for (const d of detections) markers.current.get(d.id)?.setOpacity(ageOpacity(d.t));
  }, [minute, detections]);

  const hovered = useRef<L.Marker | null>(null);
  useEffect(() => {
    hovered.current?.closeTooltip();
    hovered.current = hoveredId ? markers.current.get(hoveredId) ?? null : null;
    hovered.current?.openTooltip();
  }, [hoveredId]);

  useEffect(() => { if (active) map.current?.invalidateSize(); }, [active]);

  useEffect(() => {
    const m = map.current, mk = focus ? markers.current.get(focus.id) : null;
    if (!m || !mk || !active) return;
    m.invalidateSize();
    m.flyTo(mk.getLatLng(), Math.max(m.getZoom(), 16), { duration: 0.6 });
    mk.openTooltip();
  }, [focus, active]);

  return <div id="map" ref={el} />;
}
