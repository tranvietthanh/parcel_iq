"use client";

import { useCallback, useEffect, useRef } from "react";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import { createMap } from "@/lib/mapbox";
import type { PropertyPin } from "@/types";

type MapContainerProps = {
  pins: any; // Accepts PropertyPin[] | SearchResult[] | FeatureCollection
  onMapReady: (map: mapboxgl.Map) => void;
  onPinClick: (propertyId: string, slug?: string) => void;
  initialBbox?: [number, number, number, number] | null;
  initialCoordinates?: [number, number] | null;
};

const SOURCE_ID = "properties";
const CLUSTER_LAYER = "clusters";
const CLUSTER_COUNT_LAYER = "cluster-count";
const UNCLUSTERED_LAYER = "unclustered-point";

export default function MapContainer({
  pins,
  onMapReady,
  onPinClick,
  initialBbox,
  initialCoordinates,
}: MapContainerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);

  /* ── Initialise map ──────────────────────────────────── */
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = createMap(containerRef.current, {
      bounds: initialBbox ?? undefined,
      center: initialCoordinates ?? undefined,
      zoom: initialCoordinates ? 16 : undefined,
    });

    map.on("load", () => {
      // Add clustered source
      map.addSource(SOURCE_ID, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
        cluster: true,
        clusterMaxZoom: 13,
        clusterRadius: 50,
      });

      // Cluster circles
      map.addLayer({
        id: CLUSTER_LAYER,
        type: "circle",
        source: SOURCE_ID,
        filter: ["has", "point_count"],
        paint: {
          "circle-color": [
            "step",
            ["get", "point_count"],
            "#51bbd6",
            50,
            "#f1f075",
            200,
            "#f28cb1",
          ],
          "circle-radius": [
            "step",
            ["get", "point_count"],
            20,
            50,
            30,
            200,
            40,
          ],
        },
      });

      // Cluster count labels
      map.addLayer({
        id: CLUSTER_COUNT_LAYER,
        type: "symbol",
        source: SOURCE_ID,
        filter: ["has", "point_count"],
        layout: {
          "text-field": ["get", "point_count_abbreviated"],
          "text-size": 12,
        },
      });

      // Individual pins
      map.addLayer({
        id: UNCLUSTERED_LAYER,
        type: "circle",
        source: SOURCE_ID,
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-color": [
            "case",
            ["!=", ["get", "report_status"], null],
            "#22c55e", // green — has a report
            "#f97316", // orange — no report
          ],
          "circle-radius": 8,
          "circle-stroke-width": 2,
          "circle-stroke-color": "#ffffff",
        },
      });

      // Click handlers
      map.on("click", UNCLUSTERED_LAYER, (e) => {
        const feature = e.features?.[0];
        if (feature?.properties?.id) {
          onPinClick(feature.properties.id as string, feature.properties.slug as string | undefined);
        }
      });

      map.on("click", CLUSTER_LAYER, (e) => {
        const features = map.queryRenderedFeatures(e.point, {
          layers: [CLUSTER_LAYER],
        });
        const clusterId = features[0]?.properties?.cluster_id;
        if (clusterId == null) return;
        const source = map.getSource(SOURCE_ID) as mapboxgl.GeoJSONSource;
        source.getClusterExpansionZoom(clusterId, (err, zoom) => {
          if (err || zoom == null) return;
          const geometry = features[0].geometry;
          if (geometry.type === "Point") {
            map.easeTo({
              center: geometry.coordinates as [number, number],
              zoom,
            });
          }
        });
      });

      const popup = new mapboxgl.Popup({
        closeButton: false,
        closeOnClick: false,
      });

      // Cursor styling and Popup
      map.on("mouseenter", UNCLUSTERED_LAYER, (e) => {
        map.getCanvas().style.cursor = "pointer";
        const feature = e.features?.[0];
        if (feature?.properties?.address && feature.geometry.type === "Point") {
          const coordinates = feature.geometry.coordinates.slice();
          while (Math.abs(e.lngLat.lng - coordinates[0]) > 180) {
            coordinates[0] += e.lngLat.lng > coordinates[0] ? 360 : -360;
          }
          popup
            .setLngLat(coordinates as [number, number])
            .setHTML(`<div class="px-2 py-1 text-sm font-medium text-zinc-900">${feature.properties.address}</div>`)
            .addTo(map);
        }
      });
      map.on("mouseleave", UNCLUSTERED_LAYER, () => {
        map.getCanvas().style.cursor = "";
        popup.remove();
      });
      map.on("mouseenter", CLUSTER_LAYER, () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", CLUSTER_LAYER, () => {
        map.getCanvas().style.cursor = "";
      });

      mapRef.current = map;
      onMapReady(map);
    });

    return () => {
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ── Update GeoJSON data when pins change ────────────── */
  const updatePins = useCallback((data: PropertyPin[] | any) => {
    const map = mapRef.current;
    if (!map) return;
    const source = map.getSource(SOURCE_ID) as mapboxgl.GeoJSONSource | undefined;
    if (!source) return;

    // Handle both FeatureCollection (from bbox search) and PropertyPin[] (from text search)
    let pins: PropertyPin[] = [];
    if (Array.isArray(data)) {
      // Text search returns SearchResult[] - filter for ADDRESS type only
      pins = data
        .filter((item) => (item as any).type === "ADDRESS")
        .map((item) => ({
          id: (item as any).id || (item as any).property_id,
          latitude: (item as any).latitude || (item as any).coordinates?.[1],
          longitude: (item as any).longitude || (item as any).coordinates?.[0],
          estimated_value: (item as any).estimated_value,
          report_status: null,
          slug: (item as any).slug || null,
          address: (item as any).label || null,
        }));
    } else if (data && typeof data === "object" && "features" in data) {
      // Bbox search returns FeatureCollection
      const fc = data as any;
      pins = fc.features.map((feature: any) => ({
        id: feature.properties?.id,
        latitude: feature.geometry?.coordinates?.[1],
        longitude: feature.geometry?.coordinates?.[0],
        estimated_value: feature.properties?.estimated_value,
        report_status: feature.properties?.report_status ?? null,
        slug: feature.properties?.slug ?? null,
        address: feature.properties?.address ?? null,
      }));
    }

    source.setData({
      type: "FeatureCollection",
      features: pins.map((pin) => ({
        type: "Feature" as const,
        geometry: {
          type: "Point" as const,
          coordinates: [pin.longitude, pin.latitude],
        },
        properties: {
          id: pin.id,
          estimated_value: pin.estimated_value,
          report_status: pin.report_status,
          slug: pin.slug,
          address: pin.address,
        },
      })),
    });
  }, []);

  useEffect(() => {
    updatePins(pins);
  }, [pins, updatePins]);

  return (
    <div
      ref={containerRef}
      className="h-full w-full"
      data-testid="map-container"
    />
  );
}
