"""
Service de localisation et de récupération des données solaires.

Priorité des sources :
1. PVGIS : irradiation solaire mensuelle et Peak Sun Hours.
2. Open-Meteo : solution de secours.
3. Valeurs par défaut : uniquement si les services externes échouent.

Les Peak Sun Hours représentent l'énergie solaire journalière reçue,
exprimée en kWh/m²/jour. Cette valeur est adaptée au dimensionnement
d'un panneau photovoltaïque.
"""

from __future__ import annotations

import calendar
import time
from typing import Any

import requests


PVGIS_API_URL = "https://re.jrc.ec.europa.eu/api/v5_3/MRcalc"

OPEN_METEO_ARCHIVE_URL = (
    "https://archive-api.open-meteo.com/v1/archive"
)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

REQUEST_TIMEOUT_SECONDS = 20

# User-Agent identifiable demandé par le service Nominatim.
USER_AGENT = (
    "IoTEnergyAssistant/1.0 "
    "(academic-project; contact: hadilsaadaoui44@gmail.com)"
)

# Petit cache en mémoire pour éviter de refaire les mêmes appels.
_solar_cache: dict[tuple[float, float], dict[str, Any]] = {}
_geocoding_cache: dict[tuple[str, str], dict[str, float] | None] = {}

# Permet de respecter un délai entre les appels Nominatim.
_last_nominatim_request_time = 0.0


def _safe_float(
    value: Any,
    default: float | None = None,
) -> float | None:
    """
    Convertit une valeur en float sans provoquer d'exception.
    """
    if value in (None, ""):
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _validate_coordinates(
    latitude: Any,
    longitude: Any,
) -> tuple[float, float]:
    """
    Vérifie et normalise les coordonnées.
    """
    lat = _safe_float(latitude)
    lon = _safe_float(longitude)

    if lat is None or lon is None:
        raise ValueError(
            "Latitude et longitude obligatoires."
        )

    if not -90 <= lat <= 90:
        raise ValueError(
            "La latitude doit être comprise entre -90 et 90."
        )

    if not -180 <= lon <= 180:
        raise ValueError(
            "La longitude doit être comprise entre -180 et 180."
        )

    return lat, lon


def _default_values(
    warning: str = (
        "Les données solaires externes sont indisponibles. "
        "Des valeurs par défaut ont été utilisées."
    ),
) -> dict[str, Any]:
    """
    Valeurs de secours utilisées uniquement si les API échouent.
    """
    return {
        "annual": 4.5,
        "worst": 3.0,
        "best": 6.0,
        "worst_month": None,
        "best_month": None,
        "monthly": [],
        "source": "default",
        "unit": "kWh/m²/jour",
        "warning": warning,
    }


def _extract_pvgis_irradiation(
    monthly_record: dict[str, Any],
) -> float | None:
    """
    Extrait l'irradiation mensuelle depuis une ligne PVGIS.

    PVGIS peut utiliser différents noms selon les options ou versions :
    - H(h)_m : irradiation horizontale mensuelle ;
    - H(i)_m : irradiation sur le plan incliné ;
    - H(i_opt)_m : irradiation sur inclinaison optimale.
    """
    possible_keys = (
        "H(h)_m",
        "H(i)_m",
        "H(i_opt)_m",
        "H_opt_m",
        "H_m",
    )

    for key in possible_keys:
        value = _safe_float(monthly_record.get(key))

        if value is not None:
            return value

    # Recherche secondaire robuste :
    # première clé ressemblant à une énergie mensuelle H(... )_m.
    for key, raw_value in monthly_record.items():
        key_text = str(key)

        if key_text.startswith("H(") and key_text.endswith("_m"):
            value = _safe_float(raw_value)

            if value is not None:
                return value

    return None


