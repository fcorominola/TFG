import osmnx as ox
import psycopg2
import random
from shapely.wkb import dumps
from shapely.geometry import LineString
from shapely.errors import WKBReadingError

# Connexió a la base de datos
conn = psycopg2.connect(
    dbname="accessibility_map",
    user="postgres",
    password="040494",
    host="localhost",
    port="5432"
)
cur = conn.cursor()

# Descarrega del graf de carrers
place_name = "Sant Andreu, Barcelona, Spain"
G = ox.graph_from_place(place_name, network_type='all')
edges = ox.graph_to_gdfs(G, nodes=False, edges=True)

# Diccionari de mock data segons el tipus de carrers
highway_specs = {
    'primary':           {'width': (3.0, 5.0), 'surface': ['asphalt'], 'smoothness': ['excellent']},
    'primary_link':      {'width': (2.5, 4.5), 'surface': ['asphalt'], 'smoothness': ['excellent']},
    'secondary':         {'width': (2.5, 4.0), 'surface': ['asphalt', 'paving_stones'], 'smoothness': ['good']},
    'secondary_link':    {'width': (2.5, 3.5), 'surface': ['asphalt'], 'smoothness': ['good', 'intermediate']},
    'tertiary':          {'width': (2.0, 3.0), 'surface': ['asphalt', 'paving_stones'], 'smoothness': ['good', 'intermediate']},
    'tertiary_link':     {'width': (2.0, 2.5), 'surface': ['asphalt'], 'smoothness': ['intermediate']},
    'residential':       {'width': (1.5, 3.0), 'surface': ['asphalt', 'paving_stones', 'sett'], 'smoothness': ['good']},
    'living_street':     {'width': (2.0, 3.5), 'surface': ['paving_stones', 'sett'], 'smoothness': ['good', 'excellent']},
    'pedestrian':        {'width': (2.5, 5.0), 'surface': ['paving_stones', 'concrete'], 'smoothness': ['excellent']},
    'footway':           {'width': (1.0, 2.5), 'surface': ['paving_stones', 'concrete'], 'smoothness': ['good']},
    'cycleway':          {'width': (1.5, 2.5), 'surface': ['asphalt', 'concrete'], 'smoothness': ['excellent', 'good']},
    'path':              {'width': (1.0, 2.0), 'surface': ['compacted', 'dirt', 'gravel'], 'smoothness': ['intermediate']},
    'steps':             {'width': (0.0, 0.0), 'surface': ['concrete', 'sett'], 'smoothness': ['impassable']},
    'track':             {'width': (1.0, 2.0), 'surface': ['compacted', 'gravel'], 'smoothness': ['bad']},
    'service':           {'width': (1.5, 3.0), 'surface': ['asphalt', 'concrete', 'paving_stones'], 'smoothness': ['good', 'intermediate']},
    'trunk':             {'width': (3.0, 5.0), 'surface': ['asphalt'], 'smoothness': ['excellent']},
    'trunk_link':        {'width': (2.5, 4.5), 'surface': ['asphalt'], 'smoothness': ['excellent']},
    'motorway_link':     {'width': (3.0, 5.0), 'surface': ['asphalt'], 'smoothness': ['excellent']},
    'corridor':          {'width': (1.5, 3.0), 'surface': ['concrete', 'wood'], 'smoothness': ['good']}
}

for idx, row in edges.iterrows():
    try:
        osm_id = row.get('osmid')
        name = row.get('name')
        highway = row.get('highway')
        surface = row.get('surface')
        condition = row.get('smoothness')
        geom = row['geometry']

        # Validar geometría
        if not isinstance(geom, LineString) or geom.is_empty or not geom.is_valid:
            continue

        # Validar campos
        if not osm_id or not highway:
            continue

        # Normalitzar camps
        if isinstance(highway, list):
            highway = highway[0]

        spec = highway_specs.get(highway, {'width': (1.0, 2.0), 'surface': ['asphalt'], 'smoothness': ['good']})

        sidewalk_width = round(random.uniform(*spec['width']), 2)
        slope_percentage = round(random.uniform(0, 5), 2)
        intersection_slope_percentage = round(random.uniform(0, 4), 2)

        if not surface:
            surface = random.choice(spec['surface'])
        if not condition:
            condition = random.choice(spec['smoothness'])

        # Insert a la base de dades
        cur.execute("""
            INSERT INTO streets_2 (
                osm_id, street_name, highway_type, sidewalk_width,
                slope_percentage, intersection_slope_percentage,
                surface_type, surface_condition, geom
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, ST_GeomFromWKB(%s, 4326))
        """, (
            str(osm_id),
            name,
            highway,
            sidewalk_width,
            slope_percentage,
            intersection_slope_percentage,
            surface,
            condition,
            dumps(geom)
        ))

    except Exception as e:
        print(f"Error insert street osm_id {osm_id}: {e}")
        continue

# Finalitzar
conn.commit()
cur.close()
conn.close()
print("Insert finalitzat correctament.")
