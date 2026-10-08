from __future__ import annotations

import math


BATTERY_DATABASE = {
    "lipo": {
        "name": "LiPo 3.7 V",
        "voltage": 3.7,
        "depth_of_discharge": 0.80,
        "system_efficiency": 0.90,
        "cycle_life": 500,
        "price_per_wh": 0.15,
        "rechargeable": True,
        "weight_per_1000mah_g": 20,
        "volume_per_1000mah_cm3": 8,
        "pros": "Légère, compacte et bonne densité énergétique",
        "cons": "Sensible à la surcharge et à la perforation",
    },

    "18650": {
        "name": "Li-ion 18650 3.7 V",
        "voltage": 3.7,
        "depth_of_discharge": 0.80,
        "system_efficiency": 0.90,
        "cycle_life": 800,
        "price_per_wh": 0.10,
        "rechargeable": True,
        "weight_per_1000mah_g": 15,
        "volume_per_1000mah_cm3": 6,
        "pros": "Bonne capacité, économique et facilement disponible",
        "cons": "Nécessite un circuit de protection adapté",
    },

    "lifepo4": {
        "name": "LiFePO4 3.2 V",
        "voltage": 3.2,
        "depth_of_discharge": 0.90,
        "system_efficiency": 0.92,
        "cycle_life": 2000,
        "price_per_wh": 0.20,
        "rechargeable": True,
        "weight_per_1000mah_g": 30,
        "volume_per_1000mah_cm3": 12,
        "pros": "Très longue durée de vie, stable et sécurisée",
        "cons": "Plus lourde et plus chère",
    },

    "nimh": {
        "name": "NiMH 1.2 V",
        "voltage": 1.2,
        "depth_of_discharge": 0.70,
        "system_efficiency": 0.75,
        "cycle_life": 1000,
        "price_per_wh": 0.08,
        "rechargeable": True,
        "weight_per_1000mah_g": 25,
        "volume_per_1000mah_cm3": 10,
        "pros": "Économique, robuste et recyclable",
        "cons": "Auto-décharge élevée et rendement plus faible",
    },

    "alkaline": {
        "name": "Pile alcaline 1.5 V",
        "voltage": 1.5,
        "depth_of_discharge": 0.85,
        "system_efficiency": 0.90,
        "cycle_life": 1,
        "price_per_wh": 0.05,
        "rechargeable": False,
        "weight_per_1000mah_g": 12,
        "volume_per_1000mah_cm3": 5,
        "pros": "Disponible partout et peu coûteuse",
        "cons": "Non rechargeable et produit des déchets",
    },

    "lithium_coin": {
        "name": "CR2032 3 V",
        "voltage": 3.0,
        "depth_of_discharge": 0.80,
        "system_efficiency": 0.90,
        "cycle_life": 1,
        "price_per_wh": 0.50,
        "rechargeable": False,
        "weight_per_1000mah_g": 10,
        "volume_per_1000mah_cm3": 3,
        "max_capacity_mah": 230,
        "pros": "Très compacte et faible auto-décharge",
        "cons": "Très faible capacité et courant de sortie limité",
    },
}


# ============================================================
# DEVISES
# ============================================================
# Les prix de BATTERY_DATABASE sont des prix de référence en EUR.
# Le budget saisi par l'utilisateur est converti en EUR avant comparaison.
#
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

# Valeurs par défaut pour vérifier une batterie sans technologie connue.
DEFAULT_DEPTH_OF_DISCHARGE = 0.80
DEFAULT_SYSTEM_EFFICIENCY = 0.90


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


def _positive_or_none(value) -> float | None:
    if value in (None, ""):
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    return number if number > 0 else None


