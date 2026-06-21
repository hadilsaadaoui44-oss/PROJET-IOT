import uuid
from django.db import models


class Project(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    name = models.CharField(
        max_length=200
    )
    description = models.TextField(
        blank=True
    )
    location_city = models.CharField(
        max_length=100
    )
    location_country = models.CharField(
        max_length=100
    )
    latitude = models.FloatField(
        null=True, blank=True
    )
    longitude = models.FloatField(
        null=True, blank=True
    )
    status = models.CharField(
        max_length=20,
        default='draft'
    )
    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class Component(models.Model):
    """Un composant du circuit"""

    CATEGORIES = [
        ('mcu', 'Microcontroleur'),
        ('sensor', 'Capteur'),
        ('communication', 'Communication'),
        ('actuator', 'Actionneur'),
        ('display', 'Ecran/LED'),
        ('power', 'Alimentation'),
        ('other', 'Autre'),
    ]

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='components'
    )
    name = models.CharField(max_length=200)
    category = models.CharField(
        max_length=20,
        choices=CATEGORIES
    )
    voltage = models.FloatField(default=3.3)
    datasheet = models.FileField(
        upload_to='datasheets/',
        blank=True
    )

    def __str__(self):
        return self.name


class ConsumptionMode(models.Model):
    """
    Mode de consommation DYNAMIQUE.
    Pas de liste fixe !
    Chaque carte a ses propres modes.
    L'utilisateur les saisit depuis la datasheet.
    """

    component = models.ForeignKey(
        Component,
        on_delete=models.CASCADE,
        related_name='modes'
    )
    name = models.CharField(
        max_length=100,
        help_text="Ex: Deep Sleep, WiFi TX, LoRa TX..."
    )
    current_ma = models.FloatField(
        help_text="Courant en mA (depuis datasheet)"
    )
    duration_ms = models.FloatField(
        help_text="Duree en ms (depuis le code)"
    )
    count_per_cycle = models.IntegerField(
        default=1,
        help_text="Nombre de fois par cycle"
    )

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.name}: {self.current_ma}mA"


class Firmware(models.Model):
    INPUT_TYPES = [
        ('code', 'Code source'),
        ('flowchart', 'Organigramme'),
    ]

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='firmwares'
    )
    input_type = models.CharField(
        max_length=20,
        choices=INPUT_TYPES,
        default='code'
    )
    source_code = models.TextField(blank=True)
    code_file = models.FileField(
        upload_to='code_files/',
        blank=True
    )
    flowchart = models.ImageField(
        upload_to='flowcharts/',
        blank=True
    )

    def __str__(self):
        return f"Firmware de {self.project.name}"


class AnalysisResult(models.Model):
    project = models.OneToOneField(
        Project,
        on_delete=models.CASCADE,
        related_name='result'
    )
    summary = models.JSONField(
        null=True, blank=True
    )
    energy_profile = models.JSONField(
        null=True, blank=True
    )
    consumption_curve = models.JSONField(
        null=True, blank=True
    )
    battery_recommendation = models.JSONField(
        null=True, blank=True
    )
    adapter_recommendation = models.JSONField(
        null=True, blank=True
    )
    solar_report = models.JSONField(
        null=True, blank=True
    )
    daily_energy_mah = models.FloatField(
        null=True, blank=True
    )
    daily_energy_mwh = models.FloatField(
        null=True, blank=True
    )
    full_report = models.JSONField(
        null=True, blank=True
    )
    status = models.CharField(
        max_length=20,
        default='pending'
    )
    analysis_source = models.CharField(
        max_length=20,
        default='local'
    )
    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"Resultat de {self.project.name}"