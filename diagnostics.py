import geopandas as gpd

def accesibilidad_estandar_diagnostic(streets, ramps):
    surface_type_penalty = {
        'concrete': 0, 'asphalt': 0, 'wood': 10, 'compacted': 10,
        'paving_stones': 30, 'dirt': 30, 'gravel': 30, 'sett': 30
    }
    surface_condition_multiplier = {
        'good': 0.5, 'intermediate': 1, 'bad': 1.5, 'impassable': 2
    }

    diagnostics, weights = [], []

    for _, row in streets.iterrows():
        width = row.get('sidewalk_width', 2)
        slope = abs(row.get('slope_percentage', 0))
        inter_slope = abs(row.get('intersection_slope_percentage', 0))
        surface = str(row.get('surface_type', '')).lower()
        condition = str(row.get('surface_condition', 'good')).lower()

        base = surface_type_penalty.get(surface, 0)
        mult = surface_condition_multiplier.get(condition, 1)
        score = base * mult

        if condition == 'impassable':
            score += 100
        elif condition == 'bad':
            score += 50

        diag = []
        if width < 1.5:
            score += 20
            diag.append("vorera estreta")
        if slope > 4:
            score += 20
            diag.append("pendent excessiva")
        if inter_slope > 4:
            score += 10
            diag.append("pendent en cruïlla")

        score = min(score, 100)
        diagnostics.append(", ".join(diag) if diag else "correcte")
        weights.append(score)

    streets['weight'] = weights
    streets['diagnostic'] = diagnostics

    diagnostics, weights = [], []

    for _, row in ramps.iterrows():
        width = row.get('width', 1.5)
        incline = row.get('incline_percentage', 5)
        has_handrail = row.get('has_handrail', True)
        length = row['geom'].length

        score = 0
        diag = []
        if length <= 1.5 and incline > 10:
            score += 30
            diag.append("pendent > 10%")
        elif length <= 3 and incline > 8:
            score += 30
            diag.append("pendent > 8%")
        elif length > 3 and incline > 6:
            score += 30
            diag.append("pendent > 6%")

        if incline > 5 and not has_handrail:
            score += 20
            diag.append("sense baranes")

        if width < 1.2:
            score += 20
            diag.append("amplada insuficient")

        score = min(score, 100)
        diagnostics.append(", ".join(diag) if diag else "correcte")
        weights.append(score)

    ramps['weight'] = weights
    ramps['diagnostic'] = diagnostics

    total_length = streets['geom'].length.sum() + ramps['geom'].length.sum()
    if total_length == 0:
        percent = 0
    else:
        weighted = (
            (streets['weight'] * streets['geom'].length).sum() +
            (ramps['weight'] * ramps['geom'].length).sum()
        )
        percent = 100 - (weighted / total_length)

    return percent, streets, ramps


def accesibilidad_con_preferencias_diagnostic(streets, ramps, preferencias):
    diagnostics, weights = [], []

    for _, row in streets.iterrows():
        width = row.get('sidewalk_width', 2)
        slope = abs(row.get('slope_percentage', 0))
        inter_slope = abs(row.get('intersection_slope_percentage', 0))
        surface = str(row.get('surface_type', '')).lower()
        condition = str(row.get('surface_condition', 'good')).lower()
        base = 0
        mult = 1

        score = 0
        diag = []

        if preferencias.get("carrers_estrets", False):
            if width < 1.5:
                score += 30
                diag.append("carrer estret (preferència)")
            elif width < 1.8:
                score += 15
                diag.append("carrer una mica estret")

        if preferencias.get("preferencia_pendents", False):
            if slope > 4:
                score += 30
                diag.append("pendent elevada (preferència)")
            elif slope > 2:
                score += 15
                diag.append("pendent mitjana")

        if inter_slope > 4:
            score += 10
            diag.append("pendent en cruïlla")

        if surface:
            base_penalty = {
                'concrete': 0, 'asphalt': 0, 'wood': 10, 'compacted': 10,
                'paving_stones': 30, 'dirt': 30, 'gravel': 30, 'sett': 30
            }.get(surface, 0)
            mult = {
                'good': 0.5, 'intermediate': 1, 'bad': 1.5, 'impassable': 2
            }.get(condition, 1)
            score += base_penalty * mult
            if base_penalty > 0:
                diag.append(f"tipus paviment {surface} ({base_penalty * mult:.1f})")

        if condition == 'impassable':
            score += 100
            diag.append("estat impracticable (+100)")
        elif condition == 'bad':
            score += 50
            diag.append("estat dolent (+50)")

        score = min(score, 100)
        diagnostics.append(", ".join(diag) if diag else "correcte")
        weights.append(score)

    streets['weight'] = weights
    streets['diagnostic'] = diagnostics

    diagnostics, weights = [], []

    for _, row in ramps.iterrows():
        incline = row.get('incline_percentage', 5)
        width = row.get('width', 1.5)
        has_handrail = row.get('has_handrail', True)

        score = 0
        diag = []

        if preferencias.get("dificultats_rampes", False):
            if incline > 6:
                score += 30
                diag.append("rampa inclinada (preferència)")

        if preferencias.get("baranes", False) and not has_handrail:
            score += 20
            diag.append("sense baranes (preferència)")

        if width < 1.2:
            score += 20
            diag.append("amplada insuficient")

        score = min(score, 100)
        diagnostics.append(", ".join(diag) if diag else "correcte")
        weights.append(score)

    ramps['weight'] = weights
    ramps['diagnostic'] = diagnostics

    total_length = streets['geom'].length.sum() + ramps['geom'].length.sum()
    if total_length == 0:
        percent = 0
    else:
        weighted = (
            (streets['weight'] * streets['geom'].length).sum() +
            (ramps['weight'] * ramps['geom'].length).sum()
        )
        percent = 100 - (weighted / total_length)

    return percent, streets, ramps
