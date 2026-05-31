"use client";

import { useEffect } from "react";
import type mapboxgl from "mapbox-gl";

type ZoneLayerProps = {
  map: mapboxgl.Map | null;
  id: string;
  geojson: GeoJSON.FeatureCollection;
  color?: string;
  opacity?: number;
  visible?: boolean;
};

/**
 * Renders a GeoJSON polygon overlay on the map (school zones, LGA boundaries, etc.).
 */
export default function ZoneLayer({
  map,
  id,
  geojson,
  color = "#6366f1",
  opacity = 0.2,
  visible = true,
}: ZoneLayerProps) {
  useEffect(() => {
    if (!map) return;

    const sourceId = `zone-${id}`;
    const fillLayerId = `zone-fill-${id}`;
    const lineLayerId = `zone-line-${id}`;

    const addLayers = () => {
      // Guard against map being removed during async wait
      if (!map.getStyle()) return;

      if (map.getSource(sourceId)) {
        (map.getSource(sourceId) as mapboxgl.GeoJSONSource).setData(geojson);
        return;
      }

      map.addSource(sourceId, {
        type: "geojson",
        data: geojson,
      });

      map.addLayer({
        id: fillLayerId,
        type: "fill",
        source: sourceId,
        paint: {
          "fill-color": color,
          "fill-opacity": opacity,
        },
      });

      map.addLayer({
        id: lineLayerId,
        type: "line",
        source: sourceId,
        paint: {
          "line-color": color,
          "line-width": 2,
        },
      });
    };

    // The map reference is set via onMapReady which fires inside the map's
    // "load" handler. By the time React re-renders this component with the
    // new map prop, the "load" event has already fired (it only fires once).
    // Use "idle" instead — it fires whenever the map finishes rendering.
    if (map.isStyleLoaded()) {
      addLayers();
    } else {
      map.once("idle", addLayers);
    }

    return () => {
      map.off("idle", addLayers);
      if (!map?.getStyle()) return;
      if (map.getLayer(fillLayerId)) map.removeLayer(fillLayerId);
      if (map.getLayer(lineLayerId)) map.removeLayer(lineLayerId);
      if (map.getSource(sourceId)) map.removeSource(sourceId);
    };
  }, [map, id, geojson, color, opacity]);

  /* Toggle visibility */
  useEffect(() => {
    if (!map || !map.getStyle()) return;
    const fillLayerId = `zone-fill-${id}`;
    const lineLayerId = `zone-line-${id}`;
    const visibility = visible ? "visible" : "none";

    if (map.getLayer(fillLayerId)) {
      map.setLayoutProperty(fillLayerId, "visibility", visibility);
    }
    if (map.getLayer(lineLayerId)) {
      map.setLayoutProperty(lineLayerId, "visibility", visibility);
    }
  }, [map, id, visible]);

  return null;
}

