import sys
from pathlib import Path

try:
    import fiona
except ImportError:
    print("fiona is not installed. Please run `uv sync` in infra/scripts first.")
    sys.exit(1)

DATA_DIR = Path(__file__).parent.parent.parent / "data"

def inspect_shapefile(name: str):
    shp_path = DATA_DIR / name
    if not shp_path.exists():
        print(f"Error: {shp_path} does not exist.")
        return

    print("=" * 60)
    print(f"INSPECTING: {shp_path.name}")
    print("=" * 60)

    try:
        with fiona.open(shp_path) as src:
            print(f"Driver: {src.driver}")
            print(f"CRS: {src.crs}")
            print(f"Bounds: {src.bounds}")
            print(f"Feature count: {len(src)}")
            print("\nSchema properties:")
            for k, v in src.schema["properties"].items():
                print(f"  - {k}: {v}")

            print("\nSample features (first 3):")
            for i, feat in enumerate(src):
                if i >= 3:
                    break
                print(f"\n--- Feature #{i+1} ---")
                print(f"ID: {feat.get('id')}")
                print("Properties:")
                props = feat.get("properties", {})
                for k, v in props.items():
                    print(f"  {k}: {v}")
                
                geom = feat.get("geometry", {})
                geom_type = geom.get("type") if geom else "None"
                print(f"Geometry type: {geom_type}")
                if geom and geom_type == "Point":
                    print(f"Geometry coordinates: {geom.get('coordinates')}")
                elif geom:
                    coords = geom.get("coordinates", [])
                    print(f"Geometry coordinate parts: {len(coords)}")
    except Exception as e:
        print(f"Error reading shapefile {name}: {e}")

    print("\n" + "=" * 60 + "\n")

if __name__ == "__main__":
    inspect_shapefile("LGA_2025_AUST_GDA2020.shp")
    inspect_shapefile("SAL_2021_AUST_GDA2020.shp")
