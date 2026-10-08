"""
Service de dimensionnement et de comparaison des technologies
de panneaux solaires.

Principe important :
- La puissance nominale du panneau en Wc est calculée à partir de
  l'énergie quotidienne, des heures de soleil équivalentes et des
  pertes globales du système.
- Le rendement de la technologie photovoltaïque n'est pas utilisé
  une deuxième fois dans le calcul de puissance, car la puissance Wc
  représente déjà la puissance électrique nominale du panneau.
- La technologie influence surtout la surface, le prix, la durée de vie
  et la pertinence selon le type d'installation.

Deux modes :
- compare_panels() : « Recommander un panneau » ;
- verify_panel()   : « Vérifier mon panneau ».
Le mode « Sans alimentation solaire » n'appelle aucune fonction de ce module.
"""

from __future__ import annotations

from typing import Any


# ============================================================
# BASE DE DONNÉES DES TECHNOLOGIES DE PANNEAUX
# ============================================================

PANEL_DATABASE = {
    "monocrystalline": {
        "name": "Monocristallin",
        "efficiency": 0.20,
        "price_per_watt": 1.50,
        "lifespan_years": 25,
        "surface_per_watt_cm2": 50,
        "indoor_score": 0.45,
        "outdoor_score": 0.90,
        "pros": "Bon rendement, faible surface et longue durée de vie",
        "cons": "Prix relativement élevé",
    },
    "polycrystalline": {
        "name": "Polycristallin",
        "efficiency": 0.15,
        "price_per_watt": 1.00,
        "lifespan_years": 20,
        "surface_per_watt_cm2": 70,
        "indoor_score": 0.35,
        "outdoor_score": 0.75,
        "pros": "Bon compromis entre prix et performance",
        "cons": "Surface nécessaire plus importante",
    },
    "amorphous": {
        "name": "Amorphe / Couche mince",
        "efficiency": 0.08,
        "price_per_watt": 0.50,
        "lifespan_years": 10,
        "surface_per_watt_cm2": 130,
        "indoor_score": 0.90,
        "outdoor_score": 0.50,
        "pros": "Fonctionne mieux en faible lumière et peut être flexible",
        "cons": "Faible rendement et grande surface nécessaire",
    },
    "perc": {
        "name": "PERC",
        "efficiency": 0.22,
        "price_per_watt": 1.80,
        "lifespan_years": 25,
        "surface_per_watt_cm2": 45,
        "indoor_score": 0.55,
        "outdoor_score": 1.00,
        "pros": "Très bon rendement et bonne performance en faible lumière",
        "cons": "Prix élevé",
    },
    "bifacial": {
        "name": "Bifacial",
        "efficiency": 0.21,
        "price_per_watt": 1.70,
        "lifespan_years": 25,
        "surface_per_watt_cm2": 48,
        "indoor_score": 0.20,
        "outdoor_score": 0.85,
        "pros": "Peut produire sur les deux faces avec une installation adaptée",
        "cons": "Installation plus complexe et peu adaptée en intérieur",
    },
}


# ============================================================
# CONSTANTES DE DIMENSIONNEMENT
# ============================================================

# Pertes du régulateur, câbles, température, conversion et batterie.
DEFAULT_SYSTEM_EFFICIENCY = 0.75

# Marge supplémentaire pour les variations météo et le vieillissement.
DEFAULT_SAFETY_FACTOR = 1.20

# En intérieur, la production solaire est très dépendante de l'éclairage.
# Cette valeur est une hypothèse simplifiée et doit être signalée.
DEFAULT_INDOOR_PRODUCTION_FACTOR = 0.30

# Les prix de PANEL_DATABASE sont des prix de référence en EUR.
# ⚠ Taux APPROXIMATIFS : à vérifier / ajuster avant la soutenance.
CURRENCY_TO_EUR = {
    "EUR": 1.0,
    "€": 1.0,
    "TND": 0.30,
    "DT": 0.30,
    "USD": 0.90,
    "$": 0.90,
}

DEFAULT_CURRENCY = "EUR"


# ============================================================
# OUTILS
# ============================================================

def _to_positive_float(value: Any, default: float | None = None) -> float | None:
    """
    Convertit une valeur en nombre positif.

    Retourne default si la valeur est absente, invalide ou négative.
    """
    if value in (None, ""):
        return default

    try:
        number = float(value)
    except (TypeError, ValueError):
        return default

    if number < 0:
        return default

    return number


