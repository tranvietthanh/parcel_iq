import mapboxgl from "mapbox-gl";

const MAPBOX_TOKEN = process.env.NEXT_PUBLIC_MAPBOX_TOKEN ?? "";

/** Default map centre — Sydney, wide enough for national scope */
export const DEFAULT_CENTER: [number, number] = [151.21, -33.87];
export const DEFAULT_ZOOM = 5;
export const MAP_STYLE = "mapbox://styles/mapbox/light-v11";

/**
 * Initialise a Mapbox GL JS map instance on the given container element.
 */
export function createMap(
  container: HTMLElement,
  options?: {
    bounds?: [number, number, number, number];
    center?: [number, number];
    zoom?: number;
  }
): mapboxgl.Map {
  mapboxgl.accessToken = MAPBOX_TOKEN;

  let boundsObj;
  if (options?.bounds) {
    boundsObj = [
      [options.bounds[0], options.bounds[1]],
      [options.bounds[2], options.bounds[3]],
    ] as mapboxgl.LngLatBoundsLike;
  }

  return new mapboxgl.Map({
    container,
    style: MAP_STYLE,
    center: options?.center ?? DEFAULT_CENTER,
    zoom: options?.zoom ?? DEFAULT_ZOOM,
    bounds: boundsObj,
    fitBoundsOptions: boundsObj ? { padding: 50, duration: 0 } : undefined,
    attributionControl: true,
  });
}

/**
 * Extract the bounding box of the current map viewport as [west, south, east, north].
 */
export function getMapBounds(
  map: mapboxgl.Map,
): [number, number, number, number] {
  const bounds = map.getBounds();
  if (!bounds) {
    // Return Australia's approximate bounds as fallback
    return [113.3, -43.6, 153.6, -10.6];
  }
  return [
    bounds.getWest(),
    bounds.getSouth(),
    bounds.getEast(),
    bounds.getNorth(),
  ];
}
