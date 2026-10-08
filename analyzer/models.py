import uuid
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email obligatoire')

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        return self.create_user(email, password, **extra_fields)


class CustomUser(AbstractUser):
    email = models.EmailField(
        _("Adresse Email"),
        unique=True,
        max_length=255
    )
    username = models.CharField(
        max_length=150,
        unique=False,
        blank=True,
        null=True
    )

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    @property
    def display_name(self):
        if self.first_name:
            return self.first_name

        return self.email.split('@')[0] if self.email else '?'

    def __str__(self):
        return self.email


class Project(models.Model):
    INSTALLATION_TYPES = [
        ('outdoor', 'Extérieur (Outdoor)'),
        ('indoor', 'Intérieur (Indoor)'),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='projects',
        null=True,
        blank=True
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    location_city = models.CharField(max_length=100)
    location_country = models.CharField(max_length=100)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    installation_type = models.CharField(
        max_length=20,
        choices=INSTALLATION_TYPES,
        default='outdoor'
    )
    sun_hours_annual = models.FloatField(null=True, blank=True)
    sun_hours_worst = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=20, default='draft')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class Component(models.Model):
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
    voltage = models.FloatField(
        null=True,
        blank=True,
        default=3.3
    )
    datasheet = models.FileField(
        upload_to='datasheets/',
        blank=True
    )
    nominal_current_ma = models.FloatField(
        null=True,
        blank=True
    )
    cores_count = models.IntegerField(
        null=True,
        blank=True
    )
    freq_min_mhz = models.FloatField(
        null=True,
        blank=True
    )
    freq_max_mhz = models.FloatField(
        null=True,
        blank=True
    )
    freq_used_mhz = models.FloatField(
        null=True,
        blank=True
    )
    separate_power = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class ConsumptionMode(models.Model):
    component = models.ForeignKey(
        Component,
        on_delete=models.CASCADE,
        related_name='modes'
    )
    name = models.CharField(max_length=100)
    current_ma = models.FloatField()
    duration_ms = models.FloatField()
    count_per_cycle = models.IntegerField(default=1)
    freq_mhz = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.name}: {self.current_ma}mA"


class SolarPreference(models.Model):
    # Technologie souhaitée pour la recommandation (liste complète)
    PANEL_TYPES = [
        ('auto', 'Choix automatique'),
        ('monocrystalline', 'Monocristallin (~20%)'),
        ('polycrystalline', 'Polycristallin (~15%)'),
        ('amorphous', 'Amorphe (~8%)'),
        ('perc', 'PERC (~22%)'),
        ('bifacial', 'Bifacial (~21%)'),
    ]

    # Technologie du matériel choisi (sans « Choix automatique » :
    # le champ affiche « --------- » quand il est vide)
    CHOSEN_PANEL_TECHNOLOGIES = [
        (key, label) for key, label in PANEL_TYPES if key != 'auto'
    ]

    OBJECTIVES = [
        ('recommend', 'Recommander un panneau'),
        ('verify', 'Vérifier mon panneau'),
        ('none', 'Sans alimentation solaire'),
    ]

    # ⚠ Liste à adapter à ton projet : les captures montrent seulement
    # le menu fermé (« --------- »), pas ses options.
    PLACEMENTS = [
        ('outdoor_open', 'Extérieur, plein soleil'),
        ('outdoor_partial', 'Extérieur, partiellement ombragé'),
        ('indoor_window', 'Intérieur, derrière une vitre'),
        ('indoor_artificial', 'Intérieur, éclairage artificiel'),
    ]

    project = models.OneToOneField(
        Project,
        on_delete=models.CASCADE,
        related_name='solar_pref'
    )

    # --- Votre demande ---
    objective = models.CharField(
        max_length=20,
        choices=OBJECTIVES,
        default='recommend'
    )

    # --- Matériel choisi (mode « Vérifier ») ---
    chosen_model = models.CharField(
        max_length=200,
        blank=True,
        default=''
    )
    chosen_technology = models.CharField(
        max_length=30,
        choices=CHOSEN_PANEL_TECHNOLOGIES,
        blank=True,
        default=''
    )
    panel_power_w = models.FloatField(null=True, blank=True)
    panel_count = models.PositiveIntegerField(null=True, blank=True)
    vmp_v = models.FloatField(null=True, blank=True)
    voc_v = models.FloatField(null=True, blank=True)
    imp_ma = models.FloatField(null=True, blank=True)
    isc_ma = models.FloatField(null=True, blank=True)

    # --- Où sera placé le panneau ? ---
    placement = models.CharField(
        max_length=30,
        choices=PLACEMENTS,
        blank=True,
        default=''
    )
    shading_notes = models.TextField(blank=True, default='')
    lighting_notes = models.TextField(blank=True, default='')
    azimuth_deg = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(360)]
    )
    tilt_deg = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(90)]
    )

    # --- Contraintes facultatives ---
    panel_type = models.CharField(
        max_length=30,
        choices=PANEL_TYPES,
        default='auto'
    )
    max_surface_cm2 = models.FloatField(
        null=True,
        blank=True
    )
    max_budget = models.FloatField(
        null=True,
        blank=True
    )
    currency = models.CharField(
        max_length=10,
        blank=True,
        default=''
    )

    def __str__(self):
        return f"Solaire - {self.project.name}"


