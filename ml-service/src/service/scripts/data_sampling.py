# %%
import pandas as pd
import numpy as np

import matplotlib.pyplot as plt
import seaborn as sns

from pathlib import Path

# %%
PROJECT_ROOT = Path.cwd().parent

path = PROJECT_ROOT / "data" / "combine" / "cicids2017_combined.csv"
df = pd.read_csv(path)
# df

# %%
print(df.Label.value_counts())

# %%
# Sampling fractions for each original class
sampling_rates = {
    "BENIGN": 0.01,
    "DoS Hulk": 0.05,
    "DDoS": 0.05,
    "PortScan": 0.05,
    "DoS GoldenEye": 0.20,
    "DoS slowloris": 0.20,
    "DoS Slowhttptest": 0.20,
    "FTP-Patator": 0.50,
    "SSH-Patator": 0.50,
    "Web Attack - Brute Force": 1.00,
    "Web Attack - XSS": 1.00,
    "Web Attack - Sql Injection": 1.00,
    "Bot": 1.00,
    "Infiltration": 1.00,
    "Heartbleed": 1.00,
}

# Sample each class independently
sampled_dfs = []

for label, frac in sampling_rates.items():
    class_df = df[df["Label"] == label]

    if class_df.empty:
        print(f"WARNING: No records found for {label}")
        continue

    sampled_df = class_df.sample(
        frac=frac,
        random_state=42
    )

    sampled_dfs.append(sampled_df)

    print(f"{label}: {len(class_df):,} -> {len(sampled_df):,}")


# %%
# Combine sampled classes
df_s = pd.concat(
    sampled_dfs,
    ignore_index=True
)

# Shuffle rows
df_s = df_s.sample(frac=1, random_state=42).reset_index(drop=True)

print("\nSampled dataset shape:", df_s.shape)
print("\nClass distribution:")
print(df_s["Label"].value_counts())

# %%
# Save the sampled dataset
output_path = PROJECT_ROOT / "data" / "cicids2017_sampled.csv"
df_s.to_csv(output_path, index=0)

print(f"\nSampled dataset saved successfully to {output_path}!")