def _currency_info(currency: str | None) -> tuple[str, float, str | None]:
    """
    Retourne (libellé, taux vers EUR, avertissement éventuel).

    Une devise inconnue est traitée comme de l'EUR, avec un avertissement.
    """
    label = (currency or "").strip().upper() or DEFAULT_CURRENCY
    rate = CURRENCY_TO_EUR.get(label)

    if rate is None:
        return (
            label,
            1.0,
            f"Devise « {label} » inconnue : le budget est comparé "
            "comme s'il était en EUR.",
        )

    return label, rate, None


def installation_type_from_placement(placement: str | None) -> str:
    """
    Convertit l'« Emplacement du panneau » du formulaire en type
    d'installation utilisé par le calcul : "indoor" ou "outdoor".

    Les emplacements « indoor_* » (intérieur, vitre, éclairage artificiel)
    donnent "indoor" ; tout le reste donne "outdoor".
    """
    if str(placement or "").startswith("indoor"):
        return "indoor"

    return "outdoor"


def _orientation_warnings(
    installation_type: str,
    tilt_deg: float | None,
    azimuth_deg: float | None,
) -> list[str]:
    """
    Avertissements d'orientation (hémisphère nord).

    Ils ne modifient pas la puissance calculée : ils signalent seulement
    une orientation susceptible de faire perdre de la production.
    """
    warnings: list[str] = []

    if installation_type != "outdoor":
        return warnings

    if azimuth_deg is not None and abs(azimuth_deg - 180) > 45:
        warnings.append(
            f"Azimut {azimuth_deg:g}° : l'orientation est éloignée du sud "
            "(180°). La production réelle peut être inférieure à l'estimation."
        )

    if tilt_deg is not None and not 10 <= tilt_deg <= 60:
        warnings.append(
            f"Inclinaison {tilt_deg:g}° : en dehors de la plage courante "
            "(10° à 60°). La production réelle peut être inférieure "
            "à l'estimation, et l'accumulation de poussière est plus "
            "probable à faible inclinaison."
        )

    return warnings


def _calculate_required_panel_power(
    daily_wh: float,
    sun_hours_worst: float,
    installation_type: str,
    system_efficiency: float,
    safety_factor: float,
    indoor_production_factor: float,
) -> tuple[float, float]:
    """
    Calcule la puissance nominale minimale du panneau en Wc.

    Formule outdoor :

        Panneau_Wc =
            énergie_quotidienne_Wh
            / (heures_de_soleil_équivalentes × rendement_système)
            × facteur_de_sécurité

    Pour indoor, les heures solaires équivalentes sont réduites
    par un facteur simplifié.

    Returns:
        tuple:
            - puissance nécessaire en Wc ;
            - heures solaires effectives utilisées.
    """
    if daily_wh <= 0:
        return 0.0, 0.0

    if sun_hours_worst <= 0:
        return 0.0, 0.0

    effective_sun_hours = sun_hours_worst

    if installation_type == "indoor":
        effective_sun_hours *= indoor_production_factor

    if effective_sun_hours <= 0 or system_efficiency <= 0:
        return 0.0, effective_sun_hours

    required_power_w = (
        daily_wh
        / (effective_sun_hours * system_efficiency)
        * safety_factor
    )

    return round(required_power_w, 2), round(effective_sun_hours, 3)


def _calculate_option_score(
    option: dict[str, Any],
    installation_type: str,
    max_surface_cm2: float | None,
    max_budget_eur: float | None,
    preferred_type: str | None,
) -> float:
    """
    Produit un score multicritère pour classer les panneaux.

    Le score favorise :
    - le respect des contraintes ;
    - l'adaptation à l'installation ;
    - la durée de vie ;
    - le rendement ;
    - une faible surface ;
    - un prix raisonnable ;
    - la préférence utilisateur.
    """
    score = 0.0

    if option["valid"]:
        score += 100.0
    else:
        score -= 100.0
        score -= 20.0 * len(option["reasons_invalid"])

    if installation_type == "indoor":
        score += option["indoor_score"] * 30.0
    else:
        score += option["outdoor_score"] * 30.0

    score += option["lifespan_years"] * 0.50
    score += option["efficiency_percent"] * 0.50

    # Les normalisations évitent qu'un grand nombre domine entièrement le score.
    score -= option["surface_cm2"] / 1000.0
    score -= option["price_estimate"] * 0.20

    if preferred_type and preferred_type != "auto":
        if option["key"] == preferred_type:
            score += 25.0

    # Bonus lorsque l'option reste bien sous les contraintes.
    if max_surface_cm2 and option["surface_cm2"] <= max_surface_cm2:
        remaining_surface_ratio = (
            max_surface_cm2 - option["surface_cm2"]
        ) / max_surface_cm2
        score += max(0.0, remaining_surface_ratio) * 5.0

    if max_budget_eur and option["price_estimate"] <= max_budget_eur:
        remaining_budget_ratio = (
            max_budget_eur - option["price_estimate"]
        ) / max_budget_eur
        score += max(0.0, remaining_budget_ratio) * 5.0

    return round(score, 3)


