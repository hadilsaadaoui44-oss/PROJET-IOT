from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm

from .models import (
    Project,
    Component,
    Firmware,
    CustomUser,
    SolarPreference,
    BatteryPreference,
)


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = [
            "name", "description", "location_city", "location_country",
            "latitude", "longitude", "installation_type",
        ]
        labels = {
            "name": "Nom du projet", "description": "Description",
            "location_city": "Ville", "location_country": "Pays",
            "latitude": "Latitude", "longitude": "Longitude",
            "installation_type": "Type d’installation",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex : Station météo"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Décrivez brièvement le projet IoT."}),
            "location_city": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex : Tunis"}),
            "location_country": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex : Tunisie"}),
            "latitude": forms.NumberInput(attrs={"class": "form-control", "step": "0.0001", "min": "-90", "max": "90"}),
            "longitude": forms.NumberInput(attrs={"class": "form-control", "step": "0.0001", "min": "-180", "max": "180"}),
            "installation_type": forms.Select(attrs={"class": "form-select"}),
        }

    def clean_latitude(self):
        latitude = self.cleaned_data.get("latitude")
        if latitude is not None and not -90 <= latitude <= 90:
            raise forms.ValidationError("La latitude doit être comprise entre -90 et 90.")
        return latitude

    def clean_longitude(self):
        longitude = self.cleaned_data.get("longitude")
        if longitude is not None and not -180 <= longitude <= 180:
            raise forms.ValidationError("La longitude doit être comprise entre -180 et 180.")
        return longitude


class McuForm(forms.ModelForm):
    class Meta:
        model = Component
        fields = ["name", "voltage", "datasheet", "nominal_current_ma", "cores_count", "freq_min_mhz", "freq_max_mhz", "freq_used_mhz"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex : ESP32"}),
            "voltage": forms.NumberInput(attrs={"class": "form-control", "step": "0.1", "min": "0.1", "placeholder": "3.3"}),
            "datasheet": forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".pdf"}),
            "nominal_current_ma": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0", "placeholder": "80"}),
            "cores_count": forms.NumberInput(attrs={"class": "form-control", "min": "1", "placeholder": "2"}),
            "freq_min_mhz": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0", "placeholder": "80"}),
            "freq_max_mhz": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0", "placeholder": "240"}),
            "freq_used_mhz": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0", "placeholder": "160"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in self.fields:
            if field_name != "name":
                self.fields[field_name].required = False

    def clean(self):
        cleaned_data = super().clean()
        voltage = cleaned_data.get("voltage")
        nominal_current = cleaned_data.get("nominal_current_ma")
        cores_count = cleaned_data.get("cores_count")
        freq_min = cleaned_data.get("freq_min_mhz")
        freq_max = cleaned_data.get("freq_max_mhz")
        freq_used = cleaned_data.get("freq_used_mhz")
        if voltage is not None and voltage <= 0:
            self.add_error("voltage", "La tension doit être supérieure à zéro.")
        if nominal_current is not None and nominal_current < 0:
            self.add_error("nominal_current_ma", "Le courant nominal ne peut pas être négatif.")
        if cores_count is not None and cores_count <= 0:
            self.add_error("cores_count", "Le nombre de cœurs doit être supérieur à zéro.")
        if freq_min is not None and freq_max is not None and freq_min > freq_max:
            self.add_error("freq_max_mhz", "La fréquence maximale doit être supérieure ou égale à la fréquence minimale.")
        if freq_used is not None:
            if freq_min is not None and freq_used < freq_min:
                self.add_error("freq_used_mhz", "La fréquence utilisée est inférieure à la fréquence minimale.")
            if freq_max is not None and freq_used > freq_max:
                self.add_error("freq_used_mhz", "La fréquence utilisée dépasse la fréquence maximale.")
        return cleaned_data


