import osmnx as ox
import psycopg2
from shapely.geometry import Point
import random

# Connexió bas de dades
conn = psycopg2.connect(
    dbname="accessibility_map",
    user="postgres",
    password="040494",
    host="localhost",
    port="5432"
)
cur = conn.cursor()

place_name = "Sant Andreu, Barcelona, Catalonia, Spain"

tags = {
    "highway": "crossing"
}

gdf = ox.features_from_place(place_name, tags)

inserted = 0

for idx, row in gdf.iterrows():
    if row.geometry.geom_type != 'Point':
        continue

    osm_id = idx[1]  # OSM ID de l'element
    geom = row.geometry

    # 1. Tipus de pas de vianants
    crossing_tag = row.get("crossing", "normal")
    if crossing_tag == "traffic_signals":
        crossing_type = "amb semàfor"
    elif crossing_tag == "zebra":
        crossing_type = "normal"
    elif crossing_tag == "raised":
        crossing_type = "elevat"
    else:
        crossing_type = crossing_tag or "normal"

    # 2. Amplada (real si hi és)
    width = None
    try:
        width_value = row.get("width", None)
        width = float(width_value) if width_value is not None else round(random.uniform(4.0, 6.0), 2)
    except (ValueError, TypeError):
        width = round(random.uniform(4.0, 6.0), 2)

    # 3. Paviment tàctil
    tactile_raw = row.get("tactile_paving")
    if isinstance(tactile_raw, str):
        tactile_pavement = tactile_raw.lower() == "yes"
    else:
        tactile_pavement = bool(random.choices([True, False], weights=[0.5, 0.5])[0])

    # Contrast de color (no disponible a OSM, mock sempre)
    color_contrast = bool(random.choices([True, False], weights=[0.5, 0.5])[0])

    # Inserció a la base de dades
    try:
        cur.execute("""
            INSERT INTO pedestrian_crossing (
                osm_id, crossing_type, width,
                tactile_pavement, color_contrast, geom
            ) VALUES (
                %s, %s, %s, %s, %s, ST_GeomFromText(%s, 4326)
            )
        """, (
            str(osm_id),
            crossing_type,
            width,
            tactile_pavement,
            color_contrast,
            geom.wkt
        ))
        inserted += 1
    except Exception as e:
        print(f"Error en osm_id {osm_id}: {e}")
        conn.rollback()

conn.commit()
cur.close()
conn.close()

print(f"Inserts correctes a la base de dades")