# ============================================================
# MODE « RECOMMANDER UN PANNEAU »
# ============================================================

def compare_panels(
    daily_wh: float,
    sun_hours_worst: float,
    installation_type: str = "outdoor",
    max_surface_cm2: float | None = None,
    max_budget: float | None = None,
    preferred_type: str | None = None,
    system_efficiency: float = DEFAULT_SYSTEM_EFFICIENCY,
    safety_factor: float = DEFAULT_SAFETY_FACTOR,
    indoor_production_factor: float = DEFAULT_INDOOR_PRODUCTION_FACTOR,
    currency: str | None = None,
    tilt_deg: float | None = None,
    azimuth_deg: float | None = None,
) -> dict[str, Any]:
    """
    Compare les technologies photovoltaïques selon les besoins du projet.

    Args:
        daily_wh:
            Énergie consommée chaque jour en Wh.

        sun_hours_worst:
            Heures de soleil équivalentes du mois défavorable.
            Idéalement, cette valeur provient de PVGIS ou d'une source
            d'irradiation solaire.

        installation_type:
            "outdoor" ou "indoor" (voir installation_type_from_placement).

        max_surface_cm2:
            Surface solaire totale maximale disponible en cm².

        max_budget:
            Budget maximal, exprimé dans la devise `currency`.

        preferred_type:
            Technologie souhaitée par l'utilisateur ou "auto".

        system_efficiency:
            Rendement global du système solaire :
            régulateur, câbles, batterie, température et conversion.

        safety_factor:
            Marge de sécurité appliquée au dimensionnement.

        indoor_production_factor:
            Facteur simplifié appliqué à la production en intérieur.

        currency:
            Devise du budget (TND, EUR, USD...). Vide = EUR.

        tilt_deg, azimuth_deg:
            Orientation du panneau (facultatif) : utilisée uniquement
            pour produire des avertissements.

    Returns:
        Dictionnaire contenant :
        - best_choice ;
        - all_options ;
        - preferred ;
        - données et hypothèses utilisées ;
        - warnings.
    """
    daily_wh_value = _to_positive_float(daily_wh, 0.0) or 0.0
    sun_hours_value = _to_positive_float(sun_hours_worst, 0.0) or 0.0
    max_surface_value = _to_positive_float(max_surface_cm2)
    max_budget_value = _to_positive_float(max_budget)

    currency_label, rate_to_eur, currency_warning = _currency_info(currency)
    max_budget_eur = (
        max_budget_value * rate_to_eur
        if max_budget_value is not None
        else None
    )

    efficiency_value = _to_positive_float(
        system_efficiency,
        DEFAULT_SYSTEM_EFFICIENCY,
    ) or DEFAULT_SYSTEM_EFFICIENCY

    safety_value = _to_positive_float(
        safety_factor,
        DEFAULT_SAFETY_FACTOR,
    ) or DEFAULT_SAFETY_FACTOR

    indoor_factor_value = _to_positive_float(
        indoor_production_factor,
        DEFAULT_INDOOR_PRODUCTION_FACTOR,
    ) or DEFAULT_INDOOR_PRODUCTION_FACTOR

    installation = str(installation_type or "outdoor").lower().strip()

    if installation not in {"outdoor", "indoor"}:
        installation = "outdoor"

    warnings: list[str] = []

    if currency_warning:
        warnings.append(currency_warning)

    if daily_wh_value <= 0:
        warnings.append(
            "La consommation quotidienne doit être supérieure à zéro."
        )

    if sun_hours_value <= 0:
        warnings.append(
            "Les heures de soleil équivalentes doivent être supérieures à zéro."
        )

    if installation == "indoor":
        warnings.append(
            "Le calcul indoor est une estimation simplifiée. "
            "La production réelle dépend de l'éclairement, du spectre, "
            "de la distance à la source lumineuse et de la durée d'exposition."
        )

    warnings.extend(
        _orientation_warnings(
            installation,
            _to_positive_float(tilt_deg),
            _to_positive_float(azimuth_deg),
        )
    )

    required_panel_w, effective_sun_hours = _calculate_required_panel_power(
        daily_wh=daily_wh_value,
        sun_hours_worst=sun_hours_value,
        installation_type=installation,
        system_efficiency=efficiency_value,
        safety_factor=safety_value,
        indoor_production_factor=indoor_factor_value,
    )

    results: list[dict[str, Any]] = []

    for key, panel in PANEL_DATABASE.items():
        # Tous les panneaux doivent fournir approximativement la même
        # puissance électrique nominale. La technologie change surtout
        # la surface, le coût et la pertinence.
        panel_w = required_panel_w

        surface_cm2 = round(
            panel_w * panel["surface_per_watt_cm2"],
            1,
        )

        # Prix de référence en EUR, puis converti dans la devise utilisateur.
        price_eur = round(
            panel_w * panel["price_per_watt"],
            2,
        )
        price_local = round(price_eur / rate_to_eur, 2)

        valid = True
        reasons_invalid: list[str] = []

        if (
            max_surface_value is not None
            and surface_cm2 > max_surface_value
        ):
            valid = False
            reasons_invalid.append(
                "Surface trop grande "
                f"({surface_cm2} cm² > {max_surface_value} cm²)"
            )

        if (
            max_budget_eur is not None
            and price_eur > max_budget_eur
        ):
            valid = False
            reasons_invalid.append(
                "Budget dépassé "
                f"({price_local} {currency_label} > "
                f"{max_budget_value} {currency_label})"
            )

        option = {
            "key": key,
            "name": panel["name"],
            "panel_w": panel_w,
            "surface_cm2": surface_cm2,

            # Prix de référence en EUR (compatibilité avec l'existant)
            "price_estimate": price_eur,
            # Même prix exprimé dans la devise choisie par l'utilisateur
            "price_estimate_local": price_local,
            "currency": currency_label,

            "lifespan_years": panel["lifespan_years"],
            "efficiency_percent": round(
                panel["efficiency"] * 100,
                1,
            ),
            "pros": panel["pros"],
            "cons": panel["cons"],
            "indoor_score": panel["indoor_score"],
            "outdoor_score": panel["outdoor_score"],
            "valid": valid,
            "reasons_invalid": reasons_invalid,
        }

        option["score"] = _calculate_option_score(
            option=option,
            installation_type=installation,
            max_surface_cm2=max_surface_value,
            max_budget_eur=max_budget_eur,
            preferred_type=preferred_type,
        )

        results.append(option)

    # Valides en premier, puis meilleur score.
    results.sort(
        key=lambda option: (
            not option["valid"],
            -option["score"],
            option["price_estimate"],
        )
    )

    preferred = None

    if preferred_type and preferred_type != "auto":
        preferred = next(
            (
                option
                for option in results
                if option["key"] == preferred_type
            ),
            None,
        )

        if preferred is None:
            warnings.append(
                f"Le type préféré « {preferred_type} » est inconnu."
            )
        elif not preferred["valid"]:
            warnings.append(
                "La technologie préférée ne respecte pas toutes "
                "les contraintes du projet."
            )

    valid_options = [
        option
        for option in results
        if option["valid"]
    ]

    best_choice = valid_options[0] if valid_options else (
        results[0] if results else None
    )

    if results and not valid_options:
        warnings.append(
            "Aucune technologie ne respecte toutes les contraintes. "
            "La première option affichée est la moins défavorable."
        )

    return {
        "mode": "recommend",
        "best_choice": best_choice,
        "all_options": results,
        "preferred": preferred,
        "installation_type": installation,

        "daily_wh": round(daily_wh_value, 4),
        "sun_hours_worst": round(sun_hours_value, 3),
        "effective_sun_hours": effective_sun_hours,

        "required_panel_w": required_panel_w,
        "system_efficiency": round(efficiency_value, 3),
        "safety_factor": round(safety_value, 3),
        "indoor_production_factor": round(
            indoor_factor_value,
            3,
        ),

        "max_surface_cm2": max_surface_value,
        "max_budget": max_budget_value,
        "currency": currency_label,

        "calculation_formula": (
            "P_Wc = daily_Wh / "
            "(effective_sun_hours × system_efficiency) "
            "× safety_factor"
        ),
        "warnings": warnings,
    }