class BatteryPreference(models.Model):
    BATTERY_TYPES = [
        ('auto', 'Choix automatique'),
        ('lipo', 'LiPo 3.7V'),
        ('18650', 'Li-ion 18650 3.7V'),
        ('lifepo4', 'LiFePO4 3.2V'),
        ('nimh', 'NiMH 1.2V'),
        ('alkaline', 'Piles alcalines 1.5V'),
        ('lithium_coin', 'CR2032 3V'),
    ]

    CHOSEN_BATTERY_TECHNOLOGIES = [
        (key, label) for key, label in BATTERY_TYPES if key != 'auto'
    ]

    OBJECTIVES = [
        ('recommend', 'Recommander une batterie'),
        ('verify', 'Vérifier ma batterie'),
    ]

    VALUE_SCOPES = [
        ('pack', 'Batterie complète (pack)'),
        ('cell', 'Une cellule seule'),
    ]

    # Conservé pour compatibilité (anciennes vues / templates).
    # Le champ « Autonomie souhaitée » est maintenant un nombre de jours libre.
    AUTONOMY_CHOICES = [
        (1, '1 jour'),
        (3, '3 jours'),
        (7, '7 jours'),
        (14, '14 jours'),
        (30, '30 jours'),
    ]

    project = models.OneToOneField(
        Project,
        on_delete=models.CASCADE,
        related_name='battery_pref'
    )

    # --- Votre demande ---
    objective = models.CharField(
        max_length=20,
        choices=OBJECTIVES,
        default='recommend'
    )

    # --- Matériel choisi (mode « Vérifier ») ---
    chosen_model = models.CharField(
        max_length=200,
        blank=True,
        default=''
    )
    chosen_technology = models.CharField(
        max_length=30,
        choices=CHOSEN_BATTERY_TECHNOLOGIES,
        blank=True,
        default=''
    )
    value_scope = models.CharField(
        max_length=10,
        choices=VALUE_SCOPES,
        default='pack'
    )
    nominal_voltage_v = models.FloatField(null=True, blank=True)
    capacity_mah = models.FloatField(null=True, blank=True)
    cells_series = models.PositiveIntegerField(null=True, blank=True)
    cells_parallel = models.PositiveIntegerField(null=True, blank=True)

    # --- Autonomie souhaitée ---
    autonomy_days = models.PositiveIntegerField(
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(365)]
    )

    # --- Contraintes facultatives ---
    battery_type = models.CharField(
        max_length=30,
        choices=BATTERY_TYPES,
        default='auto'
    )
    max_weight_g = models.FloatField(
        null=True,
        blank=True
    )
    max_volume_cm3 = models.FloatField(
        null=True,
        blank=True
    )
    max_budget = models.FloatField(
        null=True,
        blank=True
    )
    currency = models.CharField(
        max_length=10,
        blank=True,
        default=''
    )
    rechargeable_only = models.BooleanField(
        default=True
    )

    battery_datasheet = models.FileField(
        upload_to='battery_datasheets/',
        blank=True,
        editable=False,
        verbose_name='Datasheet de la batterie'
    )

    def __str__(self):
        return f"Batterie - {self.project.name}"


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
    generated_flowchart = models.ImageField(
        upload_to='generated_flowcharts/',
        blank=True,
        null=True
    )
    estimated_curve = models.JSONField(
        null=True,
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
    summary = models.JSONField(null=True, blank=True)
    energy_profile = models.JSONField(null=True, blank=True)
    consumption_curve = models.JSONField(null=True, blank=True)
    battery_recommendation = models.JSONField(null=True, blank=True)
    battery_comparison = models.JSONField(null=True, blank=True)
    adapter_recommendation = models.JSONField(null=True, blank=True)
    solar_report = models.JSONField(null=True, blank=True)
    panel_comparison = models.JSONField(null=True, blank=True)
    daily_energy_mah = models.FloatField(null=True, blank=True)
    daily_energy_mwh = models.FloatField(null=True, blank=True)
    full_report = models.JSONField(null=True, blank=True)
    status = models.CharField(max_length=20, default='pending')
    analysis_source = models.CharField(
        max_length=20,
        default='local'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Résultat de {self.project.name}"


class PasswordResetCode(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='password_reset_codes'
    )
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveIntegerField(default=0)
    is_used = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    @staticmethod
    def generate_code():
        return f"{secrets.randbelow(1_000_000):06d}"

    @classmethod
    def create_for_user(cls, user):
        cls.objects.filter(
            user=user,
            is_used=False
        ).update(is_used=True)

        return cls.objects.create(
            user=user,
            code=cls.generate_code(),
            expires_at=timezone.now() + timedelta(minutes=10)
        )

    def is_valid(self):
        return (
            not self.is_used
            and self.attempts < 5
            and timezone.now() < self.expires_at
        )

    def __str__(self):
        return f"Code de réinitialisation pour {self.user.email}"