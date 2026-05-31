import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock mapbox-gl
vi.mock("mapbox-gl", () => ({
  default: {
    accessToken: "",
    Map: vi.fn(() => ({
      on: vi.fn(),
      remove: vi.fn(),
      getBounds: vi.fn(() => ({
        getWest: () => 150.0,
        getSouth: () => -34.0,
        getEast: () => 152.0,
        getNorth: () => -33.0,
      })),
    })),
  },
}));

import { createMap, getMapBounds, DEFAULT_CENTER, DEFAULT_ZOOM } from "@/lib/mapbox";
import mapboxgl from "mapbox-gl";

describe("mapbox lib", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("exports default center for Sydney", () => {
    expect(DEFAULT_CENTER).toEqual([151.21, -33.87]);
  });

  it("exports default zoom of 5", () => {
    expect(DEFAULT_ZOOM).toBe(5);
  });

  it("creates a map with correct options", () => {
    const container = document.createElement("div");
    createMap(container);

    expect(mapboxgl.Map).toHaveBeenCalledWith(
      expect.objectContaining({
        container,
        zoom: 5,
        attributionControl: true,
      }),
    );
  });

  it("extracts bounding box from map", () => {
    const mockMap = {
      getBounds: () => ({
        getWest: () => 150.0,
        getSouth: () => -34.0,
        getEast: () => 152.0,
        getNorth: () => -33.0,
      }),
    } as unknown as mapboxgl.Map;

    const bbox = getMapBounds(mockMap);
    expect(bbox).toEqual([150.0, -34.0, 152.0, -33.0]);
  });
});