def compare_batteries(
    daily_wh: float,
    autonomy_days: float = 3,
    rechargeable_only: bool = True,
    max_weight_g: float | None = None,
    max_volume_cm3: float | None = None,
    max_budget: float | None = None,
    preferred_type: str | None = None,
    safety_factor: float = 1.25,
    currency: str | None = None,
) -> dict:
    """
    Compare plusieurs technologies de batteries (mode « Recommander »).

    Paramètres
    ----------
    daily_wh:
        Consommation énergétique quotidienne du système en Wh/jour.

    autonomy_days:
        Nombre de jours d'autonomie souhaité.

    rechargeable_only:
        Exclut les batteries non rechargeables si True.

    max_weight_g:
        Poids maximal autorisé en grammes.

    max_volume_cm3:
        Volume maximal autorisé en cm³.

    max_budget:
        Budget maximal, exprimé dans la devise `currency`.

    preferred_type:
        Technologie préférée ou "auto".

    safety_factor:
        Marge de sécurité appliquée au besoin énergétique.

    currency:
        Devise du budget (TND, EUR, USD...). Vide = EUR.
    """

    if daily_wh <= 0:
        raise ValueError("daily_wh doit être supérieur à zéro.")

    if autonomy_days <= 0:
        raise ValueError("autonomy_days doit être supérieur à zéro.")

    if safety_factor < 1:
        raise ValueError("safety_factor doit être supérieur ou égal à 1.")

    currency_label, rate_to_eur, currency_warning = _currency_info(currency)

    max_budget_value = _positive_or_none(max_budget)
    max_budget_eur = (
        max_budget_value * rate_to_eur
        if max_budget_value is not None
        else None
    )

    useful_energy_wh = daily_wh * autonomy_days

    results = []

    for key, battery in BATTERY_DATABASE.items():
        if rechargeable_only and not battery["rechargeable"]:
            continue

        voltage = battery["voltage"]
        depth_of_discharge = battery["depth_of_discharge"]
        system_efficiency = battery["system_efficiency"]

        required_energy_wh = (
            useful_energy_wh
            * safety_factor
            / (depth_of_discharge * system_efficiency)
        )

        required_capacity_mah = (
            required_energy_wh
            / voltage
            * 1000
        )

        capacity_mah = math.ceil(required_capacity_mah)

        stored_energy_wh = capacity_mah * voltage / 1000

        weight_g = (
            capacity_mah
            / 1000
            * battery["weight_per_1000mah_g"]
        )

        volume_cm3 = (
            capacity_mah
            / 1000
            * battery["volume_per_1000mah_cm3"]
        )

        # Prix de référence en EUR, puis converti dans la devise utilisateur.
        price_eur = stored_energy_wh * battery["price_per_wh"]
        price_local = price_eur / rate_to_eur

        available_useful_energy_wh = (
            stored_energy_wh
            * depth_of_discharge
            * system_efficiency
        )

        real_autonomy_days = (
            available_useful_energy_wh
            / daily_wh
        )

        valid = True
        reasons_invalid = []
        warnings = []

        if (
            max_weight_g is not None
            and weight_g > max_weight_g
        ):
            valid = False
            reasons_invalid.append(
                f"Trop lourde : {weight_g:.1f} g > "
                f"{max_weight_g:.1f} g"
            )

        if (
            max_volume_cm3 is not None
            and volume_cm3 > max_volume_cm3
        ):
            valid = False
            reasons_invalid.append(
                f"Trop volumineuse : {volume_cm3:.1f} cm³ > "
                f"{max_volume_cm3:.1f} cm³"
            )

        if (
            max_budget_eur is not None
            and price_eur > max_budget_eur
        ):
            valid = False
            reasons_invalid.append(
                f"Trop chère : {price_local:.2f} {currency_label} > "
                f"{max_budget_value:.2f} {currency_label}"
            )

        max_capacity_mah = battery.get("max_capacity_mah")

        if (
            max_capacity_mah is not None
            and capacity_mah > max_capacity_mah
        ):
            valid = False
            reasons_invalid.append(
                f"Capacité demandée trop élevée : "
                f"{capacity_mah} mAh > "
                f"{max_capacity_mah} mAh"
            )

        if key == "lithium_coin" and daily_wh > 0.1:
            warnings.append(
                "Une pile CR2032 n'est pas adaptée aux charges "
                "consommant beaucoup de courant."
            )

        score = 0.0

        if valid:
            score += 100

        score += min(battery["cycle_life"] / 20, 100)
        score -= weight_g * 0.05
        score -= volume_cm3 * 0.05
        score -= price_eur * 0.5

        if battery["rechargeable"]:
            score += 20

        if key == "lifepo4":
            score += 15

        # La préférence utilisateur influence le classement,
        # sans permettre à une option invalide de passer devant une option valide.
        if preferred_type and preferred_type != "auto" and key == preferred_type:
            score += 25

        results.append({
            "key": key,
            "name": battery["name"],
            "voltage": voltage,

            "daily_energy_wh": round(daily_wh, 3),
            "useful_energy_wh": round(useful_energy_wh, 3),
            "required_energy_wh": round(required_energy_wh, 3),
            "stored_energy_wh": round(stored_energy_wh, 3),

            "required_capacity_mah": capacity_mah,

            # Compatibilité éventuelle avec les anciennes vues
            "capacity_mah": capacity_mah,

            "depth_of_discharge_percent": round(
                depth_of_discharge * 100,
                1,
            ),

            "system_efficiency_percent": round(
                system_efficiency * 100,
                1,
            ),

            "weight_g": round(weight_g, 1),
            "volume_cm3": round(volume_cm3, 1),

            # Prix de référence en EUR (compatibilité avec l'existant)
            "price_estimate": round(price_eur, 2),
            # Même prix exprimé dans la devise choisie par l'utilisateur
            "price_estimate_local": round(price_local, 2),
            "currency": currency_label,

            "cycle_life": battery["cycle_life"],
            "autonomy_days": round(real_autonomy_days, 2),
            "rechargeable": battery["rechargeable"],
            "safety_factor": safety_factor,
            "pros": battery["pros"],
            "cons": battery["cons"],
            "valid": valid,
            "reasons_invalid": reasons_invalid,
            "warnings": warnings,
            "score": round(score, 2),
        })

    results.sort(
        key=lambda item: (
            not item["valid"],
            -item["score"],
            item["price_estimate"],
        )
    )

    preferred = None

    preference_warnings = []

    if preferred_type and preferred_type != "auto":
        preferred = next(
            (
                item
                for item in results
                if item["key"] == preferred_type
            ),
            None,
        )

        if preferred is None:
            preference_warnings.append(
                f"Le type de batterie préféré « {preferred_type} » est inconnu."
            )
        elif not preferred["valid"]:
            preference_warnings.append(
                "La batterie préférée ne respecte pas toutes les contraintes."
            )

    best_choice = next(
        (
            item
            for item in results
            if item["valid"]
        ),
        results[0] if results else None,
    )

    global_warnings = list(preference_warnings)

    if currency_warning:
        global_warnings.append(currency_warning)

    if not results:
        global_warnings.append(
            "Aucune technologie de batterie disponible."
        )

    elif not any(item["valid"] for item in results):
        global_warnings.append(
            "Aucune batterie ne respecte toutes les contraintes."
        )

    return {
        "mode": "recommend",
        "best_choice": best_choice,
        "all_options": results,
        "preferred": preferred,

        "daily_wh": round(daily_wh, 3),
        "required_useful_energy_wh": round(
            useful_energy_wh,
            3,
        ),

        "autonomy_days": autonomy_days,
        "safety_factor": safety_factor,
        "currency": currency_label,
        "warnings": global_warnings,
    }


