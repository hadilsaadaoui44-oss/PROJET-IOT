from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _
from .models import (
    CustomUser, Project, Component,
    ConsumptionMode, Firmware, AnalysisResult,
    SolarPreference, BatteryPreference
)


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ['email', 'first_name', 'last_name', 'is_staff', 'is_active']
    list_filter = ['is_staff', 'is_active']
    search_fields = ['email', 'first_name', 'last_name']
    ordering = ['email']
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Informations personnelles'), {'fields': ('first_name', 'last_name')}),
        (_('Permissions'), {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        (_('Dates importantes'), {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'first_name', 'last_name', 'password1', 'password2', 'is_staff', 'is_active'),
        }),
    )


class ComponentInline(admin.TabularInline):
    model = Component
    extra = 0


class FirmwareInline(admin.StackedInline):
    model = Firmware
    extra = 0


class SolarPreferenceInline(admin.StackedInline):
    model = SolarPreference
    extra = 0


class BatteryPreferenceInline(admin.StackedInline):
    model = BatteryPreference
    extra = 0


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'location_city', 'location_country', 'installation_type', 'status', 'created_at']
    list_filter = ['status', 'location_country', 'installation_type']
    search_fields = ['name', 'location_city']
    inlines = [ComponentInline, FirmwareInline, SolarPreferenceInline, BatteryPreferenceInline]


class ConsumptionModeInline(admin.TabularInline):
    model = ConsumptionMode
    extra = 0


@admin.register(Component)
class ComponentAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'voltage', 'project']
    list_filter = ['category']
    search_fields = ['name']
    inlines = [ConsumptionModeInline]


@admin.register(SolarPreference)
class SolarPreferenceAdmin(admin.ModelAdmin):
    list_display = ['project', 'panel_type', 'max_surface_cm2', 'max_budget']
    list_filter = ['panel_type']


@admin.register(BatteryPreference)
class BatteryPreferenceAdmin(admin.ModelAdmin):
    list_display = ['project', 'battery_type', 'autonomy_days', 'rechargeable_only']
    list_filter = ['battery_type', 'rechargeable_only']


@admin.register(AnalysisResult)
class AnalysisResultAdmin(admin.ModelAdmin):
    list_display = ['project', 'status', 'analysis_source', 'daily_energy_mah', 'created_at']
    list_filter = ['status', 'analysis_source']
    readonly_fields = ['created_at']