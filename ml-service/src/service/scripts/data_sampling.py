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
#df

# %%
print("before sampling:")
print(df.Label.value_counts())

# %%
# Randomly sample instances from majority classes
df_minor = df[(df['Label']=='WebAttack')|(df['Label']=='Bot')|(df['Label']=='Infiltration')]
df_BENIGN = df[(df['Label']=='BENIGN')]
df_BENIGN = df_BENIGN.sample(n=None, frac=0.01, replace=False, weights=None, random_state=None, axis=0)
df_DoS = df[(df['Label']=='DoS')]
df_DoS = df_DoS.sample(n=None, frac=0.05, replace=False, weights=None, random_state=None, axis=0)
df_PortScan = df[(df['Label']=='PortScan')]
df_PortScan = df_PortScan.sample(n=None, frac=0.05, replace=False, weights=None, random_state=None, axis=0)
df_BruteForce = df[(df['Label']=='BruteForce')]
df_BruteForce = df_BruteForce.sample(n=None, frac=0.2, replace=False, weights=None, random_state=None, axis=0)

# %%
df_s = pd.concat(
    [df_BENIGN, df_DoS, df_PortScan, df_BruteForce, df_minor],
    ignore_index=True
)


print(df_s.shape)
print(df_s["Label"].value_counts())

# %%
df_s = df_s.sort_index()
# Save the sampled dataset
output_path = PROJECT_ROOT / "data" / "cicids2017_sampled.csv"
df_s.to_csv(output_path, index=0)

print(f"\nSampled dataset saved successfully to {output_path}!")

# %%



