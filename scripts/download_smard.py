"""Download SMARD load and generation, 2015 to September 2026."""
from pathlib import Path

from adequacy import smard

RAW = Path(__file__).resolve().parents[1] / "data" / "raw" / "smard"
df = smard.load_all("2015-01-05", "2026-09-30", RAW)
print(df.describe().round(0))
