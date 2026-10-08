from __future__ import annotations

from .services.weather_api import (
    get_sun_hours,
    get_coordinates_from_city,
)
from .services.panel_selector import compare_panels
from .services.battery_selector import compare_batteries


class EnergyCalculator:
    def __init__(self, project):
        self.project = project
        self.warnings = []

    def analyze(self):
        components = list(self.project.components.all())

        if not components:
            return self._empty_result()

        voltage_values = [
            component.voltage or 3.3
            for component in components
        ]

        system_voltage = (
            max(voltage_values)
            if voltage_values
            else 3.3
        )

        # --------------------------------------------------
        # Lecture des modes de fonctionnement
        # --------------------------------------------------

        all_modes = []

        for component in components:
            modes = component.modes.all()

            if not modes.exists():
                self.warnings.append(
                    f"⚠️ {component.name} : Aucun mode saisi."
                )
                continue

            for mode in modes:
                if (
                    mode.current_ma is None
                    or mode.duration_ms is None
                ):
                    continue

                if mode.count_per_cycle <= 0:
                    continue

                all_modes.append(
                    {
                        "name": mode.name,
                        "current_ma": mode.current_ma,
                        "duration_ms": mode.duration_ms,
                        "count": mode.count_per_cycle,
                        "component": component.name,
                        "voltage_v": component.voltage or 3.3,
                    }
                )

        if not all_modes:
            return self._empty_result()

        # --------------------------------------------------
        # Calcul de la consommation d’un cycle
        # --------------------------------------------------

        states = []

        total_energy_mah = 0.0
        total_energy_mwh = 0.0
        total_cycle_ms = 0

        current_min = float("inf")
        current_max = 0.0

        mode_min = ""
        mode_max = ""

        for mode in all_modes:
            energy_mah = (
                mode["current_ma"]
                * mode["duration_ms"]
                * mode["count"]
                / 3_600_000
            )

            energy_mwh = (
                energy_mah
                * mode["voltage_v"]
            )

            power_mw = (
                mode["current_ma"]
                * mode["voltage_v"]
            )

            state = {
                "name": mode["name"],
                "component": mode["component"],
                "current_ma": round(
                    mode["current_ma"],
                    4,
                ),
                "duration_ms": mode["duration_ms"],
                "count": mode["count"],
                "voltage_v": round(
                    mode["voltage_v"],
                    3,
                ),
                "energy_mah": round(
                    energy_mah,
                    6,
                ),
                "energy_mwh": round(
                    energy_mwh,
                    6,
                ),
                "power_mw": round(
                    power_mw,
                    2,
                ),
            }

            states.append(state)

            total_energy_mah += energy_mah
            total_energy_mwh += energy_mwh

            total_cycle_ms += (
                mode["duration_ms"]
                * mode["count"]
            )

            if mode["current_ma"] < current_min:
                current_min = mode["current_ma"]
                mode_min = mode["name"]

            if mode["current_ma"] > current_max:
                current_max = mode["current_ma"]
                mode_max = mode["name"]

        # --------------------------------------------------
        # Pourcentages par état
        # --------------------------------------------------

        for state in states:
            state["energy_percent"] = round(
                (
                    state["energy_mwh"]
                    / max(total_energy_mwh, 0.000001)
                )
                * 100,
                1,
            )

            state["time_percent"] = round(
                (
                    state["duration_ms"]
                    * state["count"]
                    / max(total_cycle_ms, 1)
                )
                * 100,
                1,
            )

        # --------------------------------------------------
        # Consommation quotidienne
        # --------------------------------------------------

        milliseconds_per_day = 86_400_000

        cycles_per_day = int(
            milliseconds_per_day
            / max(total_cycle_ms, 1)
        )

        daily_mah = round(
            total_energy_mah
            * cycles_per_day,
            2,
        )

        daily_mwh = round(
            total_energy_mwh
            * cycles_per_day,
            2,
        )

        daily_wh = round(
            daily_mwh / 1000,
            4,
        )

        avg_current = round(
            total_energy_mah
            * 3_600_000
            / max(total_cycle_ms, 1),
            2,
        )

        avg_power = round(
            total_energy_mwh
            * 3_600_000
            / max(total_cycle_ms, 1),
            2,
        )

        # --------------------------------------------------
        # Courbe de consommation
        # --------------------------------------------------

        curve = []
        time_ms = 0

        for state in states:
            for _ in range(state["count"]):
                curve.append(
                    [time_ms, 0]
                )

                curve.append(
                    [
                        time_ms + 1,
                        state["current_ma"],
                    ]
                )

                end_time = (
                    time_ms
                    + int(state["duration_ms"])
                )

                curve.append(
                    [
                        end_time - 1,
                        state["current_ma"],
                    ]
                )

                curve.append(
                    [end_time, 0]
                )

                time_ms = end_time

        # --------------------------------------------------
        # Préférences batterie
        # --------------------------------------------------

        try:
            battery_preferences = (
                self.project.battery_pref
            )

            battery_autonomy_days = (
                battery_preferences.autonomy_days
                or 3
            )

            battery_preferred_type = (
                battery_preferences.battery_type
            )

            battery_rechargeable_only = (
                battery_preferences.rechargeable_only
            )

            battery_max_weight = (
                battery_preferences.max_weight_g
            )

            battery_max_volume = (
                battery_preferences.max_volume_cm3
            )

            battery_max_budget = (
                battery_preferences.max_budget
            )

        except Exception:
            battery_autonomy_days = 3
            battery_preferred_type = "auto"
            battery_rechargeable_only = True
            battery_max_weight = None
            battery_max_volume = None
            battery_max_budget = None

        # --------------------------------------------------
        # Comparaison des batteries
        # IMPORTANT : dimensionnement en Wh
        # --------------------------------------------------

        battery_comparison = compare_batteries(
            daily_wh=daily_wh,
            autonomy_days=battery_autonomy_days,
            rechargeable_only=battery_rechargeable_only,
            max_weight_g=battery_max_weight,
            max_volume_cm3=battery_max_volume,
            max_budget=battery_max_budget,
            preferred_type=battery_preferred_type,
        )

        chosen_battery = (
            battery_comparison["preferred"]
            if battery_comparison["preferred"]
            else battery_comparison["best_choice"]
        )

        # --------------------------------------------------
        # Adaptateur / régulateur
        # --------------------------------------------------

        peak_current_a = round(
            current_max / 1000,
            3,
        )

        adapter_current_a = round(
            peak_current_a * 1.5,
            2,
        )

        if system_voltage <= 3.3:
            adapter_type = "LDO 3.3 V (AMS1117)"

        elif system_voltage <= 5:
            adapter_type = "Buck DC-DC 5 V vers 3.3 V"

        else:
            adapter_type = "Buck DC-DC ajustable"

        # --------------------------------------------------
        # Données solaires
        # --------------------------------------------------

        sun_data = self._get_real_sun_data()

        installation_type = (
            self.project.installation_type
            or "outdoor"
        )

        try:
            solar_preferences = (
                self.project.solar_pref
            )

            preferred_panel_type = (
                solar_preferences.panel_type
            )

            max_panel_surface = (
                solar_preferences.max_surface_cm2
            )

            max_solar_budget = (
                solar_preferences.max_budget
            )

        except Exception:
            preferred_panel_type = "auto"
            max_panel_surface = None
            max_solar_budget = None

        # --------------------------------------------------
        # Comparaison des panneaux
        # --------------------------------------------------

        panel_comparison = compare_panels(
            daily_wh=daily_wh,
            sun_hours_worst=sun_data["worst"],
            installation_type=installation_type,
            max_surface_cm2=max_panel_surface,
            max_budget=max_solar_budget,
            preferred_type=preferred_panel_type,
        )

        chosen_panel = (
            panel_comparison["preferred"]
            if panel_comparison["preferred"]
            else panel_comparison["best_choice"]
        )

        inclination = int(
            self.project.latitude
            or 35
        )

        # --------------------------------------------------
        # Verdict général
        # --------------------------------------------------

        if daily_wh < 0.01:
            verdict = "Très faible consommation"

        elif daily_wh < 1:
            verdict = "Système basse consommation"

        elif daily_wh < 10:
            verdict = "Système viable"

        elif daily_wh < 50:
            verdict = "Consommation moyenne"

        else:
            verdict = "Consommation élevée"

        # --------------------------------------------------
        # Résultat final
        # --------------------------------------------------

        return {
            "summary": {
                "avg_current_ma": avg_current,
                "min_current_ma": round(
                    current_min,
                    4,
                ),
                "min_current_mode": mode_min,
                "max_current_ma": round(
                    current_max,
                    2,
                ),
                "max_current_mode": mode_max,
                "avg_power_mw": avg_power,
                "daily_energy_mah": daily_mah,
                "daily_energy_wh": daily_wh,
                "voltage": system_voltage,
                "verdict": verdict,
            },

            "energy_profile": {
                "states": states,
                "total_energy_mah": round(
                    total_energy_mah,
                    6,
                ),
                "total_energy_mwh": round(
                    total_energy_mwh,
                    6,
                ),
                "cycle_duration_s": round(
                    total_cycle_ms / 1000,
                    2,
                ),
                "cycles_per_day": cycles_per_day,
                "daily_energy_mah": daily_mah,
                "daily_energy_mwh": daily_mwh,
                "daily_energy_wh": daily_wh,
            },

            "consumption_curve": curve,

            "battery_recommendation": {
                "capacity_mah": (
                    chosen_battery["capacity_mah"]
                    if chosen_battery
                    else 0
                ),
                "required_energy_wh": (
                    chosen_battery[
                        "required_energy_wh"
                    ]
                    if chosen_battery
                    else 0
                ),
                "stored_energy_wh": (
                    chosen_battery[
                        "stored_energy_wh"
                    ]
                    if chosen_battery
                    else 0
                ),
                "voltage": (
                    chosen_battery["voltage"]
                    if chosen_battery
                    else 0
                ),
                "autonomy_days": (
                    chosen_battery[
                        "autonomy_days"
                    ]
                    if chosen_battery
                    else 0
                ),
                "type": (
                    chosen_battery["name"]
                    if chosen_battery
                    else "-"
                ),
                "safety_factor": (
                    chosen_battery[
                        "safety_factor"
                    ]
                    if chosen_battery
                    else 1.25
                ),
                "depth_of_discharge_percent": (
                    chosen_battery[
                        "depth_of_discharge_percent"
                    ]
                    if chosen_battery
                    else 0
                ),
                "system_efficiency_percent": (
                    chosen_battery[
                        "system_efficiency_percent"
                    ]
                    if chosen_battery
                    else 0
                ),
                "weight_g": (
                    chosen_battery["weight_g"]
                    if chosen_battery
                    else 0
                ),
                "volume_cm3": (
                    chosen_battery[
                        "volume_cm3"
                    ]
                    if chosen_battery
                    else 0
                ),
                "price_estimate": (
                    chosen_battery[
                        "price_estimate"
                    ]
                    if chosen_battery
                    else 0
                ),
                "cycle_life": (
                    chosen_battery[
                        "cycle_life"
                    ]
                    if chosen_battery
                    else 0
                ),
                "rechargeable": (
                    chosen_battery[
                        "rechargeable"
                    ]
                    if chosen_battery
                    else True
                ),
                "pros": (
                    chosen_battery["pros"]
                    if chosen_battery
                    else ""
                ),
                "cons": (
                    chosen_battery["cons"]
                    if chosen_battery
                    else ""
                ),
                "valid": (
                    chosen_battery["valid"]
                    if chosen_battery
                    else False
                ),
                "warnings": (
                    chosen_battery["warnings"]
                    if chosen_battery
                    else []
                ),
            },

            "battery_comparison": battery_comparison,

            "adapter_recommendation": {
                "voltage_v": system_voltage,
                "current_a": adapter_current_a,
                "peak_current_a": peak_current_a,
                "type": adapter_type,
            },

            "solar_report": {
                "location": (
                    self.project.location_city
                ),
                "installation_type": (
                    installation_type
                ),
                "sun_hours": (
                    sun_data["annual"]
                ),
                "sun_hours_worst": (
                    sun_data["worst"]
                ),
                "worst_month_name": (
                    sun_data.get(
                        "worst_month_name",
                        "",
                    )
                ),
                "monthly": sun_data.get(
                    "monthly",
                    [],
                ),
                "data_source": sun_data.get(
                    "source",
                    "API",
                ),
                "panel_w": (
                    chosen_panel["panel_w"]
                    if chosen_panel
                    else 0
                ),
                "panel_type": (
                    chosen_panel["name"]
                    if chosen_panel
                    else "-"
                ),
                "panel_efficiency": (
                    chosen_panel[
                        "efficiency_percent"
                    ]
                    / 100
                    if chosen_panel
                    else 0
                ),
                "panel_surface_cm2": (
                    chosen_panel[
                        "surface_cm2"
                    ]
                    if chosen_panel
                    else 0
                ),
                "panel_price": (
                    chosen_panel[
                        "price_estimate"
                    ]
                    if chosen_panel
                    else 0
                ),
                "panel_lifespan": (
                    chosen_panel[
                        "lifespan_years"
                    ]
                    if chosen_panel
                    else 0
                ),
                "charger_efficiency": 0.90,
                "orientation": "Sud",
                "inclination": inclination,
            },

            "panel_comparison": panel_comparison,

            "daily_energy_mah": daily_mah,
            "daily_energy_mwh": daily_mwh,
            "daily_energy_wh": daily_wh,

            "warnings": self.warnings,
        }

    def _get_real_sun_data(self):
        # Utilisation des données déjà enregistrées
        if (
            self.project.sun_hours_annual
            and self.project.sun_hours_worst
        ):
            return {
                "annual": (
                    self.project.sun_hours_annual
                ),
                "worst": (
                    self.project.sun_hours_worst
                ),
                "source": "Cache projet",
            }

        latitude = self.project.latitude
        longitude = self.project.longitude

        # Géocodage si les coordonnées manquent
        if not latitude or not longitude:
            coordinates = get_coordinates_from_city(
                self.project.location_city,
                self.project.location_country,
            )

            if coordinates:
                latitude = coordinates["latitude"]
                longitude = coordinates["longitude"]

                self.project.latitude = latitude
                self.project.longitude = longitude

        if not latitude or not longitude:
            self.warnings.append(
                "⚠️ Impossible de localiser la ville."
            )

            return {
                "annual": 4.5,
                "worst": 3.0,
                "source": "Valeur par défaut",
                "monthly": [],
                "worst_month_name": "",
            }

        # get_sun_hours retourne déjà sa vraie source :
        # PVGIS ou Open-Meteo fallback
        sun_data = get_sun_hours(
            latitude,
            longitude,
        )

        self.project.sun_hours_annual = (
            sun_data["annual"]
        )

        self.project.sun_hours_worst = (
            sun_data["worst"]
        )

        self.project.save()

        return sun_data

    def _empty_result(self):
        self.warnings.append(
            "❌ Aucun mode de fonctionnement saisi."
        )

        return {
            "summary": {
                "avg_current_ma": 0,
                "min_current_ma": 0,
                "min_current_mode": "-",
                "max_current_ma": 0,
                "max_current_mode": "-",
                "avg_power_mw": 0,
                "daily_energy_mah": 0,
                "daily_energy_wh": 0,
                "voltage": 3.3,
                "verdict": "Aucune donnée",
            },

            "energy_profile": {
                "states": [],
                "total_energy_mah": 0,
                "total_energy_mwh": 0,
                "cycle_duration_s": 0,
                "cycles_per_day": 0,
                "daily_energy_mah": 0,
                "daily_energy_mwh": 0,
                "daily_energy_wh": 0,
            },

            "consumption_curve": [],

            "battery_recommendation": {
                "capacity_mah": 0,
                "required_energy_wh": 0,
                "stored_energy_wh": 0,
                "voltage": 0,
                "autonomy_days": 0,
                "type": "-",
                "safety_factor": 0,
                "depth_of_discharge_percent": 0,
                "system_efficiency_percent": 0,
                "weight_g": 0,
                "volume_cm3": 0,
                "price_estimate": 0,
                "cycle_life": 0,
                "rechargeable": True,
                "pros": "",
                "cons": "",
                "valid": False,
                "warnings": [],
            },

            "battery_comparison": {
                "best_choice": None,
                "all_options": [],
                "preferred": None,
                "daily_wh": 0,
                "required_useful_energy_wh": 0,
                "autonomy_days": 3,
                "safety_factor": 1.25,
                "warnings": [],
            },

            "adapter_recommendation": {
                "voltage_v": 3.3,
                "current_a": 0,
                "peak_current_a": 0,
                "type": "-",
            },

            "solar_report": {
                "location": "-",
                "installation_type": "outdoor",
                "sun_hours": 0,
                "sun_hours_worst": 0,
                "worst_month_name": "",
                "monthly": [],
                "data_source": "-",
                "panel_w": 0,
                "panel_type": "-",
                "panel_efficiency": 0,
                "panel_surface_cm2": 0,
                "panel_price": 0,
                "panel_lifespan": 0,
                "charger_efficiency": 0,
                "orientation": "-",
                "inclination": 0,
            },

            "panel_comparison": {
                "best_choice": None,
                "all_options": [],
                "preferred": None,
                "installation_type": "outdoor",
                "warnings": [],
            },

            "daily_energy_mah": 0,
            "daily_energy_mwh": 0,
            "daily_energy_wh": 0,

            "warnings": self.warnings,
        }