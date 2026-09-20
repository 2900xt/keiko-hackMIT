"use client";
import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { ageOpacity, RANGE_M, type Detection } from "@/lib/detections";

interface Props {
  buoyId: string;
  position: { lat: number; lon: number };
  detections: Detection[];
  hoveredId: string | null;
  focus: { id: string; n: number } | null; // "show on map": pan to this detection
  active: boolean;
  now: number | null;
}

// Imperative Leaflet map. Created once; markers are keyed by detection id and
// added as new rows arrive, so the React tree never re-renders the map itself.
export default function MapView({ buoyId, position, detections, hoveredId, focus, active, now }: Props) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const buoy = useRef<L.Marker | null>(null);
  const range = useRef<L.Circle | null>(null);
  const sightings = useRef<L.LayerGroup | null>(null);
  const markers = useRef(new Map<string, L.Marker>());

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
        .bindTooltip(Math.round(d.confidence * 100) + "% · " + when.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }), { direction: "top", offset: [0, -6], className: "sight-tip" })
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
