import osmnx as ox
import psycopg2
import random
import numpy as np
from shapely.wkb import dumps
from shapely.geometry import LineString
import pandas as pd


# Connexió a la base de dades
conn = psycopg2.connect(
    dbname="accessibility_map",
    user="postgres",
    password="040494",
    host="localhost",
    port="5432"
)
cur = conn.cursor()

# OSM: rampes i camins
place_name = "Sant Andreu, Barcelona, Spain"
tags = {
    "footway": ["ramp", "sidewalk", "crossing", "steps"],
    "incline": True
}
ramps_gdf = ox.features_from_place(place_name, tags)

ramps_gdf = ramps_gdf[ramps_gdf.geometry.type == "LineString"]

for idx, row in ramps_gdf.iterrows():
    osm_type, osm_num_id = row.name
    osm_id = f"{osm_type}/{osm_num_id}"

    location_name = row.get('name')
    if pd.isna(location_name):
        location_name = "Rampa sense nom"

    geom = row.geometry
    if not isinstance(geom, LineString):
        continue

    # Incline
    incline_tag = row.get('incline')
    incline = None
    try:
        if isinstance(incline_tag, str) and '%' in incline_tag:
            incline = float(incline_tag.replace('%', '').strip())
        elif isinstance(incline_tag, str):
            mapping = {
                'up': random.uniform(4.0, 8.0),
                'down': random.uniform(4.0, 8.0),
                'yes': random.uniform(4.0, 8.0),
                'no': 0.0,
                'steep': random.uniform(8.0, 15.0)
            }
            incline = mapping.get(incline_tag.lower(), random.uniform(4.0, 8.0))
        elif isinstance(incline_tag, (int, float)):
            incline = float(incline_tag)
    except:
        incline = None

    if incline is None or np.isnan(incline):
        incline = round(random.uniform(5.0, 10.0), 2)

    # Longitud
    try:
        geom_proj = ox.project_geometry(geom)[0]
        length = round(geom_proj.length, 2)
    except:
        length = round(random.uniform(2.0, 10.0), 2)

    # Amplada
    width_tag = row.get("width")
    try:
        width = float(width_tag)
    except (TypeError, ValueError):
        width = round(random.uniform(1.2, 2.0), 2)

    if width is None or np.isnan(width):
        width = round(random.uniform(1.2, 2.0), 2)

    # Accessibilitat
    is_accessible = incline <= 10 and width >= 1.2

    # Barana
    bar_enabled = incline > 5

    # Superfície
    surface = row.get("surface")
    if pd.isna(surface):
        surface = random.choice(['asphalt', 'paved'])

    # Inserció
    cur.execute("""
        INSERT INTO ramps (
            osm_id, location_name, incline_percentage,
            length, width, is_accessible, bar_enabled,
            surface_type, geom
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, ST_GeomFromWKB(%s, 4326))
    """, (
        str(osm_id),
        location_name,
        incline,
        length,
        width,
        is_accessible,
        bar_enabled,
        surface,
        dumps(geom)
    ))

conn.commit()
cur.close()
conn.close()
