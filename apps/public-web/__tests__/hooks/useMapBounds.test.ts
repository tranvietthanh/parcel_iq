import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";

// Mock mapbox-gl
vi.mock("mapbox-gl", () => ({
  default: {
    Map: vi.fn(),
  },
}));

import { useMapBounds } from "@/hooks/useMapBounds";
import type mapboxgl from "mapbox-gl";

describe("useMapBounds", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("returns null bbox initially", () => {
    const { result } = renderHook(() => useMapBounds());
    expect(result.current.bbox).toBeNull();
  });

  it("updates bbox after map moveend with debounce", () => {
    const { result } = renderHook(() => useMapBounds());

    const listeners: Record<string, (() => void)[]> = {};
    const mockMap = {
      on: vi.fn((event: string, cb: () => void) => {
        if (!listeners[event]) listeners[event] = [];
        listeners[event].push(cb);
      }),
      off: vi.fn(),
      getBounds: vi.fn(() => ({
        getWest: () => 150.0,
        getSouth: () => -34.0,
        getEast: () => 152.0,
        getNorth: () => -33.0,
      })),
    } as unknown as mapboxgl.Map;

    act(() => {
      result.current.setMap(mockMap);
    });

    // Initial trigger fires after debounce
    act(() => {
      vi.advanceTimersByTime(400);
    });

    expect(result.current.bbox).toEqual([150.0, -34.0, 152.0, -33.0]);
  });
});
