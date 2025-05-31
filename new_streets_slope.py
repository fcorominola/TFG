import geopandas as gpd
import psycopg2
import rasterio
from shapely import wkb
from shapely.geometry import LineString

# Connexió base de dades
DB_CONFIG = {
    "dbname": "accessibility_map",
    "user": "postgres",
    "password": "040494",
    "host": "localhost",
    "port": "5432"
}

# Document rasterio amb les altituds extret del IGC
DEM_PATH = "C:/Users/user/Desktop/Data science/TFG/Python_Code/TFG/data/output_hh.tif"

# Funció per obtenir altitud d'un punt
def get_elevation_from_dem(dem_path, lon, lat):
    with rasterio.open(dem_path) as dem:
        coords = [(lon, lat)]
        values = list(dem.sample(coords))
        return values[0][0] if values and values[0][0] != dem.nodata else None

conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor()

cur.execute("""
    SELECT id, osm_id, ST_AsEWKB(geom)
    FROM streets_2
    WHERE geom IS NOT NULL AND NOT ST_IsEmpty(geom)
""")

streets_data = cur.fetchall()

print(f"S'han carregat {len(streets_data)} carrers.")

# Preparamos lista para pendientes
slope_records = []

with rasterio.open(DEM_PATH) as dem:
    for street_id, osm_id, geom_wkb in streets_data:
        try:
            if geom_wkb is None:
                continue
            # Si es memoryview, convertir a bytes
            if isinstance(geom_wkb, memoryview):
                geom_wkb = bytes(geom_wkb)
            geom_wgs84 = wkb.loads(geom_wkb, hex=False)
        except Exception as e:
            print(f"Error geom del street_id {street_id}: {e}")
            continue

        if not isinstance(geom_wgs84, LineString):
            continue

        try:
            start_lon, start_lat = geom_wgs84.coords[0]
            end_lon, end_lat = geom_wgs84.coords[-1]
        except (IndexError, ValueError):
            continue

        elev_start = get_elevation_from_dem(DEM_PATH, start_lon, start_lat)
        elev_end = get_elevation_from_dem(DEM_PATH, end_lon, end_lat)

        if elev_start is not None and elev_end is not None:
            # Convertir a UTM (EPSG:25831) para medir distàncies reals en metres
            geom_utm = gpd.GeoSeries([geom_wgs84], crs="EPSG:4326").to_crs(epsg=25831).iloc[0]
            dx = geom_utm.length

            if dx > 0:
                slope_pct = round(((elev_end - elev_start) / dx) * 100, 2)
                slope_records.append({
                    "street_id": street_id,
                    "osm_id": osm_id,
                    "altitude_start": elev_start,
                    "altitude_end": elev_end,
                    "slope_percentage": slope_pct,
                    "geom": geom_wgs84
                })

# Convertir a GeoDataFrame per insertar a la base de dades
slopes_gdf = gpd.GeoDataFrame(slope_records, geometry="geom", crs="EPSG:4326")

print("Inserint pendents a la base de dades...")
insert_sql = """
    INSERT INTO street_slopes (street_id, osm_id, altitude_start, altitude_end, slope_percentage, geom)
    VALUES (%s, %s, %s, %s, %s, ST_GeomFromText(%s, 4326))
"""

for _, row in slopes_gdf.iterrows():
    cur.execute(insert_sql, (
        row["street_id"],
        row["osm_id"],
        row["altitude_start"],
        row["altitude_end"],
        row["slope_percentage"],
        row["geom"].wkt
    ))

conn.commit()
cur.close()
conn.close()

