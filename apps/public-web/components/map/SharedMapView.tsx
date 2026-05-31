"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type mapboxgl from "mapbox-gl";
import MapContainer from "@/components/map/MapContainer";
import SearchOmnibox from "@/components/map/SearchOmnibox";
import PropertyDetail from "@/components/property/PropertyDetail";
import Toast from "@/components/ui/Toast";
import { UserAvatar } from "@/components/auth/AuthGuard";
import ZoneLayer from "@/components/map/ZoneLayer";
import { useMapBounds } from "@/hooks/useMapBounds";
import { usePropertySearch } from "@/hooks/usePropertySearch";
import type { SearchSuggestion } from "@/types";

type SharedMapViewProps = {
  initialPropertyId?: string | null;
  initialBbox?: [number, number, number, number] | null;
  initialCoordinates?: [number, number] | null;
  zoneOverlay?: {
    id: string;
    geojson: GeoJSON.FeatureCollection;
    color?: string;
  } | null;
  zoneId?: string | null;
};

export default function SharedMapView({
  initialPropertyId = null,
  initialBbox = null,
  initialCoordinates = null,
  zoneOverlay = null,
  zoneId = null,
}: SharedMapViewProps) {
  const router = useRouter();
  const { bbox, setMap } = useMapBounds();
  const { results } = usePropertySearch(bbox, undefined, zoneId ?? undefined);
  const [selectedId, setSelectedId] = useState<string | null>(initialPropertyId);
  const [mapInstance, setMapInstance] = useState<mapboxgl.Map | null>(null);

  const handleMapReady = useCallback(
    (map: mapboxgl.Map) => {
      setMapInstance(map);
      setMap(map);
    },
    [setMap],
  );

  useEffect(() => {
    if (initialPropertyId) {
      setSelectedId(initialPropertyId);
    }
  }, [initialPropertyId]);

  const handlePinClick = useCallback((propertyId: string, slug?: string) => {
    setSelectedId(propertyId);
    if (slug) {
      window.history.pushState(null, "", `/property/${slug}`);
    }
  }, []);

  const handleSearchSelect = useCallback(
    (result: SearchSuggestion) => {
      // Zone navigations use router.push to trigger a full server component
      // re-render — the new zone's overlay and filtered properties need to
      // be fetched server-side.
      if (result.type === "SUBURB" && result.slug && result.zone_state) {
        router.push(`/suburb/${result.zone_state.toLowerCase()}/${result.slug}`);
        return;
      }
      if (result.type === "SCHOOL_CATCHMENT" && result.slug && result.zone_state) {
        router.push(`/school/${result.zone_state.toLowerCase()}/${result.slug}`);
        return;
      }

      // Address navigations stay client-side — just pan the map and open the panel.
      if (!mapInstance) return;

      if (result.bbox) {
        const [west, south, east, north] = result.bbox;
        mapInstance.fitBounds(
          [
            [west, south],
            [east, north],
          ],
          { padding: 50 },
        );
      } else if (result.coordinates) {
        const [longitude, latitude] = result.coordinates;
        mapInstance.flyTo({
          center: [longitude, latitude],
          zoom: 16,
        });
      }

      if (result.type === "ADDRESS") {
        setSelectedId(result.property_id);
      }

      if (result.type === "ADDRESS" && result.slug) {
        window.history.pushState(null, "", `/property/${result.slug}`);
      }
    },
    [mapInstance, router],
  );

  return (
    <>
      <MapContainer
        pins={results}
        onMapReady={handleMapReady}
        onPinClick={handlePinClick}
        initialBbox={initialBbox}
        initialCoordinates={initialCoordinates}
      />
      <div className="absolute left-4 top-4 z-30">
        <SearchOmnibox onSelect={handleSearchSelect} />
      </div>
      <div className="absolute right-4 top-4 z-30">
        <UserAvatar />
      </div>
      <PropertyDetail
        propertyId={selectedId}
        onClose={() => setSelectedId(null)}
        mode="panel"
      />
      {zoneOverlay && (
        <ZoneLayer
          map={mapInstance}
          id={zoneOverlay.id}
          geojson={zoneOverlay.geojson}
          color={zoneOverlay.color}
        />
      )}
      <Toast />
    </>
  );
}
