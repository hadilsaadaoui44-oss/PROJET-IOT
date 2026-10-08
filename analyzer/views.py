import datetime
import decimal
import json
import logging
import re
import uuid

import requests
from django.conf import settings
from django.core.mail import send_mail
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from django.utils.crypto import constant_time_compare

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.db import transaction

from .models import (
    Project,
    ConsumptionMode,
    AnalysisResult,
    Component,
    CustomUser,
    PasswordResetCode,
)
from .forms import (
    ProjectForm,
    FirmwareForm,
    CustomUserCreationForm,
    SolarPreferenceForm,
    BatteryPreferenceForm,
)
from .calculator import EnergyCalculator
from .services.panel_selector import installation_type_from_placement
from .services.datasheet_extractor import (
    extract_battery_values_from_datasheet,
    extract_component_values_from_datasheet,
    extract_mode_values_from_datasheet,
)

logger = logging.getLogger(__name__)


# ============================================================
# TRADUCTIONS DU RAPPORT
# ============================================================

REPORT_TRANSLATIONS = {
    'Very Good': 'Très bon',
    'Good': 'Bon',
    'Fair': 'Moyen',
    'Poor': 'Faible',
    'Requires redesign': 'Conception à revoir',
    'Feasible with improvements': 'Faisable avec améliorations',
    'Feasible': 'Faisable',
    'Not yet validated': 'Non encore validé',
    'Validated with engineering recommendations': (
        'Validé avec recommandations techniques'
    ),
    'Conditionally validated': 'Validé sous conditions',
    'Requires a compatible LiFePO4 charger': (
        'Nécessite un chargeur compatible LiFePO4.'
    ),
    'Charging below 0°C should be avoided without protection': (
        'Éviter la recharge sous 0 °C sans protection adaptée.'
    ),
    'Intermittent consumption with marked peaks': (
        'Consommation intermittente avec pics marqués'
    ),
    'Low baseline with short high-current peaks': (
        'Faible consommation de fond avec de courts pics de courant'
    ),
    'Monocrystalline': 'Monocristallin',
    'Polycrystalline': 'Polycristallin',
    'Amorphous': 'Amorphe',
    'Alkaline': 'Alcaline',
    'Lithium Coin': 'Pile bouton lithium',
    'Requires a compatible charger': 'Nécessite un chargeur compatible.',
    'Not rechargeable': 'Non rechargeable',
    'Sensitive to overcharging and puncture': (
        'Sensible à la surcharge et à la perforation'
    ),
}


def _translate_report_value(value):
    """Traduit récursivement les valeurs textuelles connues du rapport."""

    if isinstance(value, dict):
        return {key: _translate_report_value(item) for key, item in value.items()}

    if isinstance(value, list):
        return [_translate_report_value(item) for item in value]

    if not isinstance(value, str):
        return value

    translated = value

    for source, target in REPORT_TRANSLATIONS.items():
        translated = translated.replace(source, target)

    return translated


def _frenchify_decimals(text):
    """Utilise la virgule pour les nombres décimaux présents dans un texte."""

    if not isinstance(text, str):
        return text

    return re.sub(r'(?<=\d)\.(?=\d)', ',', text)


def _json_default(obj):
    """Sérialisation JSON sûre (Decimal, dates, UUID, fichiers...)."""

    if isinstance(obj, decimal.Decimal):
        return float(obj)

    if isinstance(obj, (datetime.datetime, datetime.date, datetime.time)):
        return obj.isoformat()

    if isinstance(obj, uuid.UUID):
        return str(obj)

    if isinstance(obj, (set, frozenset, tuple)):
        return list(obj)

    if hasattr(obj, 'name') and hasattr(obj, 'storage'):
        return obj.name

    return str(obj)


# ============================================================
# HOME
# ============================================================

def home(request):
    if request.user.is_authenticated:
        projects = (
            Project.objects
            .filter(user=request.user)
            .order_by('-id')[:10]
        )
    else:
        projects = Project.objects.none()

    return render(
        request,
        'analyzer/home.html',
        {'projects': projects},
    )


# ============================================================
# HELPERS NUMÉRIQUES / GÉNÉRIQUES
# ============================================================

def _to_float(value):
    try:
        if value is None:
            return None

        value = str(value).strip()

        if value == '':
            return None

        return float(value.replace(',', '.'))

    except (ValueError, TypeError):
        return None


def _to_int(value):
    try:
        if value is None:
            return None

        value = str(value).strip()

        if value == '':
            return None

        return int(value)

    except (ValueError, TypeError):
        return None


def _get_indices(post_data, prefix):
    pattern = re.compile(rf'^{re.escape(prefix)}(\d+)$')

    indices = []

    for key in post_data.keys():
        match = pattern.match(key)

        if match:
            indices.append(int(match.group(1)))

    return sorted(set(indices))


def _first_dict(*values):
    """Retourne le premier dictionnaire non vide."""

    for value in values:
        if isinstance(value, dict) and value:
            return value

    return {}


def _first_list(*values):
    """Retourne la première liste non vide."""

    for value in values:
        if isinstance(value, list) and value:
            return value

    return []


def _as_dict(value):
    """Retourne value si c'est un dict, sinon un dict vide."""

    return value if isinstance(value, dict) else {}


