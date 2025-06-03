import geopandas as gpd
import networkx as nx
from shapely.geometry import Point, LineString
from shapely.ops import unary_union, transform
from sqlalchemy import create_engine, text
import folium
import numpy as np
from pyproj import Transformer
from shapely.geometry import mapping
import json
from scipy.spatial import KDTree

from diagnostics import (
    accesibilidad_estandar_diagnostic,
    accesibilidad_con_preferencias_diagnostic
)

def cerca_ruta(user_id, pre_form_id):
    DB_URL = 'postgresql://postgres:040494@localhost:5432/accessibility_map'
    engine = create_engine(DB_URL)

    streets = gpd.read_postgis("SELECT * FROM streets", engine, geom_col='geom')
    ramps = gpd.read_postgis("SELECT * FROM ramps", engine, geom_col='geom')
    obstacles = gpd.read_postgis("SELECT geom FROM urban_obstacles", engine, geom_col='geom')
    rest_areas = gpd.read_postgis("SELECT * FROM urban_rest_areas", engine, geom_col='geom')

    streets = streets.to_crs(epsg=25831)
    ramps = ramps.to_crs(epsg=25831)
    obstacles = obstacles.to_crs(epsg=25831)
    rest_areas = rest_areas.to_crs(epsg=25831)

    query_search = f"""
            SELECT origin_lat, origin_lon, dest_lat, dest_lon, id
            FROM searches
            WHERE userid = {user_id} and fk_preform_id = {pre_form_id}
            ORDER BY id DESC
            LIMIT 1
        """
    with engine.connect() as connection:
        result = connection.execute(text(query_search))
        search_result = result.fetchone()

    if not search_result:
        raise ValueError(f"No s'ha trobat cap cerca per l'usuari={user_id}")

    origin_lat, origin_lon, dest_lat, dest_lon, search_id = search_result
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:25831", always_xy=True)
    start_x, start_y = transformer.transform(origin_lon, origin_lat)
    end_x, end_y = transformer.transform(dest_lon, dest_lat)

    start_point = Point(start_x, start_y)
    end_point = Point(end_x, end_y)

    buffer_area = unary_union([start_point.buffer(2000), end_point.buffer(2000)])
    streets = streets[streets.intersects(buffer_area)]
    ramps = ramps[ramps.intersects(buffer_area)]

    obstacle_sindex = obstacles.sindex
    rest_area_sindex = rest_areas.sindex

    query_preferences = f"""
            SELECT evitar_escales, dificultats_rampes, baranes, preferencia_pendents,
                   carrers_estrets, zones_descans
            FROM pre_form_answers
            WHERE userid = {user_id} AND id = {pre_form_id}
            LIMIT 1
        """
    with engine.connect() as connection:
        result = connection.execute(text(query_preferences))
        preferences_row = result.fetchone()

    if not preferences_row:
        raise ValueError(f"No s'han trobat preferències per l'usuari={user_id} i preform_id={pre_form_id}")

    preferencias = {
        "evitar_escales": preferences_row[0],
        "dificultats_rampes": preferences_row[1],
        "baranes": preferences_row[2],
        "preferencia_pendents": preferences_row[3],
        "carrers_estrets": preferences_row[4],
        "zones_descans": preferences_row[5]
    }

    surface_type_penalty = {
        'concrete': 0,
        'asphalt': 0,
        'wood': 10,
        'compacted': 10,
        'paving_stones': 30,
        'dirt': 30,
        'gravel': 30,
        'sett': 30
    }

    surface_condition_multiplier = {
        'good': 0.5,
        'intermediate': 1,
        'bad': 1.5,
        'impassable': 2
    }

    street_weights = []
    for _, row in streets.iterrows():
        score = 1
        width = row.get('sidewalk_width', 2)
        slope = abs(row.get('slope_percentage', 0))
        inter_slope = abs(row.get('intersection_slope_percentage', 0))
        surface_type = str(row.get('surface_type', '')).lower()
        surface_condition = str(row.get('surface_condition', 'good')).lower()
        base_penalty = surface_type_penalty.get(surface_type, 0)
        condition_mult = surface_condition_multiplier.get(surface_condition, 1)
        length = row['geom'].length

        if preferencias["carrers_estrets"]:
            if width < 1.5:
                score += 100
            elif width < 1.8:
                score += 30

        if preferencias["preferencia_pendents"]:
            if slope > 4:
                score += 100
            elif slope > 2:
                score += 30

        if inter_slope > 4:
            score += 30
        elif inter_slope > 2:
            score += 15

        score += base_penalty * condition_mult

        if surface_condition == 'impassable':
            score += 100
        elif surface_condition == 'bad':
            score += 50

        nearby = list(obstacle_sindex.query(row['geom'].buffer(1.5), predicate='intersects'))
        if nearby:
            score += 20

        if preferencias["zones_descans"] != "No":
            distancia_max = 200 if "200" in preferencias["zones_descans"] else 100
            tramo_centro = row['geom'].interpolate(0.5, normalized=True)
            zonas_cercanas = list(rest_area_sindex.query(tramo_centro.buffer(distancia_max), predicate='intersects'))
            if not zonas_cercanas:
                score += 50

        score = min(score, 100)
        cost = score * length if length > 0 else 100
        street_weights.append(cost)

    streets['weight'] = street_weights

    ramp_weights = []
    for _, row in ramps.iterrows():
        incline = row.get('incline_percentage', 5)
        width = row.get('width', 1.5)
        cost = 1
        if preferencias["dificultats_rampes"] and incline > 6:
            cost += 100
        if preferencias["baranes"] and not row.get('has_handrail', True):
            cost += 50
        if width < 1.2:
            cost += 30
        ramp_weights.append(cost)

    ramps['weight'] = ramp_weights

    G = nx.Graph()
    for _, row in streets.iterrows():
        coords = list(row['geom'].coords)
        for i in range(len(coords) - 1):
            start, end = coords[i], coords[i + 1]
            G.add_edge(start, end, weight=row['weight'], type='street')

    node_coords = list(G.nodes)
    kdtree = KDTree(node_coords)

    for _, row in ramps.iterrows():
        coords = list(row['geom'].coords)
        start = coords[0]
        _, idx = kdtree.query(start)
        nearest_node = node_coords[idx]
        G.add_edge(start, nearest_node, weight=row['weight'], type='ramp')

    _, idx = kdtree.query((start_point.x, start_point.y))
    start_node = node_coords[idx]
    _, idx = kdtree.query((end_point.x, end_point.y))
    end_node = node_coords[idx]

    path = nx.shortest_path(G, source=start_node, target=end_node, weight='weight')

    line_geom = LineString(path)
    transformer = Transformer.from_crs("EPSG:25831", "EPSG:4326", always_xy=True)

    def project_geom(geom):
        return transform(transformer.transform, geom)

    line_geom_4326 = project_geom(line_geom)

    geojson_geom = mapping(line_geom_4326)

    acc_estandar, _, _ = accesibilidad_estandar_diagnostic(streets.copy(), ramps.copy())

    acc_preferencies, _, _ = accesibilidad_con_preferencias_diagnostic(
        streets.copy(), ramps.copy(), preferencias
    )

    with engine.connect() as conn:
        conn.execute(
            text("""
                INSERT INTO routes (id_search, accessibility, accessibility_preferences, geojson)
                VALUES (:id_search, :acc_estandar, :acc_pref, :geojson)
            """),
            {
                "id_search": search_id,
                "acc_estandar": float(round(acc_estandar, 2)),
                "acc_pref": float(round(acc_preferencies, 2)),
                "geojson": json.dumps(geojson_geom)
            }
        )
        conn.commit()

    return geojson_geom

if __name__ == "__main__":
    import sys
    uid = int(sys.argv[1])
    pid = int(sys.argv[2])
    ruta = cerca_ruta(uid, pid)
    print(json.dumps(ruta))