import osmnx as ox
import psycopg2
from shapely.wkb import dumps
import random
import pandas as pd

# Connexió a la BBDD
conn = psycopg2.connect(
    dbname="accessibility_map",
    user="postgres",
    password="040494",
    host="localhost",
    port="5432"
)
cur = conn.cursor()

place_name = "Sant Andreu, Barcelona, Spain"

# Etiquetes OSM d'interès
tags = {
    "amenity": ["bench", "picnic_table", "toilets"],
    "leisure": ["park", "garden"]
}

# Obtenir dades d'OSM
rest_areas_gdf = ox.features_from_place(place_name, tags)
rest_areas_gdf = rest_areas_gdf[rest_areas_gdf.geometry.type == "Point"]

for idx, row in rest_areas_gdf.iterrows():
    osm_type, osm_num_id = row.name
    osm_id = f"{osm_type}/{osm_num_id}"
    geom = row.geometry

    if not geom.is_valid:
        print(f"Geometria invàlida per {osm_id}, s'omet...")
        continue

    # Identificació de tipus (amenity > leisure)
    type_tag = row.get("amenity") or row.get("leisure")
    if pd.isna(type_tag):
        print(f"{osm_id} no té tipus, s'omet...")
        continue

    # Accessibilitat
    wheelchair = row.get("wheelchair")
    is_accessible = True if wheelchair in ["yes", "designated"] else False if wheelchair == "no" else None

    # Descripció i nom (si existeix)
    location_description = row.get("description")
    location_name = row.get("name")

    # MOCK DATA només per bancs
    has_backrest = None
    has_armrest = None
    is_sheltered = False  # per defecte

    if type_tag == "bench":
        has_backrest = random.choices([True, False], weights=[0.9, 0.1])[0]
        has_armrest = random.choices([True, False], weights=[0.9, 0.1])[0]
        is_sheltered = row.get("shelter") == "yes"

    elif type_tag == "picnic_table":
        is_sheltered = row.get("shelter") == "yes"

    try:
        cur.execute("""
            INSERT INTO urban_rest_areas (
                osm_id, type, has_backrest, has_armrest, is_sheltered,
                is_wheelchair_accessible, location_name, location_description, geom
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, ST_GeomFromWKB(%s, 4326))
        """, (
            osm_id,
            type_tag,
            has_backrest,
            has_armrest,
            is_sheltered,
            is_accessible,
            location_name,
            location_description,
            dumps(geom)
        ))
        print(f"Insertat {osm_id} ({type_tag})")
    except psycopg2.Error as e:
        print(f"Error al insertar {osm_id}: {e}")
        conn.rollback()

conn.commit()
cur.close()
conn.close()