def _compute_cycles_per_day(energy):
    """
    Nombre de cycles par jour pour l'affichage du rapport.

    Priorité :
    1. valeur fournie par le moteur (cycles_per_day / occurrences_per_day) ;
    2. 86 400 000 ms / durée du cycle ;
    3. énergie journalière / énergie par cycle.
    """

    energy = _as_dict(energy)

    for key in ('cycles_per_day', 'occurrences_per_day'):
        value = _to_float(energy.get(key))

        if value is not None and value > 0:
            return int(round(value))

    cycle_ms = _to_float(energy.get('cycle_duration_ms'))

    if cycle_ms is not None and cycle_ms > 0:
        return max(1, int(86_400_000 // cycle_ms))

    daily = _to_float(energy.get('energy_daily_mwh'))
    per_cycle = _to_float(energy.get('energy_cycle_mwh'))

    if daily is not None and per_cycle is not None and per_cycle > 0:
        return max(1, int(round(daily / per_cycle)))

    return None


# ============================================================
# NORMALISATION RÉPONSE N8N
# ============================================================

def _unwrap_n8n_result(value):
    """Extrait le rapport métier de l'enveloppe renvoyée par n8n."""

    report_keys = {
        'summary',
        'energy',
        'battery',
        'solar',
        'power',
        'engineering_analysis',
        'energy_profile',
        'daily_energy_mah',
        'daily_energy_mwh',
        'battery_recommendation',
        'solar_report',
    }

    current = value
    seen_ids = set()

    for _level in range(6):

        if isinstance(current, str):
            try:
                current = json.loads(current)
            except (TypeError, ValueError):
                return None

            continue

        if isinstance(current, list):
            if not current:
                return None

            current = current[0]
            continue

        if not isinstance(current, dict):
            return None

        if id(current) in seen_ids:
            return None

        seen_ids.add(id(current))

        if any(key in current for key in report_keys):
            return current

        nested = None

        for envelope_key in (
            'result',
            'results',
            'json',
            'data',
            'body',
            'output',
        ):
            candidate = current.get(envelope_key)

            if isinstance(candidate, (dict, list, str)) and candidate:
                nested = candidate
                break

        if nested is None:
            return current

        current = nested

    return current if isinstance(current, dict) else None


# ============================================================
# CRÉATION DE PROJET
# ============================================================

@login_required
def project_create(request):

    if request.method == 'POST':

        draft = None

        draft_id = request.POST.get('draft_id')

        if draft_id:
            draft = get_object_or_404(
                Project,
                id=draft_id,
                user=request.user,
            )

        existing_firmware = draft.firmwares.first() if draft else None

        existing_solar = (
            getattr(draft, 'solar_pref', None) if draft else None
        )

        existing_battery = (
            getattr(draft, 'battery_pref', None) if draft else None
        )

        form = ProjectForm(request.POST, instance=draft)

        firm_form = FirmwareForm(
            request.POST,
            request.FILES,
            instance=existing_firmware,
        )

        solar_form = SolarPreferenceForm(
            request.POST,
            instance=existing_solar,
        )

        battery_form = BatteryPreferenceForm(
            request.POST,
            instance=existing_battery,
        )

        use_saved = request.POST.get('use_saved_components') == '1'

        if use_saved:
            forms_are_valid = bool(
                draft
                and existing_firmware
                and existing_solar
                and existing_battery
            )

        else:
            forms_are_valid = (
                form.is_valid()
                and firm_form.is_valid()
                and solar_form.is_valid()
                and battery_form.is_valid()
            )

        if forms_are_valid:

            if use_saved:
                project = draft

            else:
                project = form.save(commit=False)
                project.user = request.user
                project.save()

            warnings = []

            if not use_saved:

                for category in ('mcu', 'sensor', 'actuator'):
                    _save_components(
                        request.POST,
                        request.FILES,
                        project,
                        category,
                        warnings,
                    )

            if use_saved:
                firmware = existing_firmware

            else:
                firmware = firm_form.save(commit=False)
                firmware.project = project
                firmware.save()

            if not use_saved:

                solar_pref = solar_form.save(commit=False)
                solar_pref.project = project
                solar_pref.save()

                battery_pref = battery_form.save(commit=False)
                battery_pref.project = project
                battery_pref.save()

            total_modes = sum(
                component.modes.count()
                for component in project.components.all()
            )

            has_code = (
                bool((firmware.source_code or '').strip())
                or bool(firmware.code_file)
            )

            if total_modes == 0 and not has_code:

                project.status = 'failed'
                project.save(update_fields=['status'])

                messages.error(
                    request,
                    '❌ Fournissez un code source ou saisissez au moins '
                    'un mode de fonctionnement.'
                )

                if draft:
                    return redirect('wizard_review', project_id=project.id)

                return redirect('project_create')

            # ======================================================
            # 1. N8N PRINCIPAL
            # ======================================================

            n8n_result = _unwrap_n8n_result(_send_to_n8n(project))

            if _is_valid_n8n_result(n8n_result):
                results = n8n_result
                source = 'n8n'

            # ======================================================
            # 2. FALLBACK LOCAL
            # ======================================================

            elif total_modes > 0:

                try:

                    calculator = EnergyCalculator(project)

                    local_results = calculator.analyze()

                    if not isinstance(local_results, dict):
                        raise ValueError(
                            'Le calculateur local a retourné un format invalide.'
                        )

                    daily_wh = _extract_daily_wh(local_results)

                    if daily_wh <= 0:
                        raise ValueError(
                            'La consommation quotidienne calculée est '
                            'nulle ou invalide.'
                        )

                    results = local_results
                    source = 'local'

                    messages.warning(
                        request,
                        '⚠️ n8n est indisponible ou a retourné une erreur. '
                        'Le calculateur local de secours a été utilisé.'
                    )

                except Exception:

                    project.status = 'failed'
                    project.save(update_fields=['status'])

                    logger.exception(
                        'Erreur du calculateur local de secours.'
                    )

                    messages.error(
                        request,
                        '❌ n8n est indisponible et le calculateur local '
                        'n’a pas pu terminer l’analyse. Vérifiez les '
                        'courants, les durées et le nombre d’exécutions '
                        'des modes.'
                    )

                    if draft:
                        return redirect('wizard_review', project_id=draft.id)

                    return redirect('project_create')

            # ======================================================
            # 3. CODE SEUL + N8N INDISPONIBLE
            # ======================================================

            else:

                project.status = 'pending'
                project.save(update_fields=['status'])

                messages.error(
                    request,
                    '❌ n8n est indisponible. Le projet a été conservé, '
                    'mais le calculateur local ne peut pas analyser '
                    'automatiquement le code source. Réessayez plus tard '
                    'ou ajoutez des modes manuellement.'
                )

                return redirect('project_list')

            # ======================================================
            # 4. SAUVEGARDE DU RÉSULTAT
            # ======================================================

            engineering = _as_dict(results.get('engineering_analysis'))

            summary = _first_dict(
                engineering.get('executive_summary'),
                results.get('summary'),
            )

            energy_data = _first_dict(
                engineering.get('energy'),
                results.get('energy'),
                results.get('energy_profile'),
            )

            battery_data = _first_dict(
                engineering.get('battery'),
                results.get('battery'),
                results.get('battery_recommendation'),
            )

            solar_data = _first_dict(
                engineering.get('solar'),
                results.get('solar'),
                results.get('solar_report'),
            )

            power_data = _first_dict(
                engineering.get('power'),
                results.get('power'),
                results.get('adapter_recommendation'),
            )

            result, _created = AnalysisResult.objects.get_or_create(
                project=project
            )

            result.summary = summary
            result.energy_profile = energy_data

            result.consumption_curve = _first_list(
                results.get('consumption_curve'),
                engineering.get('consumption_curve'),
            )

            result.battery_recommendation = battery_data

            result.battery_comparison = _first_list(
                results.get('battery_comparison'),
                battery_data.get('commercial_models'),
            )

            result.adapter_recommendation = power_data
            result.solar_report = solar_data

            result.panel_comparison = _first_list(
                results.get('panel_comparison'),
                solar_data.get('commercial_panels'),
            )

            daily_mah = (
                summary.get('daily_energy_mah')
                or results.get('daily_energy_mah')
                or energy_data.get('daily_energy_mah')
            )

            if daily_mah is None:

                average_current = _to_float(
                    energy_data.get('average_current_ma')
                    or energy_data.get('current_average_ma')
                )

                if average_current is not None:
                    daily_mah = average_current * 24

            daily_mwh = (
                results.get('daily_energy_mwh')
                or energy_data.get('daily_energy_mwh')
                or energy_data.get('energy_daily_mwh')
                or summary.get('daily_energy_mwh')
            )

            if daily_mwh is None:

                daily_wh = _to_float(
                    energy_data.get('daily_energy_wh')
                    or summary.get('daily_energy_wh')
                    or results.get('daily_energy_wh')
                )

                if daily_wh is not None:
                    daily_mwh = daily_wh * 1000

            result.daily_energy_mah = _to_float(daily_mah) or 0
            result.daily_energy_mwh = _to_float(daily_mwh) or 0

            result.full_report = results
            result.status = 'completed'
            result.analysis_source = source

            result.save()

            project.status = 'completed'
            project.save(update_fields=['status'])

            for warning in warnings:
                messages.warning(request, warning)

            result_warnings = results.get('warnings', [])

            if isinstance(result_warnings, list):
                for warning in result_warnings:
                    messages.warning(request, str(warning))

            if source == 'n8n':
                messages.success(request, '✅ Analyse n8n + IA terminée !')
            else:
                messages.info(
                    request,
                    'ℹ️ n8n était indisponible : calcul local de secours '
                    'utilisé.'
                )

            return redirect('report', project_id=project.id)

        if use_saved and draft:

            messages.error(
                request,
                'Le brouillon est incomplet. Vérifiez les étapes Programme, '
                'Batterie et Solaire avant de relancer l’analyse.'
            )

            return redirect('wizard_review', project_id=draft.id)

    else:

        form = ProjectForm()
        firm_form = FirmwareForm()
        solar_form = SolarPreferenceForm()
        battery_form = BatteryPreferenceForm()

    return render(
        request,
        'analyzer/project_form.html',
        {
            'form': form,
            'firm_form': firm_form,
            'solar_form': solar_form,
            'battery_form': battery_form,
        },
    )


# ============================================================
# WIZARD
# ============================================================

WIZARD_STEPS = (
    ('project', 'Projet et position'),
    ('mcu', 'Microcontrôleur'),
    ('peripherals', 'Capteurs et communications'),
    ('actuators', 'Actionneurs et charges'),
    ('firmware', 'Programme embarqué'),
    ('energy', 'Batterie et solaire'),
    ('review', 'Vérification'),
)


def _wizard_context(step, project=None, **extra):
    current = next(
        index
        for index, item in enumerate(WIZARD_STEPS, start=1)
        if item[0] == step
    )

    context = {
        'wizard_steps': WIZARD_STEPS,
        'wizard_step': step,
        'wizard_current': current,
        'wizard_total': len(WIZARD_STEPS),
        'wizard_percent': round(current / len(WIZARD_STEPS) * 100),
        'project': project,
    }

    context.update(extra)

    return context


def _wizard_project(request, project_id):
    return get_object_or_404(
        Project,
        id=project_id,
        user=request.user,
    )


def workflow_intro(request):
    return render(request, 'analyzer/workflow_intro.html')


@login_required
def wizard_project(request, project_id=None):
    project = _wizard_project(request, project_id) if project_id else None

    form = ProjectForm(request.POST or None, instance=project)

    if request.method == 'POST' and form.is_valid():

        project = form.save(commit=False)
        project.user = request.user
        project.status = 'draft'
        project.save()

        return redirect('wizard_mcu', project_id=project.id)

    return render(
        request,
        'analyzer/wizard/project.html',
        _wizard_context('project', project, form=form),
    )


def _component_rows(project, categories):
    return (
        project.components
        .filter(category__in=categories)
        .prefetch_related('modes')
        .order_by('id')
    )


def _save_wizard_categories(request, project, categories):
    warnings = []

    with transaction.atomic():

        project.components.filter(category__in=categories).delete()

        for category in categories:
            _save_components(
                request.POST,
                request.FILES,
                project,
                category,
                warnings,
            )

    for warning in warnings:
        messages.warning(request, warning)


@login_required
def wizard_mcu(request, project_id):
    project = _wizard_project(request, project_id)

    if request.method == 'POST':

        if not any(
            value.strip()
            for key, value in request.POST.items()
            if key.startswith('mcu_name_')
        ):
            messages.error(request, 'Ajoutez au moins un microcontrôleur.')

        else:
            _save_wizard_categories(request, project, ('mcu',))

            return redirect('wizard_peripherals', project_id=project.id)

    return render(
        request,
        'analyzer/wizard/components.html',
        _wizard_context(
            'mcu',
            project,
            sections=(('mcu', 'Microcontrôleurs', True),),
            component_rows=_component_rows(project, ('mcu',)),
            previous_url='wizard_project_edit',
            next_label='Continuer vers les capteurs',
        ),
    )


@login_required
def wizard_peripherals(request, project_id):
    project = _wizard_project(request, project_id)

    if request.method == 'POST':

        _save_wizard_categories(
            request,
            project,
            ('sensor', 'communication'),
        )

        return redirect('wizard_actuators', project_id=project.id)

    return render(
        request,
        'analyzer/wizard/components.html',
        _wizard_context(
            'peripherals',
            project,
            sections=(
                ('sensor', 'Capteurs', False),
                ('communication', 'Communications', False),
            ),
            component_rows=_component_rows(
                project,
                ('sensor', 'communication'),
            ),
            previous_url='wizard_mcu',
            next_label='Continuer vers les actionneurs',
        ),
    )


@login_required
def wizard_actuators(request, project_id):
    project = _wizard_project(request, project_id)

    if request.method == 'POST':

        _save_wizard_categories(request, project, ('actuator',))

        return redirect('wizard_firmware', project_id=project.id)

    return render(
        request,
        'analyzer/wizard/components.html',
        _wizard_context(
            'actuators',
            project,
            sections=(('actuator', 'Actionneurs et charges', False),),
            component_rows=_component_rows(project, ('actuator',)),
            previous_url='wizard_peripherals',
            next_label='Continuer vers le programme',
        ),
    )


@login_required
def wizard_firmware(request, project_id):
    project = _wizard_project(request, project_id)

    firmware = project.firmwares.first()

    form = FirmwareForm(
        request.POST or None,
        request.FILES or None,
        instance=firmware,
    )

    if request.method == 'POST' and form.is_valid():

        firmware = form.save(commit=False)
        firmware.project = project
        firmware.save()

        return redirect('wizard_energy', project_id=project.id)

    return render(
        request,
        'analyzer/wizard/firmware.html',
        _wizard_context('firmware', project, form=form),
    )


# ============================================================
# VALIDATION DATASHEET BATTERIE
# ============================================================

def _validate_battery_datasheet(uploaded_file):
    """
    Vérifie la datasheet de batterie :
    - extension PDF ;
    - taille maximale ;
    - signature PDF.
    """

    if not uploaded_file:
        return

    filename = str(uploaded_file.name or '').strip().lower()

    if not filename.endswith('.pdf'):
        raise ValidationError(
            'La datasheet de la batterie doit être fournie au format PDF.'
        )

    maximum_size = 10 * 1024 * 1024

    if uploaded_file.size > maximum_size:
        raise ValidationError(
            'La datasheet de la batterie ne doit pas dépasser 10 Mo.'
        )

    try:
        signature = uploaded_file.read(5)
        uploaded_file.seek(0)

    except (OSError, AttributeError) as exc:
        raise ValidationError(
            'Impossible de lire la datasheet de la batterie.'
        ) from exc

    if signature != b'%PDF-':
        raise ValidationError(
            'Le fichier fourni ne contient pas un document PDF valide.'
        )


@login_required
def wizard_energy(request, project_id):
    project = _wizard_project(request, project_id)

    solar = getattr(project, 'solar_pref', None)
    battery = getattr(project, 'battery_pref', None)

    solar_form = SolarPreferenceForm(
        request.POST or None,
        instance=solar,
        prefix='solar',
    )

    battery_form = BatteryPreferenceForm(
        request.POST or None,
        instance=battery,
        prefix='battery',
    )

    if request.method == 'POST':

        solar_is_valid = solar_form.is_valid()
        battery_is_valid = battery_form.is_valid()

        if solar_is_valid and battery_is_valid:

            battery_datasheet = request.FILES.get('battery_datasheet')

            try:
                _validate_battery_datasheet(battery_datasheet)

            except ValidationError as exc:

                for error_message in exc.messages:
                    messages.error(request, error_message)

            else:

                with transaction.atomic():

                    solar = solar_form.save(commit=False)
                    solar.project = project
                    solar.save()

                    battery = battery_form.save(commit=False)
                    battery.project = project

                    if battery_datasheet:
                        battery.battery_datasheet = battery_datasheet

                    battery.save()

                messages.success(
                    request,
                    'Les préférences énergétiques ont été enregistrées.'
                )

                return redirect('wizard_review', project_id=project.id)

    return render(
        request,
        'analyzer/wizard/energy.html',
        _wizard_context(
            'energy',
            project,
            solar_form=solar_form,
            battery_form=battery_form,
            battery=battery,
        ),
    )


@login_required
def wizard_review(request, project_id):
    project = _wizard_project(request, project_id)

    components = project.components.prefetch_related('modes').all()

    firmware = project.firmwares.first()

    if not firmware:

        messages.error(request, 'Complétez d’abord l’étape Programme.')

        return redirect('wizard_firmware', project_id=project.id)

    if (
        not hasattr(project, 'solar_pref')
        or not hasattr(project, 'battery_pref')
    ):

        messages.error(request, 'Complétez les préférences énergétiques.')

        return redirect('wizard_energy', project_id=project.id)

    return render(
        request,
        'analyzer/wizard/review.html',
        _wizard_context(
            'review',
            project,
            components=components,
            firmware=firmware,
            solar=project.solar_pref,
            battery=project.battery_pref,
        ),
    )


# ============================================================
# EXTRACTION ÉNERGIE JOURNALIÈRE
# ============================================================

def _extract_daily_wh(results):
    """Retourne l'énergie journalière en Wh."""

    if not isinstance(results, dict):
        return 0.0

    engineering = _as_dict(results.get('engineering_analysis'))

    energy = _first_dict(
        engineering.get('energy'),
        results.get('energy'),
        results.get('energy_profile'),
    )

    candidates = [
        results.get('daily_energy_wh'),
        (
            results.get('summary', {}).get('daily_energy_wh')
            if isinstance(results.get('summary'), dict)
            else None
        ),
        energy.get('daily_energy_wh'),
    ]

    for value in candidates:

        converted = _to_float(value)

        if converted is not None:
            return converted

    daily_mwh = _to_float(
        results.get('daily_energy_mwh')
        or energy.get('daily_energy_mwh')
        or energy.get('energy_daily_mwh')
    )

    if daily_mwh is not None:
        return daily_mwh / 1000.0

    return 0.0


# ============================================================
# VALIDATION RÉSULTAT N8N
# ============================================================

def _is_valid_n8n_result(result):
    """Vérifie que n8n a retourné un rapport exploitable."""

    result = _unwrap_n8n_result(result)

    if not isinstance(result, dict) or not result:
        return False

    if result.get('error'):
        return False

    if result.get('valid') is False:
        return False

    status = str(result.get('status', '')).lower()

    if status in {'error', 'failed', 'failure'}:
        return False

    expected_keys = {
        'summary',
        'energy',
        'battery',
        'solar',
        'power',
        'engineering_analysis',
        'energy_profile',
        'daily_energy_mah',
        'daily_energy_mwh',
        'battery_recommendation',
        'solar_report',
    }

    # Un rapport doit contenir au moins une section métier.
    return any(key in result for key in expected_keys)


# ============================================================
# SAUVEGARDE DES COMPOSANTS
# ============================================================

def _save_components(post_data, files, project, category, warnings):
    indices = _get_indices(post_data, f'{category}_name_')

    for i in indices:

        name = post_data.get(f'{category}_name_{i}', '').strip()

        if not name:
            continue

        raw_voltage = post_data.get(f'{category}_voltage_{i}', '').strip()

        voltage = _to_float(raw_voltage)

        voltage_provided = bool(raw_voltage)

        try:

            comp = Component(
                project=project,
                name=name,
                category=category,
            )

            if voltage is not None:
                comp.voltage = voltage

            if category == 'mcu':

                nominal = _to_float(
                    post_data.get(f'{category}_nominal_{i}', '')
                )
                cores = _to_int(post_data.get(f'{category}_cores_{i}', ''))
                fmin = _to_float(post_data.get(f'{category}_fmin_{i}', ''))
                fmax = _to_float(post_data.get(f'{category}_fmax_{i}', ''))
                fused = _to_float(post_data.get(f'{category}_fused_{i}', ''))

                if nominal is not None:
                    comp.nominal_current_ma = nominal

                if cores is not None:
                    comp.cores_count = cores

                if fmin is not None:
                    comp.freq_min_mhz = fmin

                if fmax is not None:
                    comp.freq_max_mhz = fmax

                if fused is not None:
                    comp.freq_used_mhz = fused

            if category == 'actuator':

                sep_power = post_data.get(f'{category}_seppower_{i}', '')

                comp.separate_power = sep_power == 'on'

            datasheet_key = f'{category}_datasheet_{i}'

            if datasheet_key in files:
                comp.datasheet = files[datasheet_key]

            comp.save()

            _apply_datasheet_fallback(
                comp,
                warnings,
                override_voltage=not voltage_provided,
            )

            _save_modes_for_component(
                post_data,
                comp,
                category,
                i,
                warnings,
            )

        except (ValueError, TypeError) as error:

            warnings.append(
                f'⚠️ {category.upper()} #{i + 1} : erreur ({error})'
            )


def _apply_datasheet_fallback(component, warnings, override_voltage=False):
    extracted = extract_component_values_from_datasheet(component)

    updated = False

    if override_voltage:

        voltage = _to_float(extracted.get('voltage'))

        if voltage is not None:
            component.voltage = voltage
            updated = True

    if component.category == 'mcu':

        for field, key in [
            ('nominal_current_ma', 'nominal_current_ma'),
            ('cores_count', 'cores_count'),
            ('freq_min_mhz', 'freq_min_mhz'),
            ('freq_max_mhz', 'freq_max_mhz'),
            ('freq_used_mhz', 'freq_used_mhz'),
        ]:

            if getattr(component, field) is None:

                value = (
                    _to_float(extracted.get(key))
                    if 'count' not in field
                    else _to_int(extracted.get(key))
                )

                if value is not None:
                    setattr(component, field, value)
                    updated = True

    if updated:
        component.save()


def _save_modes_for_component(
    post_data,
    component,
    category,
    comp_idx,
    warnings,
):
    mode_prefix = f'{category}_mode_name_{comp_idx}_'

    indices = _get_indices(post_data, mode_prefix)

    for mi in indices:

        name = post_data.get(
            f'{category}_mode_name_{comp_idx}_{mi}',
            '',
        ).strip()

        if not name:
            continue

        current = _to_float(
            post_data.get(f'{category}_mode_current_{comp_idx}_{mi}', '')
        )

        duration = _to_float(
            post_data.get(f'{category}_mode_duration_{comp_idx}_{mi}', '')
        )

        count = _to_int(
            post_data.get(f'{category}_mode_count_{comp_idx}_{mi}', '1')
        )

        if count is None or count <= 0:
            count = 1

        if (current is None or duration is None) and component.datasheet:

            extracted = extract_mode_values_from_datasheet(component, name)

            if current is None:
                current = _to_float(extracted.get('current_ma'))

            if duration is None:
                duration = _to_float(extracted.get('duration_ms'))

        if current is None or duration is None:

            warnings.append(
                f'⚠️ {component.name}/{name} : valeurs manquantes.'
            )

            continue

        try:

            ConsumptionMode.objects.create(
                component=component,
                name=name,
                current_ma=current,
                duration_ms=duration,
                count_per_cycle=count,
            )

        except (ValueError, TypeError) as error:

            warnings.append(
                f'⚠️ {component.name}/{name} : erreur ({error})'
            )


# ============================================================
# PRÉFÉRENCES SOLAIRES POUR N8N
# ============================================================

def _build_solar_preferences(project):
    """
    Construit le bloc `solar_preferences` envoyé à n8n à partir du
    formulaire « Panneau solaire » (SolarPreference).

    L'orientation et l'inclinaison viennent maintenant du formulaire ;
    les anciennes valeurs par défaut (sud, 30°) ne servent que si
    l'utilisateur laisse les champs vides.
    """

    solar_preferences = {
        # Votre demande : recommend | verify | none
        'objective': 'recommend',
        'enabled': True,

        # Contraintes facultatives
        'preferred_type': 'auto',
        'panel_type': 'auto',
        'max_surface_cm2': None,
        'max_budget': None,
        'currency': '',

        'sun_hours': (
            project.sun_hours_worst
            or project.sun_hours_annual
            or None
        ),

        # Où sera placé le panneau ?
        'placement': '',
        'panel_installation_type': project.installation_type or 'outdoor',
        'shading_notes': '',
        'lighting_notes': '',
        'orientation': 'south',
        'azimuth_deg': 180,
        'inclination_deg': 30,

        # Matériel choisi (mode « verify » uniquement)
        'chosen_hardware': None,
    }

    try:

        solar_pref = project.solar_pref

        azimuth = solar_pref.azimuth_deg
        tilt = solar_pref.tilt_deg

        solar_preferences.update({
            'objective': solar_pref.objective,
            'enabled': solar_pref.objective != 'none',

            'preferred_type': solar_pref.panel_type,
            'panel_type': solar_pref.panel_type,
            'max_surface_cm2': solar_pref.max_surface_cm2,
            'max_budget': (
                float(solar_pref.max_budget)
                if solar_pref.max_budget is not None
                else None
            ),
            'currency': (solar_pref.currency or '').strip(),

            'placement': solar_pref.placement,
            'shading_notes': solar_pref.shading_notes or '',
            'lighting_notes': solar_pref.lighting_notes or '',
        })

        if solar_pref.placement:
            solar_preferences['panel_installation_type'] = (
                installation_type_from_placement(solar_pref.placement)
            )

        if azimuth is not None:
            solar_preferences['azimuth_deg'] = azimuth

        if tilt is not None:
            solar_preferences['inclination_deg'] = tilt

        if solar_pref.objective == 'verify':

            panel_power = solar_pref.panel_power_w
            panel_count = solar_pref.panel_count or 1

            solar_preferences['chosen_hardware'] = {
                'model': solar_pref.chosen_model or '',
                'technology': solar_pref.chosen_technology or '',
                'panel_power_w': panel_power,
                'panel_count': panel_count,
                'total_power_w': (
                    round(panel_power * panel_count, 2)
                    if panel_power is not None
                    else None
                ),
                'vmp_v': solar_pref.vmp_v,
                'voc_v': solar_pref.voc_v,
                'imp_ma': solar_pref.imp_ma,
                'isc_ma': solar_pref.isc_ma,
            }

    except Exception:
        pass

    return solar_preferences


# ============================================================
# ENVOI N8N
# ============================================================

def _send_to_n8n(project):
    """
    Envoie toutes les données réelles du projet Django
    au workflow principal AIDE-IoT.
    """

    components_data = []

    mcu_voltages = {
        float(component.voltage)
        for component in project.components.filter(category='mcu')
        if component.voltage is not None and float(component.voltage) > 0
    }

    load_voltage_v = (
        next(iter(mcu_voltages)) if len(mcu_voltages) == 1 else None
    )

    components = project.components.prefetch_related('modes').all()

    for component in components:

        operating_modes = [
            {
                'name': mode.name,
                'current_ma': mode.current_ma,
                'duration_ms': mode.duration_ms,
                'count_per_cycle': mode.count_per_cycle,
                'frequency_mhz': mode.freq_mhz,
                'value_source': 'manual',
            }
            for mode in component.modes.all()
        ]

        component_document = {
            'provided': bool(component.datasheet),
            'status': 'not_provided',
            'filename': (
                component.datasheet.name.rsplit('/', 1)[-1]
                if component.datasheet
                else None
            ),
            'extracted_data': {},
            'requires_manual_validation': True,
            'warnings': [],
        }

        if component.datasheet:

            try:

                extraction = extract_component_values_from_datasheet(
                    component
                )

                if isinstance(extraction, dict):

                    raw_values = extraction.get('extracted_data', extraction)

                    if isinstance(raw_values, dict):

                        allowed = (
                            'voltage',
                            'voltage_v',
                            'nominal_current_ma',
                            'cores_count',
                            'freq_min_mhz',
                            'freq_max_mhz',
                            'freq_used_mhz',
                        )

                        component_document['extracted_data'] = {
                            key: raw_values[key]
                            for key in allowed
                            if key in raw_values
                            and raw_values[key] is not None
                        }

                    component_document['status'] = (
                        'extracted'
                        if component_document['extracted_data']
                        else 'no_values_extracted'
                    )

                    extraction_warnings = extraction.get('warnings')

                    component_document['warnings'] = (
                        [str(item) for item in extraction_warnings][:20]
                        if isinstance(extraction_warnings, list)
                        else []
                    )

                else:
                    component_document['status'] = 'extraction_failed'

            except Exception:

                logger.exception(
                    'Extraction de la fiche du composant %s',
                    component.id,
                )

                component_document['status'] = 'extraction_failed'

        components_data.append({
            'id': str(component.id),
            'name': component.name,
            'category': component.category,
            'datasheet': component_document,
            'voltage_v': component.voltage,
            'nominal_current_ma': component.nominal_current_ma,
            'separate_power': component.separate_power,
            'cores_count': component.cores_count,
            'frequency_min_mhz': component.freq_min_mhz,
            'frequency_max_mhz': component.freq_max_mhz,
            'frequency_used_mhz': component.freq_used_mhz,
            'operating_modes': operating_modes,
        })

    firmware_data = []

    for firmware in project.firmwares.all():

        firmware_data.append({
            'id': str(firmware.id),
            'source_code': firmware.source_code or '',
            'has_code_file': bool(firmware.code_file),
        })

    solar_preferences = _build_solar_preferences(project)

    battery_preferences = {}

    battery_datasheet_data = {
        'provided': False,
        'status': 'not_provided',
        'source': None,
        'filename': None,
        'extracted_data': {},
        'warnings': [],
    }

    try:

        battery_pref = project.battery_pref

        # Tous les champs du modèle sont envoyés automatiquement
        # (objective, chosen_model, chosen_technology, value_scope,
        # nominal_voltage_v, capacity_mah, cells_series, cells_parallel,
        # autonomy_days, max_*, currency, rechargeable_only...).
        battery_preferences = {
            field.name: getattr(battery_pref, field.name)
            for field in battery_pref._meta.fields
            if field.name not in {'id', 'project', 'battery_datasheet'}
        }

        battery_preferences['preferred_type'] = battery_pref.battery_type

        battery_datasheet_data = extract_battery_values_from_datasheet(
            battery_pref
        )

    except Exception:

        logger.exception(
            'Impossible de préparer les préférences ou la '
            'datasheet de la batterie.'
        )

    # ==========================================================
    # CALCUL DES CYCLES RÉELS PAR JOUR
    # ==========================================================

    component_cycle_durations_ms = []

    for component_data in components_data:

        component_duration_ms = 0.0

        for mode_data in component_data.get('operating_modes', []):

            duration_ms = _to_float(mode_data.get('duration_ms'))

            count_per_cycle = _to_int(mode_data.get('count_per_cycle'))

            if count_per_cycle is None:
                count_per_cycle = 1

            if (
                duration_ms is not None
                and duration_ms > 0
                and count_per_cycle > 0
            ):
                component_duration_ms += duration_ms * count_per_cycle

        if component_duration_ms > 0:
            component_cycle_durations_ms.append(component_duration_ms)

    cycle_duration_ms = max(component_cycle_durations_ms, default=0.0)

    if cycle_duration_ms > 0:

        cycles_per_day = max(1, int(86_400_000 // cycle_duration_ms))

    else:

        cycles_per_day = getattr(
            settings,
            'ENERGY_DEFAULT_CYCLES_PER_DAY',
            1440,
        )

        try:
            cycles_per_day = int(cycles_per_day)
        except (TypeError, ValueError):
            cycles_per_day = 1440

        if cycles_per_day <= 0:
            cycles_per_day = 1440

    payload = {
        'request_metadata': {
            'source': 'django',
            'request_type': 'complete_energy_analysis',
            'project_id': str(project.id),
            'request_id': str(uuid.uuid4()),
        },

        'project': {
            'id': str(project.id),
            'name': project.name,
            'description': project.description or '',
            'installation_type': project.installation_type or 'outdoor',
            'cycles_per_day': cycles_per_day,
            'load_voltage_v': load_voltage_v,
            'sun_hours_annual': project.sun_hours_annual,
            'sun_hours_worst': project.sun_hours_worst,
            'location': {
                'city': project.location_city,
                'country': project.location_country,
                'latitude': project.latitude,
                'longitude': project.longitude,
            },
        },

        'components': components_data,

        'firmware': firmware_data,

        'solar_preferences': solar_preferences,

        'battery_preferences': battery_preferences,

        'battery_datasheet': battery_datasheet_data,

        'preferences': {
            'solar': solar_preferences,
            'battery': battery_preferences,
        },

        'analysis_options': {
            'analyze_firmware': True,
            'calculate_energy': True,
            'calculate_battery': True,
            'calculate_solar': solar_preferences.get('enabled', True),
            'calculate_adapter': True,
            'compare_solutions': True,
            'generate_recommendations': True,
        },
    }

    webhook_url = getattr(settings, 'N8N_ENERGY_WEBHOOK_URL', None)

    if not webhook_url:

        logger.error('N8N_ENERGY_WEBHOOK_URL n’est pas configurée.')

        return None

    timeout_seconds = getattr(settings, 'N8N_ENERGY_TIMEOUT_SECONDS', 300)

    try:
        timeout_seconds = float(timeout_seconds)
    except (TypeError, ValueError):
        timeout_seconds = 300.0

    if timeout_seconds <= 0:
        timeout_seconds = 300.0

    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }

    api_key = getattr(settings, 'N8N_ENERGY_API_KEY', '')

    if api_key:
        headers['X-EnergyAI-Key'] = api_key

    # Sérialisation sûre : évite un TypeError (Decimal, date, fichier...)
    # qui ferait planter la vue avant même l'appel à n8n.
    try:

        body = json.dumps(
            payload,
            default=_json_default,
            ensure_ascii=False,
        ).encode('utf-8')

    except (TypeError, ValueError):

        logger.exception('Impossible de sérialiser la requête vers n8n.')

        return None

    try:

        response = requests.post(
            webhook_url,
            data=body,
            headers=headers,
            timeout=timeout_seconds,
        )

        response.raise_for_status()

    except requests.Timeout:

        logger.exception('Délai dépassé pendant l’appel du workflow n8n.')

        return None

    except requests.ConnectionError:

        logger.exception('Impossible de joindre le service n8n.')

        return None

    except requests.HTTPError:

        logger.error(
            'Erreur HTTP n8n %s : %s',
            response.status_code,
            response.text[:1000],
        )

        return None

    except requests.RequestException:

        logger.exception('Erreur réseau pendant l’appel du workflow n8n.')

        return None

    try:

        data = response.json()

    except ValueError:

        logger.error(
            'n8n a retourné une réponse non JSON : %s',
            response.text[:1000],
        )

        return None

    data = _unwrap_n8n_result(data)

    if not isinstance(data, dict):

        logger.error(
            'Format de réponse n8n invalide : %s',
            type(data).__name__,
        )

        return None

    logger.info(
        'Réponse n8n reçue et normalisée (clés : %s).',
        ', '.join(sorted(str(key) for key in data.keys())),
    )

    return data


# ============================================================
# RAPPORT
# ============================================================

@login_required
def report(request, project_id):
    """
    Affiche le dashboard professionnel d'un projet analysé.

    Compatible avec :
    - nouveau format FastAPI ;
    - ancien format n8n/local ;
    - résultat stocké dans full_report ;
    - champs séparés AnalysisResult.
    """

    project = get_object_or_404(
        Project,
        id=project_id,
        user=request.user,
    )

    try:
        result = project.result

    except AnalysisResult.DoesNotExist:
        result = None

    full_report = {}
    engineering = {}
    executive_summary = {}
    energy = {}
    battery = {}
    solar = {}
    power = {}
    lifecycle = {}
    timeline = {}
    consumption_profile = {}
    score = {}
    pvgis_data = {}

    # ==========================================================
    # 1. RÉCUPÉRATION DU RAPPORT
    # ==========================================================

    if result:

        if isinstance(result.full_report, dict):
            full_report = result.full_report

        engineering = _as_dict(full_report.get('engineering_analysis'))

        energy = (
            engineering.get('energy')
            or full_report.get('energy')
            or result.energy_profile
            or {}
        )

        battery = (
            engineering.get('battery')
            or full_report.get('battery')
            or result.battery_recommendation
            or {}
        )

        solar = (
            engineering.get('solar')
            or full_report.get('solar')
            or result.solar_report
            or {}
        )

        power = (
            engineering.get('power')
            or full_report.get('power')
            or result.adapter_recommendation
            or {}
        )

        lifecycle = engineering.get('lifecycle_simulation') or {}

        timeline = engineering.get('timeline') or {}

        consumption_profile = engineering.get('consumption_profile') or {}

        score = engineering.get('score') or {}

        executive_summary = (
            engineering.get('executive_summary')
            or result.summary
            or {}
        )

        # ======================================================
        # PVGIS
        # ======================================================

        pvgis_candidates = (
            full_report.get('pvgis_result'),
            full_report.get('pvgis'),
            engineering.get('pvgis_result'),
            engineering.get('pvgis'),
            solar.get('pvgis_result') if isinstance(solar, dict) else None,
        )

        for candidate in pvgis_candidates:

            if isinstance(candidate, dict) and candidate:
                pvgis_data = candidate
                break

    # On force des dictionnaires pour que les .get() ci-dessous
    # ne plantent jamais si le moteur renvoie une liste ou une chaîne.
    energy = _as_dict(energy)
    battery = _as_dict(battery)
    solar = _as_dict(solar)
    power = _as_dict(power)
    lifecycle = _as_dict(lifecycle)
    timeline = _as_dict(timeline)
    consumption_profile = _as_dict(consumption_profile)
    score = _as_dict(score)
    executive_summary = _as_dict(executive_summary)

    # ==========================================================
    # 2. DONNÉES PVGIS
    # ==========================================================

    raw_solar = solar

    sun_hours_worst = (
        pvgis_data.get('sun_hours_worst')
        or raw_solar.get('sun_hours_worst')
        or raw_solar.get('sun_hours')
        or project.sun_hours_worst
    )

    sun_hours_annual = (
        pvgis_data.get('sun_hours_annual')
        or raw_solar.get('sun_hours_annual')
        or project.sun_hours_annual
    )

    annual_irradiation = (
        pvgis_data.get('annual_irradiation_kwh_m2')
        or raw_solar.get('annual_irradiation_kwh_m2')
    )

    worst_month = (
        pvgis_data.get('worst_month')
        or raw_solar.get('worst_month')
    )

    month_names = {
        1: 'Janvier',
        2: 'Février',
        3: 'Mars',
        4: 'Avril',
        5: 'Mai',
        6: 'Juin',
        7: 'Juillet',
        8: 'Août',
        9: 'Septembre',
        10: 'Octobre',
        11: 'Novembre',
        12: 'Décembre',
    }

    worst_month_label = None

    try:

        if worst_month is not None:
            worst_month_label = month_names.get(int(float(worst_month)))

    except (TypeError, ValueError):

        worst_month_label = str(worst_month)

    pvgis_source = (
        pvgis_data.get('source')
        or raw_solar.get('sun_hours_source')
        or raw_solar.get('irradiation_source')
        or raw_solar.get('source')
    )

    if not pvgis_source and sun_hours_worst is not None:
        pvgis_source = 'PVGIS via le workflow n8n'

    pvgis_trace = {
        'available': sun_hours_worst is not None,
        'source': pvgis_source or 'Source non disponible',
        'sun_hours_worst': sun_hours_worst,
        'sun_hours_annual': sun_hours_annual,
        'annual_irradiation_kwh_m2': annual_irradiation,
        'worst_month': worst_month,
        'worst_month_label': worst_month_label,
        'latitude': pvgis_data.get('latitude') or project.latitude,
        'longitude': pvgis_data.get('longitude') or project.longitude,
        'metadata_complete': bool(pvgis_data),
    }

    # ==========================================================
    # 3. TRADUCTION
    # ==========================================================

    energy = _translate_report_value(energy)
    battery = _translate_report_value(battery)
    solar = _translate_report_value(solar)
    power = _translate_report_value(power)
    lifecycle = _translate_report_value(lifecycle)
    consumption_profile = _translate_report_value(consumption_profile)
    score = _translate_report_value(score)
    executive_summary = _translate_report_value(executive_summary)

    # ==========================================================
    # 4. CYCLES PAR JOUR (affichage « cycles/j » du rapport)
    # ==========================================================

    cycles_per_day = _compute_cycles_per_day(energy)

    if cycles_per_day is not None:
        energy['cycles_per_day'] = cycles_per_day

    # ==========================================================
    # 5. FRANÇAIS POUR LES RÉSUMÉS
    # ==========================================================

    for section in (
        energy,
        battery,
        solar,
        power,
        lifecycle,
        consumption_profile,
        executive_summary,
    ):

        if isinstance(section, dict) and 'summary' in section:
            section['summary'] = _frenchify_decimals(section['summary'])

    # ==========================================================
    # 6. DONNÉES GRAPHIQUES
    # ==========================================================

    timeline_points = timeline.get('points', [])

    if not isinstance(timeline_points, list):
        timeline_points = []

    timeline_points = [
        point for point in timeline_points if isinstance(point, dict)
    ]

    lifecycle_years = lifecycle.get('annual_results', [])

    if not isinstance(lifecycle_years, list):
        lifecycle_years = []

    lifecycle_years = [
        item for item in lifecycle_years if isinstance(item, dict)
    ]

    def _year_section(item, key):
        return _as_dict(item.get(key))

    chart_data = {
        'timeline': {
            'labels': [p.get('time_ms', 0) for p in timeline_points],
            'current': [p.get('current_ma', 0) for p in timeline_points],
            'power': [p.get('power_mw', 0) for p in timeline_points],
            'energy': [
                p.get('cumulative_energy_mwh', 0) for p in timeline_points
            ],
        },

        'lifecycle': {
            'years': [item.get('year', 0) for item in lifecycle_years],

            'battery_health': [
                _year_section(item, 'battery').get(
                    'state_of_health_percent', 0
                )
                for item in lifecycle_years
            ],

            'battery_capacity': [
                _year_section(item, 'battery').get(
                    'remaining_capacity_mah', 0
                )
                for item in lifecycle_years
            ],

            'autonomy': [
                _year_section(item, 'battery').get(
                    'estimated_autonomy_days', 0
                )
                for item in lifecycle_years
            ],

            'panel_power': [
                _year_section(item, 'solar').get(
                    'degraded_panel_power_w', 0
                )
                for item in lifecycle_years
            ],
        },

        'score': {
            'labels': [
                'Energy',
                'Battery',
                'Solar',
                'Power',
                'Reliability',
            ],

            'values': [
                score.get('energy_score', 0),
                score.get('battery_score', 0),
                score.get('solar_score', 0),
                score.get('power_score', 0),
                score.get('reliability_score', 0),
            ],
        },
    }

    # ==========================================================
    # 7. WARNINGS / RECOMMANDATIONS
    # ==========================================================

    warnings = []
    recommendations = []

    for section in (energy, battery, solar, power, lifecycle):

        if not isinstance(section, dict):
            continue

        section_warnings = section.get('warnings', [])

        if isinstance(section_warnings, list):
            warnings.extend(section_warnings)

        section_recommendations = section.get('recommendations', [])

        if isinstance(section_recommendations, list):
            recommendations.extend(section_recommendations)

    warnings = list(
        dict.fromkeys(
            str(item).strip() for item in warnings if str(item).strip()
        )
    )

    recommendations = list(
        dict.fromkeys(
            str(item).strip()
            for item in recommendations
            if str(item).strip()
        )
    )

    # ==========================================================
    # 8. CONTEXTE DU TEMPLATE
    # ==========================================================

    context = {
        'project': project,
        'result': result,
        'full_report': full_report,
        'engineering': engineering,
        'executive_summary': executive_summary,
        'energy': energy,
        'battery': battery,
        'solar': solar,
        'power': power,
        'lifecycle': lifecycle,
        'timeline': timeline,
        'consumption_profile': consumption_profile,
        'score': score,
        'pvgis': pvgis_trace,
        'warnings': warnings,
        'recommendations': recommendations,
        'chart_data_json': chart_data,

        'curve_json': json.dumps(
            result.consumption_curve
            if (result and result.consumption_curve)
            else [],
            ensure_ascii=False,
        ),

        'states_json': json.dumps(
            result.energy_profile.get('states', [])
            if (result and isinstance(result.energy_profile, dict))
            else [],
            ensure_ascii=False,
        ),
    }

    return render(request, 'analyzer/report.html', context)


# ============================================================
# LISTE DES PROJETS
# ============================================================

@login_required
def project_list(request):

    projects = (
        Project.objects
        .filter(user=request.user)
        .order_by('-id')
    )

    return render(
        request,
        'analyzer/project_list.html',
        {'projects': projects},
    )


# ============================================================
# INSCRIPTION
# ============================================================

def register(request):

    if request.method == 'POST':

        form = CustomUserCreationForm(request.POST)

        if form.is_valid():

            user = form.save()

            login(request, user)

            messages.success(request, f"Bienvenue {user.display_name}")

            return redirect('home')

    else:

        form = CustomUserCreationForm()

    return render(
        request,
        'analyzer/auth/register.html',
        {'form': form},
    )


# ============================================================
# PROFIL
# ============================================================

@login_required
def profile(request):

    return render(request, 'analyzer/auth/profile.html')


# ============================================================
# MOT DE PASSE OUBLIÉ
# ============================================================

def forgot_password(request):
    """
    Étape 1 :
    l'utilisateur saisit son adresse e-mail et reçoit
    un code à 6 chiffres.
    """

    if request.method == 'POST':

        email = request.POST.get('email', '').strip().lower()

        if not email:

            messages.error(request, "Veuillez saisir votre adresse e-mail.")

            return render(
                request,
                'analyzer/auth/forgot_password.html',
                {'email': email},
            )

        user = CustomUser.objects.filter(email__iexact=email).first()

        if user is None:

            messages.error(
                request,
                "Aucun compte n'est associé à cette adresse e-mail."
            )

            return render(
                request,
                'analyzer/auth/forgot_password.html',
                {'email': email},
            )

        reset_code = PasswordResetCode.create_for_user(user)

        subject = "Code de réinitialisation de votre mot de passe"

        message = (
            f"Bonjour {user.display_name},\n\n"
            f"Votre code de réinitialisation est : {reset_code.code}\n\n"
            "Ce code est valable pendant 10 minutes.\n"
            "Ne communiquez jamais ce code à une autre personne.\n\n"
            "Assistant Énergétique IoT"
        )

        try:

            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )

        except Exception:

            reset_code.is_used = True
            reset_code.save(update_fields=['is_used'])

            logger.exception("Erreur d'envoi de l'e-mail.")

            messages.error(
                request,
                "Impossible d'envoyer le code. Vérifiez la configuration "
                "du serveur d'e-mail."
            )

            return render(
                request,
                'analyzer/auth/forgot_password.html',
                {'email': email},
            )

        request.session['password_reset_user_id'] = user.pk
        request.session['password_reset_verified'] = False

        messages.success(
            request,
            "Un code à 6 chiffres a été envoyé à votre adresse e-mail."
        )

        return redirect('verify_reset_code')

    return render(request, 'analyzer/auth/forgot_password.html')


# ============================================================
# VÉRIFICATION DU CODE
# ============================================================

def verify_reset_code(request):
    """
    Étape 2 :
    l'utilisateur saisit le code reçu par e-mail.
    """

    user_id = request.session.get('password_reset_user_id')

    if not user_id:

        messages.error(request, "Commencez par saisir votre adresse e-mail.")

        return redirect('forgot_password')

    user = CustomUser.objects.filter(pk=user_id).first()

    if user is None:

        request.session.pop('password_reset_user_id', None)
        request.session.pop('password_reset_verified', None)

        messages.error(request, "Utilisateur introuvable.")

        return redirect('forgot_password')

    if request.method == 'POST':

        submitted_code = request.POST.get('code', '').strip()

        if not submitted_code.isdigit() or len(submitted_code) != 6:

            messages.error(
                request,
                "Le code doit contenir exactement 6 chiffres."
            )

            return render(
                request,
                'analyzer/auth/verify_reset_code.html',
                {'email': user.email},
            )

        # Toujours le code le plus récent non utilisé.
        reset_code = (
            PasswordResetCode.objects
            .filter(user=user, is_used=False)
            .order_by('-id')
            .first()
        )

        if reset_code is None:

            messages.error(
                request,
                "Aucun code valide n'a été trouvé. Demandez un nouveau code."
            )

            return redirect('forgot_password')

        if not reset_code.is_valid():

            reset_code.is_used = True
            reset_code.save(update_fields=['is_used'])

            messages.error(
                request,
                "Ce code a expiré ou le nombre maximal d'essais a été atteint."
            )

            return redirect('forgot_password')

        if not constant_time_compare(reset_code.code, submitted_code):

            reset_code.attempts += 1
            reset_code.save(update_fields=['attempts'])

            remaining_attempts = max(0, 5 - reset_code.attempts)

            if remaining_attempts == 0:

                reset_code.is_used = True
                reset_code.save(update_fields=['is_used'])

                messages.error(
                    request,
                    "Trop de tentatives incorrectes. Demandez un nouveau code."
                )

                return redirect('forgot_password')

            messages.error(
                request,
                f"Code incorrect. Il vous reste {remaining_attempts} "
                "tentative(s)."
            )

            return render(
                request,
                'analyzer/auth/verify_reset_code.html',
                {'email': user.email},
            )

        reset_code.is_used = True
        reset_code.save(update_fields=['is_used'])

        request.session['password_reset_verified'] = True

        messages.success(
            request,
            "Code vérifié. Vous pouvez maintenant choisir un nouveau "
            "mot de passe."
        )

        return redirect('new_password')

    return render(
        request,
        'analyzer/auth/verify_reset_code.html',
        {'email': user.email},
    )


# ============================================================
# NOUVEAU MOT DE PASSE
# ============================================================

def new_password(request):
    """
    Étape 3 :
    l'utilisateur choisit son nouveau mot de passe.
    """

    user_id = request.session.get('password_reset_user_id')

    is_verified = request.session.get('password_reset_verified', False)

    if not user_id or not is_verified:

        messages.error(
            request,
            "Vous devez d'abord vérifier le code reçu par e-mail."
        )

        return redirect('forgot_password')

    user = CustomUser.objects.filter(pk=user_id).first()

    if user is None:

        request.session.pop('password_reset_user_id', None)
        request.session.pop('password_reset_verified', None)

        messages.error(request, "Utilisateur introuvable.")

        return redirect('forgot_password')

    if request.method == 'POST':

        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')

        if not password1 or not password2:

            messages.error(
                request,
                "Veuillez remplir les deux champs de mot de passe."
            )

            return render(request, 'analyzer/auth/new_password.html')

        if password1 != password2:

            messages.error(
                request,
                "Les deux mots de passe ne correspondent pas."
            )

            return render(request, 'analyzer/auth/new_password.html')

        try:

            validate_password(password1, user=user)

        except ValidationError as errors:

            for error in errors.messages:
                messages.error(request, error)

            return render(request, 'analyzer/auth/new_password.html')

        user.set_password(password1)
        user.save(update_fields=['password'])

        PasswordResetCode.objects.filter(
            user=user,
            is_used=False,
        ).update(is_used=True)

        request.session.pop('password_reset_user_id', None)
        request.session.pop('password_reset_verified', None)

        messages.success(
            request,
            "Votre mot de passe a été modifié. Vous pouvez maintenant "
            "vous connecter."
        )

        return redirect('login')

    return render(request, 'analyzer/auth/new_password.html')