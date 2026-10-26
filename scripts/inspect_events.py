import pandas as pd

df_imd = pd.read_csv('data/pune_imd_rainfall.csv')
events = ['2016-08-02', '2016-08-03', '2019-08-03', '2019-08-04', '2021-07-22', '2021-07-23', '2024-07-25', '2025-08-20', '2023-08-15']

print("--- HISTORICAL REPLAY CANDIDATE SUMMARY ---")
for ev in events:
    sub = df_imd[df_imd['date'] == ev]
    d_max = sub['rainfall_mm_per_day'].max()
    d_mean = sub['rainfall_mm_per_day'].mean()
    pune_row = sub[(sub['latitude'] == 18.5) & (sub['longitude'] == 73.75)]
    pune_val = pune_row['rainfall_mm_per_day'].values[0] if len(pune_row) else 0.0
    # Also find cell with max rainfall
    max_row = sub.loc[sub['rainfall_mm_per_day'].idxmax()]
    print(f"Date: {ev} | Max: {d_max:.1f} mm at ({max_row['latitude']},{max_row['longitude']}) | Mean: {d_mean:.1f} mm | Pune Cell (18.5, 73.75): {pune_val:.1f} mm")
