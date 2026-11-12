# %%
import pandas as pd
from pathlib import Path

# %%
# Input and output directories
PROJECT_ROOT = Path.cwd().parent

input_dir = PROJECT_ROOT / "data" / "raw"
output_dir = PROJECT_ROOT / "data" / "combine"

output_dir.mkdir(parents=True, exist_ok=True)

# %%
print(f"Input directory: {input_dir}")
print(f"Output directory: {output_dir}")

# %%
files = sorted(input_dir.glob("*.csv"))

if not files:
    raise FileNotFoundError(f"No CSV files found in {input_dir}")

print(f"Found {len(files)} CSV files")

# %%
# Read and combine
dataframes = []

for file in files:
    print(f"Reading: {file.name}")

    df = pd.read_csv(file)
    df.columns = df.columns.str.strip()

    # Preserve original file information
    df["Source_File"] = file.name

    dataframes.append(df)


combined_df = pd.concat(
    dataframes,
    ignore_index=True,
    sort=False
)

# %%
output_file = output_dir / "cicids2017_combined.csv"
combined_df.to_csv(output_file, index=False)

# %%
print("\nDataset combined successfully!")
print(f"Total rows: {len(combined_df):,}")
print(f"Total columns: {len(combined_df.columns)}")
print(f"Saved to: {output_file}")

# %%