def _get_solar_data_from_pvgis(
    latitude: float,
    longitude: float,
) -> dict[str, Any] | None:
    """
    Récupère les données mensuelles d'irradiation depuis PVGIS.

    Certaines réponses PVGIS contiennent plusieurs années. Les valeurs
    sont donc regroupées par numéro de mois, puis moyennées afin de
    retourner exactement une entrée pour chacun des 12 mois.

    PVGIS fournit l'irradiation en kWh/m²/mois. Elle est convertie en
    Peak Sun Hours journalières avec la formule :

        PSH = irradiation mensuelle moyenne / nombre de jours du mois
    """
    params = {
        "lat": latitude,
        "lon": longitude,
        "horirrad": 1,
        "optrad": 0,
        "selectrad": 0,
        "angle": 0,
        "aspect": 0,
        "avtemp": 1,
        "outputformat": "json",
    }

    response = requests.get(
        PVGIS_API_URL,
        params=params,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    payload = response.json()
    monthly_records = (
        payload
        .get("outputs", {})
        .get("monthly", [])
    )

    if not monthly_records:
        return None

    # PVGIS peut renvoyer plusieurs années. On rassemble toutes les
    # irradiations disponibles pour chaque mois de l'année.
    irradiation_by_month: dict[int, list[float]] = {
        month: []
        for month in range(1, 13)
    }

    for record in monthly_records:
        month_number = record.get("month")

        try:
            month_number = int(month_number)
        except (TypeError, ValueError):
            continue

        if not 1 <= month_number <= 12:
            continue

        irradiation_month = _extract_pvgis_irradiation(record)

        if (
            irradiation_month is None
            or irradiation_month <= 0
        ):
            continue

        irradiation_by_month[month_number].append(
            irradiation_month
        )

    # Pour garantir un profil annuel cohérent, les 12 mois doivent être
    # disponibles. Sinon, Open-Meteo prendra le relais.
    if any(
        not irradiation_by_month[month]
        for month in range(1, 13)
    ):
        return None

    monthly_values: list[dict[str, Any]] = []
    annual_irradiation = 0.0

    for month_number in range(1, 13):
        values = irradiation_by_month[month_number]
        average_irradiation = sum(values) / len(values)

        # Une année non bissextile donne le nombre standard de jours.
        days_in_month = calendar.monthrange(
            2023,
            month_number,
        )[1]

        psh_per_day = average_irradiation / days_in_month
        annual_irradiation += average_irradiation

        monthly_values.append({
            "month": month_number,
            "month_name": calendar.month_name[month_number],
            "irradiation_kwh_m2_month": round(
                average_irradiation,
                3,
            ),
            "peak_sun_hours": round(
                psh_per_day,
                3,
            ),
        })

    # Moyenne journalière annuelle pondérée par le nombre de jours.
    annual_average = annual_irradiation / 365

    worst_record = min(
        monthly_values,
        key=lambda item: item["peak_sun_hours"],
    )

    best_record = max(
        monthly_values,
        key=lambda item: item["peak_sun_hours"],
    )

    return {
        "annual": round(annual_average, 2),
        "worst": round(
            worst_record["peak_sun_hours"],
            2,
        ),
        "best": round(
            best_record["peak_sun_hours"],
            2,
        ),
        "worst_month": worst_record["month"],
        "worst_month_name": worst_record["month_name"],
        "best_month": best_record["month"],
        "best_month_name": best_record["month_name"],
        "monthly": monthly_values,
        "source": "PVGIS",
        "unit": "kWh/m²/jour",
        "warning": None,
    }

def _get_solar_data_from_open_meteo(
    latitude: float,
    longitude: float,
) -> dict[str, Any] | None:
    """
    Solution de secours utilisant Open-Meteo.

    On récupère le rayonnement solaire journalier, puis on le convertit
    approximativement en kWh/m²/jour.

    Cette solution est utilisée uniquement si PVGIS ne répond pas.
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": "2021-01-01",
        "end_date": "2025-12-31",
        "daily": "shortwave_radiation_sum",
        "timezone": "auto",
    }

    response = requests.get(
        OPEN_METEO_ARCHIVE_URL,
        params=params,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )

    response.raise_for_status()

    payload = response.json()
    daily = payload.get("daily", {})

    dates = daily.get("time", [])
    radiation_values = daily.get(
        "shortwave_radiation_sum",
        [],
    )

    if not dates or not radiation_values:
        return None

    monthly_groups: dict[int, list[float]] = {
        month: []
        for month in range(1, 13)
    }

    valid_daily_values: list[float] = []

    for date_string, radiation in zip(
        dates,
        radiation_values,
    ):
        radiation_value = _safe_float(radiation)

        if (
            radiation_value is None
            or radiation_value <= 0
        ):
            continue

        try:
            month_number = int(
                str(date_string)[5:7]
            )
        except (TypeError, ValueError):
            continue

        if not 1 <= month_number <= 12:
            continue

        # Open-Meteo fournit cette variable en MJ/m².
        # Conversion approximative :
        # 1 kWh = 3,6 MJ.
        psh_value = radiation_value / 3.6

        monthly_groups[month_number].append(psh_value)
        valid_daily_values.append(psh_value)

    if not valid_daily_values:
        return None

    monthly_values: list[dict[str, Any]] = []

    for month_number in range(1, 13):
        values = monthly_groups[month_number]

        if not values:
            continue

        average_psh = sum(values) / len(values)

        monthly_values.append({
            "month": month_number,
            "month_name": calendar.month_name[month_number],
            "peak_sun_hours": round(
                average_psh,
                3,
            ),
        })

    if not monthly_values:
        return None

    annual_average = sum(valid_daily_values) / len(
        valid_daily_values
    )

    worst_record = min(
        monthly_values,
        key=lambda item: item["peak_sun_hours"],
    )

    best_record = max(
        monthly_values,
        key=lambda item: item["peak_sun_hours"],
    )

    return {
        "annual": round(annual_average, 2),
        "worst": round(
            worst_record["peak_sun_hours"],
            2,
        ),
        "best": round(
            best_record["peak_sun_hours"],
            2,
        ),
        "worst_month": worst_record["month"],
        "worst_month_name": worst_record["month_name"],
        "best_month": best_record["month"],
        "best_month_name": best_record["month_name"],
        "monthly": monthly_values,
        "source": "Open-Meteo fallback",
        "unit": "kWh/m²/jour",
        "warning": (
            "PVGIS était indisponible. "
            "Les données Open-Meteo ont été utilisées."
        ),
    }


def get_sun_hours(
    latitude: Any,
    longitude: Any,
) -> dict[str, Any]:
    """
    Retourne les Peak Sun Hours moyennes et défavorables.

    Compatibilité conservée avec l'ancien code :

        result["annual"]
        result["worst"]

    Des informations supplémentaires sont également retournées :

        result["monthly"]
        result["source"]
        result["worst_month"]
        result["best"]
    """
    try:
        lat, lon = _validate_coordinates(
            latitude,
            longitude,
        )
    except ValueError as exc:
        return _default_values(str(exc))

    cache_key = (
        round(lat, 4),
        round(lon, 4),
    )

    if cache_key in _solar_cache:
        cached_result = _solar_cache[cache_key].copy()
        cached_result["cached"] = True
        return cached_result

    try:
        result = _get_solar_data_from_pvgis(
            latitude=lat,
            longitude=lon,
        )

        if result is not None:
            result["cached"] = False
            _solar_cache[cache_key] = result.copy()
            return result

    except requests.exceptions.Timeout:
        print("⚠️ PVGIS : délai d'attente dépassé.")

    except requests.exceptions.ConnectionError:
        print("⚠️ PVGIS : connexion impossible.")

    except requests.exceptions.HTTPError as exc:
        print(f"⚠️ PVGIS : erreur HTTP ({exc}).")

    except (ValueError, KeyError, TypeError) as exc:
        print(f"⚠️ PVGIS : réponse invalide ({exc}).")

    except Exception as exc:
        print(f"⚠️ PVGIS : erreur inattendue ({exc}).")

    # Solution de secours.
    try:
        result = _get_solar_data_from_open_meteo(
            latitude=lat,
            longitude=lon,
        )

        if result is not None:
            result["cached"] = False
            _solar_cache[cache_key] = result.copy()
            return result

    except requests.exceptions.Timeout:
        print("⚠️ Open-Meteo : délai d'attente dépassé.")

    except requests.exceptions.ConnectionError:
        print("⚠️ Open-Meteo : connexion impossible.")

    except requests.exceptions.HTTPError as exc:
        print(f"⚠️ Open-Meteo : erreur HTTP ({exc}).")

    except Exception as exc:
        print(
            "⚠️ Open-Meteo : erreur inattendue "
            f"({exc})."
        )

    result = _default_values()
    result["cached"] = False
    _solar_cache[cache_key] = result.copy()

    return result


def get_coordinates_from_city(
    city: str,
    country: str,
) -> dict[str, float] | None:
    """
    Convertit une ville et un pays en latitude/longitude.

    Le résultat est mis en cache pour éviter de répéter les requêtes.
    """
    global _last_nominatim_request_time

    city_value = str(city or "").strip()
    country_value = str(country or "").strip()

    if not city_value or not country_value:
        return None

    cache_key = (
        city_value.lower(),
        country_value.lower(),
    )

    if cache_key in _geocoding_cache:
        return _geocoding_cache[cache_key]

    # Le service public Nominatim demande de ne pas dépasser
    # une requête par seconde.
    elapsed = time.monotonic() - _last_nominatim_request_time

    if elapsed < 1.0:
        time.sleep(1.0 - elapsed)

    params = {
        "city": city_value,
        "country": country_value,
        "format": "jsonv2",
        "limit": 1,
        "addressdetails": 0,
    }

    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "fr",
    }

    try:
        _last_nominatim_request_time = time.monotonic()

        response = requests.get(
            NOMINATIM_URL,
            params=params,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )

        response.raise_for_status()

        records = response.json()

        if not records:
            _geocoding_cache[cache_key] = None
            return None

        latitude = _safe_float(records[0].get("lat"))
        longitude = _safe_float(records[0].get("lon"))

        if latitude is None or longitude is None:
            _geocoding_cache[cache_key] = None
            return None

        result = {
            "latitude": latitude,
            "longitude": longitude,
        }

        _geocoding_cache[cache_key] = result
        return result

    except requests.exceptions.Timeout:
        print("⚠️ Géocodage : délai d'attente dépassé.")

    except requests.exceptions.ConnectionError:
        print("⚠️ Géocodage : connexion impossible.")

    except requests.exceptions.HTTPError as exc:
        print(f"⚠️ Géocodage : erreur HTTP ({exc}).")

    except Exception as exc:
        print(f"⚠️ Erreur de géocodage : {exc}")

    _geocoding_cache[cache_key] = None
    return None