import geopandas as gpd
import folium
from folium import Element
from sqlalchemy import create_engine

# --- Configuració conexió DB ---
db_config = {
    "host": "localhost",
    "port": "5432",
    "dbname": "accessibility_map",
    "user": "postgres",
    "password": "040494"
}
tabla_calles = "streets_2"
srid = 4326

engine = create_engine(
    f"postgresql://{db_config['user']}:{db_config['password']}@{db_config['host']}:{db_config['port']}/{db_config['dbname']}"
)

query = f"SELECT * FROM {tabla_calles};"
calles_gdf = gpd.read_postgis(query, engine, geom_col="geom")
calles_gdf = calles_gdf.set_crs(epsg=srid)

#------------CÀLCUL % D'ACCESSIBILITAT CARRERS TAULA street-------------
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

def accessibility_function(row):
    score = 100

    if row['sidewalk_width'] < 1.8:
        score -= 25

    if abs(row['intersection_slope_percentage']) > 4:
        score -= 30
    elif abs(row['intersection_slope_percentage'] )> 2:
        score -= 15

    pendiente = abs(row['slope_percentage'])
    if pendiente <= 2:
        pass
    elif pendiente <= 4:
        score -= 10
    elif pendiente <= 6:
        score -= 20
    else:
        score -= 30

    surface_type = row.get('surface_type', '').lower()
    surface_condition = row.get('surface_condition', 'good').lower()

    base_penalty = surface_type_penalty.get(surface_type, 0)
    condition_mult = surface_condition_multiplier.get(surface_condition, 1)

    penalty = base_penalty * condition_mult
    score -= penalty

    return max(0, min(100, score))

def color_per_score(score):
    if score > 90:
        return 'green'
    elif 70 < score <= 90:
        return 'yellow'
    elif 50 <= score <= 70:
        return 'orange'
    else:
        return 'red'


groups = {
    'Alta (>90%)': folium.FeatureGroup(name='Alta (>90%)'),
    'Mitjana (70-90%)': folium.FeatureGroup(name='Mitjana (70-90%)'),
    'Baixa (50-70%)': folium.FeatureGroup(name='Baixa (50-70%)'),
    'Molt Baixa (<50%)': folium.FeatureGroup(name='Molt Baixa (<50%)'),
}

# Cambiar unary_union por union_all para evitar warning
map_center_geom = calles_gdf.geometry.union_all()
map_center = [map_center_geom.centroid.y, map_center_geom.centroid.x]
calles_gdf['accesibilidad'] = calles_gdf.apply(accessibility_function, axis=1)

m = folium.Map(location=map_center, zoom_start=15, tiles="CartoDB positron")

for _, row in calles_gdf.iterrows():
    score = row['accesibilidad']
    popup_html = folium.Popup(html=f"""
        <b>Nom:</b> {row['street_name']}<br>
        <b>Tipus:</b> {row['highway_type']}<br>
        <b>Amplada vorera:</b> {row['sidewalk_width']} m<br>
        <b>Pendent:</b> {row['slope_percentage']}%<br>
        <b>Pendent intersecció:</b> {row['intersection_slope_percentage']}%<br>
        <b>Superfície:</b> {row['surface_type']}<br>
        <b>Condició superfície:</b> {row['surface_condition']}<br>
        <b>Accesibilitat:</b> {score}%
    """, max_width=300)

    color = color_per_score(score)
    gj = folium.GeoJson(
        data=row['geom'].__geo_interface__,
        style_function=lambda x, col=color: {
            'color': col,
            'weight': 4,
            'opacity': 0.8
        }
    )
    gj.add_child(popup_html)

    if score > 90:
        groups['Alta (>90%)'].add_child(gj)
    elif 70 < score <= 90:
        groups['Mitjana (70-90%)'].add_child(gj)
    elif 50 <= score <= 70:
        groups['Baixa (50-70%)'].add_child(gj)
    else:
        groups['Molt Baixa (<50%)'].add_child(gj)

for g in groups.values():
    g.add_to(m)

folium.LayerControl(collapsed=False).add_to(m)

legend_html = """
<div style="
    position: fixed;
    bottom: 50px;
    left: 50px;
    width: 180px;
    height: 150px;
    background-color: white;
    border:2px solid grey;
    z-index:9999;
    font-size:14px;
    padding: 10px;
    box-shadow: 3px 3px 6px rgba(0,0,0,0.3);
">
    <b>Leyenda accesibilidad</b><br>
    <i style="background:green; width:18px; height:18px; float:left; margin-right:8px;"></i> Alta (>90%)<br>
    <i style="background:yellow; width:18px; height:18px; float:left; margin-right:8px;"></i> Mitjana (70-90%)<br>
    <i style="background:orange; width:18px; height:18px; float:left; margin-right:8px;"></i> Baixa (50-70%)<br>
    <i style="background:red; width:18px; height:18px; float:left; margin-right:8px;"></i> Molt Baixa (<50%)<br>
</div>
"""

legend = Element(legend_html)
m.get_root().html.add_child(legend)

m.save("xarxa_accessibility_sant_andreu.html")

