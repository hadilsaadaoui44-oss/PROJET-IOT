import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils.translation import gettext_lazy as _


# ========================
# MANAGER PERSONNALISÉ
# ========================
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


# ========================
# UTILISATEUR PERSONNALISÉ
# ========================
class CustomUser(AbstractUser):
    email = models.EmailField(_("Adresse Email"), unique=True, max_length=255)
    username = models.CharField(max_length=150, unique=False, blank=True, null=True)

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


# ========================
# MODÈLES EXISTANTS
# ========================
class Project(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    location_city = models.CharField(max_length=100)
    location_country = models.CharField(max_length=100)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
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

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='components')
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=CATEGORIES)
    voltage = models.FloatField(default=3.3)
    datasheet = models.FileField(upload_to='datasheets/', blank=True)

    def __str__(self):
        return self.name


class ConsumptionMode(models.Model):
    component = models.ForeignKey(Component, on_delete=models.CASCADE, related_name='modes')
    name = models.CharField(max_length=100)
    current_ma = models.FloatField()
    duration_ms = models.FloatField()
    count_per_cycle = models.IntegerField(default=1)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.name}: {self.current_ma}mA"


class Firmware(models.Model):
    INPUT_TYPES = [
        ('code', 'Code source'),
        ('flowchart', 'Organigramme'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='firmwares')
    input_type = models.CharField(max_length=20, choices=INPUT_TYPES, default='code')
    source_code = models.TextField(blank=True)
    code_file = models.FileField(upload_to='code_files/', blank=True)
    flowchart = models.ImageField(upload_to='flowcharts/', blank=True)

    def __str__(self):
        return f"Firmware de {self.project.name}"


class AnalysisResult(models.Model):
    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name='result')
    summary = models.JSONField(null=True, blank=True)
    energy_profile = models.JSONField(null=True, blank=True)
    consumption_curve = models.JSONField(null=True, blank=True)
    battery_recommendation = models.JSONField(null=True, blank=True)
    adapter_recommendation = models.JSONField(null=True, blank=True)
    solar_report = models.JSONField(null=True, blank=True)
    daily_energy_mah = models.FloatField(null=True, blank=True)
    daily_energy_mwh = models.FloatField(null=True, blank=True)
    full_report = models.JSONField(null=True, blank=True)
    status = models.CharField(max_length=20, default='pending')
    analysis_source = models.CharField(max_length=20, default='local')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Resultat de {self.project.name}"