def get_panel_recommendation(
    daily_wh: float,
    sun_hours_worst: float,
    installation_type: str = "outdoor",
) -> dict[str, Any] | None:
    """
    Version simplifiée : retourne uniquement la meilleure recommandation.
    """
    comparison = compare_panels(
        daily_wh=daily_wh,
        sun_hours_worst=sun_hours_worst,
        installation_type=installation_type,
    )

    return comparison["best_choice"]


# ============================================================
# MODE « VÉRIFIER MON PANNEAU »
# ============================================================

def verify_panel(
    daily_wh: float,
    sun_hours_worst: float,
    installation_type: str = "outdoor",
    panel_power_w: float | None = None,
    panel_count: int | None = None,
    technology: str | None = None,
    model_name: str = "",
    vmp_v: float | None = None,
    voc_v: float | None = None,
    imp_ma: float | None = None,
    isc_ma: float | None = None,
    battery_voltage_v: float | None = None,
    max_surface_cm2: float | None = None,
    tilt_deg: float | None = None,
    azimuth_deg: float | None = None,
    system_efficiency: float = DEFAULT_SYSTEM_EFFICIENCY,
    safety_factor: float = DEFAULT_SAFETY_FACTOR,
    indoor_production_factor: float = DEFAULT_INDOOR_PRODUCTION_FACTOR,
) -> dict[str, Any]:
    """
    Vérifie un panneau déjà choisi par l'utilisateur.

    La puissance totale installée (puissance par panneau × nombre) est
    comparée à la puissance minimale calculée par la même formule que
    compare_panels().

    Statut :
        "ok"           : puissance suffisante avec la marge de sécurité ;
        "marginal"     : suffisante sans la marge de sécurité ;
        "insufficient" : puissance insuffisante.

    Les valeurs électriques (Vmp, Voc, Imp, Isc) servent à contrôler la
    cohérence des données saisies ; elles ne modifient pas le calcul
    de puissance.
    """
    daily_wh_value = _to_positive_float(daily_wh, 0.0) or 0.0
    sun_hours_value = _to_positive_float(sun_hours_worst, 0.0) or 0.0

    power_per_panel = _to_positive_float(panel_power_w)
    count = int(panel_count) if _to_positive_float(panel_count) else 1

    if power_per_panel is None or power_per_panel <= 0:
        raise ValueError(
            "La puissance nominale par panneau est nécessaire "
            "pour vérifier le panneau."
        )

    efficiency_value = _to_positive_float(
        system_efficiency,
        DEFAULT_SYSTEM_EFFICIENCY,
    ) or DEFAULT_SYSTEM_EFFICIENCY

    safety_value = _to_positive_float(
        safety_factor,
        DEFAULT_SAFETY_FACTOR,
    ) or DEFAULT_SAFETY_FACTOR

    indoor_factor_value = _to_positive_float(
        indoor_production_factor,
        DEFAULT_INDOOR_PRODUCTION_FACTOR,
    ) or DEFAULT_INDOOR_PRODUCTION_FACTOR

    installation = str(installation_type or "outdoor").lower().strip()

    if installation not in {"outdoor", "indoor"}:
        installation = "outdoor"

    warnings: list[str] = []
    reasons_invalid: list[str] = []

    if daily_wh_value <= 0:
        warnings.append(
            "La consommation quotidienne doit être supérieure à zéro."
        )

    if sun_hours_value <= 0:
        warnings.append(
            "Les heures de soleil équivalentes doivent être supérieures à zéro."
        )

    if installation == "indoor":
        warnings.append(
            "Le calcul indoor est une estimation simplifiée. "
            "La production réelle dépend de l'éclairement, du spectre, "
            "de la distance à la source lumineuse et de la durée d'exposition."
        )

    warnings.extend(
        _orientation_warnings(
            installation,
            _to_positive_float(tilt_deg),
            _to_positive_float(azimuth_deg),
        )
    )

    required_with_margin_w, effective_sun_hours = _calculate_required_panel_power(
        daily_wh=daily_wh_value,
        sun_hours_worst=sun_hours_value,
        installation_type=installation,
        system_efficiency=efficiency_value,
        safety_factor=safety_value,
        indoor_production_factor=indoor_factor_value,
    )

    required_without_margin_w = round(
        required_with_margin_w / safety_value,
        2,
    )

    total_power_w = round(power_per_panel * count, 2)

    if required_with_margin_w <= 0:
        status = "unknown"
        coverage_ratio = None
    else:
        coverage_ratio = round(total_power_w / required_with_margin_w, 3)

        if total_power_w >= required_with_margin_w:
            status = "ok"
        elif total_power_w >= required_without_margin_w:
            status = "marginal"
            warnings.append(
                "La puissance couvre le besoin, mais sans la marge de "
                f"sécurité de {safety_value:.2f}."
            )
        else:
            status = "insufficient"
            reasons_invalid.append(
                f"Puissance installée {total_power_w} Wc < "
                f"{required_without_margin_w} Wc nécessaires"
            )

    # Énergie produite un jour défavorable
    daily_production_wh = round(
        total_power_w * effective_sun_hours * efficiency_value,
        3,
    )

    # --- Technologie, surface ---
    technology_data = PANEL_DATABASE.get(technology or "")
    estimated_surface_cm2 = None

    if technology_data:
        estimated_surface_cm2 = round(
            total_power_w * technology_data["surface_per_watt_cm2"],
            1,
        )

        max_surface_value = _to_positive_float(max_surface_cm2)

        if (
            max_surface_value is not None
            and estimated_surface_cm2 > max_surface_value
        ):
            reasons_invalid.append(
                "Surface estimée trop grande "
                f"({estimated_surface_cm2} cm² > {max_surface_value} cm²)"
            )

        score_key = "indoor_score" if installation == "indoor" else "outdoor_score"
        if technology_data[score_key] < 0.5:
            warnings.append(
                f"La technologie {technology_data['name']} est peu adaptée "
                f"à une installation {'intérieure' if installation == 'indoor' else 'extérieure'}."
            )
    elif _to_positive_float(max_surface_cm2) is not None:
        warnings.append(
            "Surface non vérifiée : la technologie du panneau n'est "
            "pas précisée."
        )

    # --- Cohérence électrique des valeurs saisies ---
    vmp = _to_positive_float(vmp_v)
    voc = _to_positive_float(voc_v)
    imp_a = (_to_positive_float(imp_ma) or 0.0) / 1000 or None
    isc_a = (_to_positive_float(isc_ma) or 0.0) / 1000 or None

    if vmp and imp_a:
        computed_power_w = vmp * imp_a

        if abs(computed_power_w - power_per_panel) / power_per_panel > 0.20:
            warnings.append(
                f"Vmp × Imp = {computed_power_w:.2f} W, mais la puissance "
                f"nominale saisie est {power_per_panel:g} W : vérifiez les "
                "unités (Imp est en mA) et les valeurs."
            )

    if vmp and voc and voc < vmp:
        warnings.append("Voc devrait être supérieure ou égale à Vmp.")

    if imp_a and isc_a and isc_a < imp_a:
        warnings.append("Isc devrait être supérieur ou égal à Imp.")

    battery_voltage = _to_positive_float(battery_voltage_v)

    if vmp and battery_voltage and vmp < battery_voltage * 1.2:
        warnings.append(
            f"Vmp ({vmp:g} V) est proche de la tension de la batterie "
            f"({battery_voltage:g} V) : la charge risque d'être "
            "insuffisante. Vérifiez le régulateur de charge."
        )

    if voc and battery_voltage and voc > battery_voltage * 6:
        warnings.append(
            f"Voc ({voc:g} V) est très supérieure à la tension de la "
            "batterie : vérifiez que le régulateur de charge supporte "
            "cette tension d'entrée."
        )

    valid = status in {"ok", "marginal"} and not reasons_invalid

    return {
        "mode": "verify",
        "model_name": (model_name or "").strip(),
        "technology": technology or "",
        "technology_name": (
            technology_data["name"] if technology_data else ""
        ),
        "installation_type": installation,

        "status": status,
        "valid": valid,
        "reasons_invalid": reasons_invalid,
        "warnings": warnings,

        "panel_power_w": power_per_panel,
        "panel_count": count,
        "total_power_w": total_power_w,

        "daily_wh": round(daily_wh_value, 4),
        "sun_hours_worst": round(sun_hours_value, 3),
        "effective_sun_hours": effective_sun_hours,
        "system_efficiency": round(efficiency_value, 3),
        "safety_factor": round(safety_value, 3),

        "required_panel_w": required_with_margin_w,
        "required_panel_w_without_margin": required_without_margin_w,
        "coverage_ratio": coverage_ratio,
        "daily_production_wh": daily_production_wh,

        "estimated_surface_cm2": estimated_surface_cm2,

        "calculation_formula": (
            "P_Wc = daily_Wh / "
            "(effective_sun_hours × system_efficiency) "
            "× safety_factor"
        ),
    }