def verify_battery(
    daily_wh: float,
    autonomy_days: float = 3,
    nominal_voltage_v: float | None = None,
    capacity_mah: float | None = None,
    value_scope: str = "pack",
    cells_series: int | None = None,
    cells_parallel: int | None = None,
    technology: str | None = None,
    model_name: str = "",
    rechargeable_only: bool = True,
    max_weight_g: float | None = None,
    max_volume_cm3: float | None = None,
    safety_factor: float = 1.25,
) -> dict:
    """
    Vérifie une batterie déjà choisie par l'utilisateur (mode « Vérifier »).

    Paramètres
    ----------
    nominal_voltage_v, capacity_mah:
        Valeurs saisies dans le formulaire.

    value_scope:
        "pack"  : les valeurs décrivent déjà la batterie complète.
        "cell"  : les valeurs décrivent UNE cellule ; le pack est calculé
                  avec cells_series (tension) et cells_parallel (capacité).

    technology:
        Clé de BATTERY_DATABASE (lipo, 18650...) ou vide si inconnue.
        Elle donne la profondeur de décharge et le rendement ; sans elle,
        des valeurs par défaut sont utilisées et signalées.

    Retour
    ------
    Dictionnaire avec un statut :
        "ok"           : l'autonomie demandée est couverte avec la marge ;
        "marginal"     : couverte sans la marge de sécurité ;
        "insufficient" : autonomie insuffisante.
    """

    if daily_wh <= 0:
        raise ValueError("daily_wh doit être supérieur à zéro.")

    if autonomy_days <= 0:
        raise ValueError("autonomy_days doit être supérieur à zéro.")

    voltage = _positive_or_none(nominal_voltage_v)
    capacity = _positive_or_none(capacity_mah)

    if voltage is None or capacity is None:
        raise ValueError(
            "La tension nominale et la capacité sont nécessaires "
            "pour vérifier la batterie."
        )

    series = int(cells_series) if _positive_or_none(cells_series) else 1
    parallel = int(cells_parallel) if _positive_or_none(cells_parallel) else 1

    warnings: list[str] = []
    reasons_invalid: list[str] = []

    technology_data = BATTERY_DATABASE.get(technology or "")

    if technology_data:
        depth_of_discharge = technology_data["depth_of_discharge"]
        system_efficiency = technology_data["system_efficiency"]
    else:
        depth_of_discharge = DEFAULT_DEPTH_OF_DISCHARGE
        system_efficiency = DEFAULT_SYSTEM_EFFICIENCY
        warnings.append(
            "Technologie non précisée : profondeur de décharge "
            f"{DEFAULT_DEPTH_OF_DISCHARGE:.0%} et rendement "
            f"{DEFAULT_SYSTEM_EFFICIENCY:.0%} utilisés par défaut."
        )

    # --- Pack complet ---
    if value_scope == "cell":
        pack_voltage_v = voltage * series
        pack_capacity_mah = capacity * parallel

        if series == 1 and parallel == 1:
            warnings.append(
                "Les valeurs concernent une cellule seule, mais aucun "
                "montage série/parallèle n'est indiqué : une seule cellule "
                "est considérée."
            )
    else:
        pack_voltage_v = voltage
        pack_capacity_mah = capacity

        if technology_data and series > 1:
            expected_voltage = technology_data["voltage"] * series
            if abs(expected_voltage - voltage) / voltage > 0.15:
                warnings.append(
                    f"{series} cellules en série devraient donner environ "
                    f"{expected_voltage:.1f} V avec cette technologie, mais "
                    f"{voltage:.1f} V est déclaré : vérifiez si les valeurs "
                    "concernent le pack ou une cellule."
                )

    if (
        value_scope == "cell"
        and technology_data
        and abs(technology_data["voltage"] - voltage) / voltage > 0.25
    ):
        warnings.append(
            f"La tension d'une cellule {technology_data['name']} est "
            f"d'environ {technology_data['voltage']:.1f} V, mais "
            f"{voltage:.1f} V est déclaré."
        )

    # --- Énergie ---
    stored_energy_wh = pack_voltage_v * pack_capacity_mah / 1000
    useful_energy_wh = stored_energy_wh * depth_of_discharge * system_efficiency

    needed_without_margin_wh = daily_wh * autonomy_days
    needed_with_margin_wh = needed_without_margin_wh * safety_factor

    real_autonomy_days = useful_energy_wh / daily_wh

    if useful_energy_wh >= needed_with_margin_wh:
        status = "ok"
    elif useful_energy_wh >= needed_without_margin_wh:
        status = "marginal"
        warnings.append(
            "L'autonomie demandée est couverte, mais sans la marge de "
            f"sécurité de {safety_factor:.2f}."
        )
    else:
        status = "insufficient"
        reasons_invalid.append(
            f"Autonomie réelle {real_autonomy_days:.2f} jour(s) "
            f"< {autonomy_days:g} jour(s) demandés"
        )

    missing_capacity_mah = 0
    if status != "ok":
        required_capacity_mah = (
            needed_with_margin_wh
            / (depth_of_discharge * system_efficiency)
            / pack_voltage_v
            * 1000
        )
        missing_capacity_mah = max(
            0,
            math.ceil(required_capacity_mah - pack_capacity_mah),
        )

    # --- Rechargeable ---
    if (
        rechargeable_only
        and technology_data
        and not technology_data["rechargeable"]
    ):
        reasons_invalid.append(
            "Cette technologie n'est pas rechargeable alors que "
            "« Batterie rechargeable uniquement » est coché."
        )

    # --- Poids / volume (estimations selon la technologie) ---
    estimated_weight_g = None
    estimated_volume_cm3 = None

    if technology_data:
        estimated_weight_g = (
            pack_capacity_mah
            / 1000
            * technology_data["weight_per_1000mah_g"]
            * (pack_voltage_v / technology_data["voltage"])
        )
        estimated_volume_cm3 = (
            pack_capacity_mah
            / 1000
            * technology_data["volume_per_1000mah_cm3"]
            * (pack_voltage_v / technology_data["voltage"])
        )

        if max_weight_g is not None and estimated_weight_g > max_weight_g:
            reasons_invalid.append(
                f"Poids estimé trop élevé : {estimated_weight_g:.1f} g > "
                f"{max_weight_g:.1f} g"
            )

        if max_volume_cm3 is not None and estimated_volume_cm3 > max_volume_cm3:
            reasons_invalid.append(
                f"Volume estimé trop élevé : {estimated_volume_cm3:.1f} cm³ > "
                f"{max_volume_cm3:.1f} cm³"
            )
    elif max_weight_g is not None or max_volume_cm3 is not None:
        warnings.append(
            "Poids et volume non vérifiés : la technologie n'est pas précisée."
        )

    if technology == "lithium_coin" and daily_wh > 0.1:
        warnings.append(
            "Une pile CR2032 n'est pas adaptée aux charges "
            "consommant beaucoup de courant."
        )

    valid = status != "insufficient" and not reasons_invalid

    return {
        "mode": "verify",
        "model_name": (model_name or "").strip(),
        "technology": technology or "",
        "technology_name": (
            technology_data["name"] if technology_data else ""
        ),
        "value_scope": value_scope,

        "status": status,
        "valid": valid,
        "reasons_invalid": reasons_invalid,
        "warnings": warnings,

        "pack_voltage_v": round(pack_voltage_v, 3),
        "pack_capacity_mah": round(pack_capacity_mah, 1),
        "cells_series": series,
        "cells_parallel": parallel,

        "stored_energy_wh": round(stored_energy_wh, 3),
        "useful_energy_wh": round(useful_energy_wh, 3),
        "depth_of_discharge_percent": round(depth_of_discharge * 100, 1),
        "system_efficiency_percent": round(system_efficiency * 100, 1),

        "daily_wh": round(daily_wh, 3),
        "autonomy_days_requested": autonomy_days,
        "autonomy_days_real": round(real_autonomy_days, 2),
        "needed_energy_wh": round(needed_with_margin_wh, 3),
        "safety_factor": safety_factor,
        "missing_capacity_mah": missing_capacity_mah,

        "estimated_weight_g": (
            round(estimated_weight_g, 1)
            if estimated_weight_g is not None
            else None
        ),
        "estimated_volume_cm3": (
            round(estimated_volume_cm3, 1)
            if estimated_volume_cm3 is not None
            else None
        ),
    }