class SensorForm(forms.ModelForm):
    class Meta:
        model = Component
        fields = ["name", "voltage", "nominal_current_ma", "datasheet"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex : DHT22"}),
            "voltage": forms.NumberInput(attrs={"class": "form-control", "step": "0.1", "min": "0.1", "placeholder": "3.3"}),
            "nominal_current_ma": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0", "placeholder": "Ex : 2.5"}),
            "datasheet": forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".pdf"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["voltage"].required = False
        self.fields["nominal_current_ma"].required = False
        self.fields["datasheet"].required = False


class ActuatorForm(forms.ModelForm):
    class Meta:
        model = Component
        fields = ["name", "voltage", "nominal_current_ma", "datasheet", "separate_power"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex : Relais"}),
            "voltage": forms.NumberInput(attrs={"class": "form-control", "step": "0.1", "min": "0.1", "placeholder": "5"}),
            "nominal_current_ma": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0", "placeholder": "Ex : 70"}),
            "datasheet": forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".pdf"}),
            "separate_power": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["voltage"].required = False
        self.fields["nominal_current_ma"].required = False
        self.fields["datasheet"].required = False
        self.fields["separate_power"].required = False


def _number(step="any", min_value="0", placeholder=""):
    attrs = {"class": "form-control", "step": step, "min": min_value}
    if placeholder:
        attrs["placeholder"] = placeholder
    return forms.NumberInput(attrs=attrs)


def _positive_or_error(form, cleaned_data, field_name, message):
    value = cleaned_data.get(field_name)
    if value is not None and value <= 0:
        form.add_error(field_name, message)


