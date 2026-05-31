"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type mapboxgl from "mapbox-gl";
import type { BBox } from "@/types";

const DEBOUNCE_MS = 400;

/**
 * Track the current map viewport bounding box, debounced by 400ms.
 * Returns the latest bbox and a `setMap` callback to attach to a Mapbox Map instance.
 */
export function useMapBounds() {
  const [bbox, setBbox] = useState<BBox | null>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleMoveEnd = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      const map = mapRef.current;
      if (!map) return;
      const bounds = map.getBounds();
      if (!bounds) return;
      setBbox([
        bounds.getWest(),
        bounds.getSouth(),
        bounds.getEast(),
        bounds.getNorth(),
      ]);
    }, DEBOUNCE_MS);
  }, []);

  const setMap = useCallback(
    (map: mapboxgl.Map) => {
      mapRef.current = map;
      map.on("moveend", handleMoveEnd);
      // Trigger initial bbox
      handleMoveEnd();
    },
    [handleMoveEnd],
  );

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      const map = mapRef.current;
      if (map) map.off("moveend", handleMoveEnd);
    };
  }, [handleMoveEnd]);

  return { bbox, setMap };
}
