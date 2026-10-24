"""Download the ERA5 point series (slow on purpose: the free API is rate-limited)."""
from pathlib import Path

from adequacy import weather

RAW = Path(__file__).resolve().parents[1] / "data" / "raw" / "era5"
for name, (lat, lon) in weather.points().items():
    weather.load_point(name, lat, lon, RAW)
    print(name, "done", flush=True)
