import pandas as pd

df_glc = pd.read_csv('data/Global_Landslide_Catalog_Export_rows__3_.csv')
india = df_glc[df_glc['country_name'] == 'India']
mh = india[(india['latitude'] >= 17.5) & (india['latitude'] <= 19.5) & (india['longitude'] >= 73.0) & (india['longitude'] <= 75.0)].copy()

print(f"Total candidate rows: {len(mh)}")
for idx, r in mh.iterrows():
    loc = str(r['location_description'])
    print(f"ID: {r['event_id']} | Date: {r['event_date']} | Lat/Lon: ({r['latitude']:.4f}, {r['longitude']:.4f}) | Loc: {loc} | Trigger: {r['landslide_trigger']} | Fatalities: {r['fatality_count']}")
