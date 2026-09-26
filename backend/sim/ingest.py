"""Load the demo workbook (or uploaded CSVs) into pandas frames."""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
WORKBOOK = ROOT / "data" / "restaurant_demo_data.xlsx"
DEMO_DIR = ROOT / "backend" / "data" / "demo"

TABLES = ["ingredients", "menu", "recipes", "sales", "purchases",
          "inventory_counts", "events"]
DATE_COLS = {
    "sales": ["date"], "purchases": ["date"], "inventory_counts": ["date"],
    "events": ["start_date", "end_date"],
}


def load_workbook(path: Path = WORKBOOK) -> dict[str, pd.DataFrame]:
    sheets = pd.read_excel(path, sheet_name=None)
    data = {}
    for name in TABLES:
        df = sheets[name].copy()
        for col in DATE_COLS.get(name, []):
            df[col] = pd.to_datetime(df[col])
        data[name] = df
    data["customer_profile"] = sheets["customer_profile"].copy()
    return data


def export_csvs(data: dict[str, pd.DataFrame], out: Path = DEMO_DIR) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name, df in data.items():
        df.to_csv(out / f"{name}.csv", index=False, date_format="%Y-%m-%d")


if __name__ == "__main__":
    export_csvs(load_workbook())
    print(f"wrote CSVs to {DEMO_DIR}")