class SolarPreferenceForm(forms.ModelForm):
    class Meta:
        model = SolarPreference
        fields = [
            "objective",
            "chosen_model", "chosen_technology",
            "panel_power_w", "panel_count",
            "vmp_v", "voc_v", "imp_ma", "isc_ma",
            "placement", "shading_notes", "lighting_notes",
            "azimuth_deg", "tilt_deg",
            "panel_type", "max_surface_cm2", "max_budget", "currency",
        ]
        labels = {
            "objective": "Objectif de l’analyse",
            "chosen_model": "Modèle du matériel choisi",
            "chosen_technology": "Technologie du matériel choisi",
            "panel_power_w": "Puissance nominale par panneau (W)",
            "panel_count": "Nombre de panneaux",
            "vmp_v": "Tension Vmp par panneau (V)",
            "voc_v": "Tension Voc par panneau (V)",
            "imp_ma": "Courant Imp par panneau (mA)",
            "isc_ma": "Courant Isc par panneau (mA)",
            "placement": "Emplacement du panneau",
            "shading_notes": "Ombrage : arbres, bâtiments, horaires...",
            "lighting_notes": "Éclairage disponible (intérieur, vitre, horaires...)",
            "azimuth_deg": "Azimut (° ; nord 0, est 90, sud 180, ouest 270)",
            "tilt_deg": "Inclinaison (° ; horizontal 0)",
            "panel_type": "Technologie souhaitée pour la recommandation",
            "max_surface_cm2": "Surface solaire totale maximale (cm²)",
            "max_budget": "Budget maximal pour cette partie",
            "currency": "Devise (TND, EUR, USD...)",
        }
        widgets = {
            "objective": forms.Select(attrs={"class": "form-select"}),
            "chosen_model": forms.TextInput(attrs={"class": "form-control"}),
            "chosen_technology": forms.Select(attrs={"class": "form-select"}),
            "panel_power_w": _number(step="0.01"),
            "panel_count": _number(step="1", min_value="1"),
            "vmp_v": _number(step="0.01"),
            "voc_v": _number(step="0.01"),
            "imp_ma": _number(step="0.1"),
            "isc_ma": _number(step="0.1"),
            "placement": forms.Select(attrs={"class": "form-select"}),
            "shading_notes": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "lighting_notes": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "azimuth_deg": _number(step="1", min_value="0"),
            "tilt_deg": _number(step="1", min_value="0"),
            "panel_type": forms.Select(attrs={"class": "form-select"}),
            "max_surface_cm2": _number(step="1"),
            "max_budget": _number(step="0.01"),
            "currency": forms.TextInput(attrs={"class": "form-control", "maxlength": "10"}),
        }

    OPTIONAL_FIELDS = [
        "chosen_model", "chosen_technology",
        "panel_power_w", "panel_count",
        "vmp_v", "voc_v", "imp_ma", "isc_ma",
        "placement", "shading_notes", "lighting_notes",
        "azimuth_deg", "tilt_deg",
        "max_surface_cm2", "max_budget", "currency",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in self.OPTIONAL_FIELDS:
            self.fields[name].required = False

    def clean(self):
        cleaned_data = super().clean()
        objective = cleaned_data.get("objective")

        if objective == "none":
            return cleaned_data

        if not cleaned_data.get("placement"):
            self.add_error(
                "placement",
                "Précisez où le panneau sera installé, indépendamment du dispositif.",
            )

        if objective == "verify":
            if cleaned_data.get("panel_power_w") in (None, ""):
                self.add_error("panel_power_w", "Indiquez la puissance nominale par panneau.")
            if cleaned_data.get("panel_count") in (None, ""):
                self.add_error("panel_count", "Indiquez le nombre de panneaux.")

        for name in ("panel_power_w", "vmp_v", "voc_v", "imp_ma", "isc_ma"):
            _positive_or_error(self, cleaned_data, name, "La valeur doit être supérieure à zéro.")
        _positive_or_error(self, cleaned_data, "panel_count", "Le nombre de panneaux doit être au moins 1.")

        vmp = cleaned_data.get("vmp_v")
        voc = cleaned_data.get("voc_v")
        if vmp is not None and voc is not None and voc < vmp:
            self.add_error("voc_v", "Voc doit être supérieure ou égale à Vmp.")

        imp = cleaned_data.get("imp_ma")
        isc = cleaned_data.get("isc_ma")
        if imp is not None and isc is not None and isc < imp:
            self.add_error("isc_ma", "Isc doit être supérieur ou égal à Imp.")

        return cleaned_data


class BatteryPreferenceForm(forms.ModelForm):
    class Meta:
        model = BatteryPreference
        fields = [
            "objective",
            "chosen_model", "chosen_technology", "value_scope",
            "nominal_voltage_v", "capacity_mah",
            "cells_series", "cells_parallel",
            "autonomy_days",
            "battery_type", "max_weight_g", "max_volume_cm3",
            "max_budget", "currency", "rechargeable_only",
        ]
        labels = {
            "objective": "Objectif de l’analyse",
            "chosen_model": "Modèle du matériel choisi",
            "chosen_technology": "Technologie du matériel choisi",
            "value_scope": "Les valeurs concernent",
            "nominal_voltage_v": "Tension nominale (V)",
            "capacity_mah": "Capacité (mAh)",
            "cells_series": "Cellules en série",
            "cells_parallel": "Cellules en parallèle",
            "autonomy_days": "Autonomie souhaitée (jours)",
            "battery_type": "Technologie souhaitée pour la recommandation",
            "max_weight_g": "Poids batterie maximal (g)",
            "max_volume_cm3": "Volume batterie maximal (cm³)",
            "max_budget": "Budget maximal pour cette partie",
            "currency": "Devise (TND, EUR, USD...)",
            "rechargeable_only": "Batterie rechargeable uniquement",
        }
        widgets = {
            "objective": forms.Select(attrs={"class": "form-select"}),
            "chosen_model": forms.TextInput(attrs={"class": "form-control"}),
            "chosen_technology": forms.Select(attrs={"class": "form-select"}),
            "value_scope": forms.Select(attrs={"class": "form-select"}),
            "nominal_voltage_v": _number(step="0.01"),
            "capacity_mah": _number(step="1"),
            "cells_series": _number(step="1", min_value="1"),
            "cells_parallel": _number(step="1", min_value="1"),
            "autonomy_days": _number(step="1", min_value="1"),
            "battery_type": forms.Select(attrs={"class": "form-select"}),
            "max_weight_g": _number(step="1"),
            "max_volume_cm3": _number(step="0.1"),
            "max_budget": _number(step="0.01"),
            "currency": forms.TextInput(attrs={"class": "form-control", "maxlength": "10"}),
            "rechargeable_only": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    OPTIONAL_FIELDS = [
        "chosen_model", "chosen_technology",
        "nominal_voltage_v", "capacity_mah",
        "cells_series", "cells_parallel",
        "max_weight_g", "max_volume_cm3", "max_budget",
        "currency", "rechargeable_only",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in self.OPTIONAL_FIELDS:
            self.fields[name].required = False

    def clean(self):
        cleaned_data = super().clean()

        if cleaned_data.get("objective") == "verify":
            if cleaned_data.get("nominal_voltage_v") in (None, ""):
                self.add_error("nominal_voltage_v", "Indiquez la tension nominale.")
            if cleaned_data.get("capacity_mah") in (None, ""):
                self.add_error("capacity_mah", "Indiquez la capacité.")

        _positive_or_error(self, cleaned_data, "nominal_voltage_v", "La tension doit être supérieure à zéro.")
        _positive_or_error(self, cleaned_data, "capacity_mah", "La capacité doit être supérieure à zéro.")
        _positive_or_error(self, cleaned_data, "cells_series", "Le nombre de cellules doit être au moins 1.")
        _positive_or_error(self, cleaned_data, "cells_parallel", "Le nombre de cellules doit être au moins 1.")

        return cleaned_data


class FirmwareForm(forms.ModelForm):
    class Meta:
        model = Firmware
        fields = ["input_type", "source_code", "code_file", "flowchart"]
        labels = {
            "input_type": "Type d’entrée",
            "source_code": "Code source",
            "code_file": "Fichier du programme",
            "flowchart": "Organigramme",
        }
        widgets = {
            "input_type": forms.Select(attrs={"class": "form-select", "id": "inputType"}),
            "source_code": forms.Textarea(attrs={"class": "form-control", "rows": 15, "placeholder": "// Collez ici votre code Arduino, C, C++ ou Python"}),
            "code_file": forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".ino,.cpp,.c,.h,.hpp,.py"}),
            "flowchart": forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".png,.jpg,.jpeg"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["source_code"].required = False
        self.fields["code_file"].required = False
        self.fields["flowchart"].required = False

    def clean(self):
        cleaned_data = super().clean()
        input_type = cleaned_data.get("input_type")
        source_code = (cleaned_data.get("source_code") or "").strip()
        code_file = cleaned_data.get("code_file")
        flowchart = cleaned_data.get("flowchart")
        existing_code_file = bool(self.instance and self.instance.pk and self.instance.code_file)
        existing_flowchart = bool(self.instance and self.instance.pk and self.instance.flowchart)
        if input_type == "code":
            if not source_code and not code_file and not existing_code_file:
                raise forms.ValidationError("Collez le code source ou importez un fichier de code.")
        elif input_type == "flowchart":
            if not flowchart and not existing_flowchart:
                raise forms.ValidationError("Importez une image de l’organigramme.")
        return cleaned_data


class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = CustomUser
        fields = ["email", "first_name", "last_name"]
        widgets = {
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "exemple@email.com"}),
            "first_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Prénom"}),
            "last_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Nom"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].widget.attrs.update({"class": "form-control"})
        self.fields["password2"].widget.attrs.update({"class": "form-control"})
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True


class CustomLoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget = forms.EmailInput(attrs={
            "class": "form-control",
            "placeholder": "exemple@email.com",
            "autofocus": True,
        })
        self.fields["username"].label = "Adresse Email"
        self.fields["password"].widget.attrs.update({"class": "form-control"})