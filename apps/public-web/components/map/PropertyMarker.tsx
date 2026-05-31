"use client";

import { useEffect, useRef } from "react";
import mapboxgl from "mapbox-gl";

type PropertyMarkerProps = {
  map: mapboxgl.Map | null;
  latitude: number;
  longitude: number;
  label?: string;
  onClick?: () => void;
};

/**
 * Renders an individual Mapbox marker for a property.
 * Used for highlighted / selected properties (not for clustered pins).
 */
export default function PropertyMarker({
  map,
  latitude,
  longitude,
  label,
  onClick,
}: PropertyMarkerProps) {
  const markerRef = useRef<mapboxgl.Marker | null>(null);

  useEffect(() => {
    if (!map) return;

    const el = document.createElement("div");
    el.className =
      "w-6 h-6 rounded-full bg-blue-600 border-2 border-white shadow-lg cursor-pointer";
    if (label) {
      el.title = label;
    }
    if (onClick) {
      el.addEventListener("click", onClick);
    }

    const marker = new mapboxgl.Marker({ element: el })
      .setLngLat([longitude, latitude])
      .addTo(map);

    markerRef.current = marker;

    return () => {
      marker.remove();
      markerRef.current = null;
    };
  }, [map, latitude, longitude, label, onClick]);

  return null;
}
