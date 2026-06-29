from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login

from .models import Project, ConsumptionMode, AnalysisResult
from .forms import ProjectForm, ComponentFormSet, FirmwareForm, CustomUserCreationForm
from .calculator import EnergyCalculator
import json
import requests


def home(request):
    projects = Project.objects.all()[:10]
    return render(request, 'analyzer/home.html', {'projects': projects})


@login_required
def project_create(request):
    if request.method == 'POST':
        form = ProjectForm(request.POST)
        comp_formset = ComponentFormSet(request.POST, request.FILES, prefix='components')
        firm_form = FirmwareForm(request.POST, request.FILES)

        if form.is_valid() and comp_formset.is_valid() and firm_form.is_valid():
            project = form.save()
            comp_formset.instance = project
            saved_comps = comp_formset.save()

            _save_modes(request.POST, saved_comps)

            firmware = firm_form.save(commit=False)
            firmware.project = project
            firmware.save()

            total_modes = sum(comp.modes.count() for comp in project.components.all())
            if total_modes == 0:
                messages.error(request, '❌ Saisissez les modes !')
                return redirect('project_create')

            n8n_result = _send_to_n8n(project)
            if n8n_result is not None:
                results = n8n_result
                source = 'n8n'
            else:
                calculator = EnergyCalculator(project)
                results = calculator.analyze()
                source = 'local'

            result = AnalysisResult(project=project)
            result.summary = results.get('summary')
            result.energy_profile = results.get('energy_profile')
            result.consumption_curve = results.get('consumption_curve')
            result.battery_recommendation = results.get('battery_recommendation')
            result.adapter_recommendation = results.get('adapter_recommendation')
            result.solar_report = results.get('solar_report')
            result.daily_energy_mah = results.get('daily_energy_mah', 0)
            result.daily_energy_mwh = results.get('daily_energy_mwh', 0)
            result.full_report = results
            result.status = 'completed'
            result.analysis_source = source
            result.save()

            project.status = 'completed'
            project.save()

            for w in results.get('warnings', []):
                messages.warning(request, w)

            if source == 'n8n':
                messages.success(request, '✅ Analyse n8n terminée !')
            else:
                messages.info(request, 'ℹ️ n8n non disponible. Calcul local utilisé.')

            return redirect('report', project_id=project.id)

    else:
        form = ProjectForm()
        comp_formset = ComponentFormSet(prefix='components')
        firm_form = FirmwareForm()

    return render(request, 'analyzer/project_form.html', {
        'form': form,
        'comp_formset': comp_formset,
        'firm_form': firm_form,
    })


def _send_to_n8n(project):
    try:
        components_data = []
        for comp in project.components.all():
            modes_data = []
            for mode in comp.modes.all():
                modes_data.append({
                    'name': mode.name,
                    'current_ma': mode.current_ma,
                    'duration_ms': mode.duration_ms,
                    'count': mode.count_per_cycle,
                })
            components_data.append({
                'name': comp.name,
                'category': comp.category,
                'voltage': comp.voltage,
                'modes': modes_data,
            })

        firmware = project.firmwares.first()
        firmware_data = {}
        if firmware:
            firmware_data = {'source_code': firmware.source_code or ''}

        payload = {
            'project_id': str(project.id),
            'project_name': project.name,
            'location': {
                'city': project.location_city,
                'country': project.location_country,
                'latitude': project.latitude,
                'longitude': project.longitude,
            },
            'components': components_data,
            'firmware': firmware_data,
        }

        response = requests.post(
            'http://localhost:5678/webhook/energy-analysis',
            json=payload,
            timeout=120,
        )

        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                if len(data) > 0:
                    if isinstance(data[0], dict) and 'json' in data[0]:
                        return data[0]['json']
                    return data[0]
                return None
            if isinstance(data, dict):
                return data
            return None
        return None

    except requests.exceptions.ConnectionError:
        return None
    except requests.exceptions.Timeout:
        return None
    except Exception as e:
        print(f"Erreur n8n: {e}")
        return None


def _save_modes(post_data, components):
    for ci, comp in enumerate(components):
        mi = 0
        while True:
            key = f'mode_name_{ci}_{mi}'
            if key not in post_data:
                break
            name = post_data.get(key, '').strip()
            current = post_data.get(f'mode_current_{ci}_{mi}', '').strip()
            duration = post_data.get(f'mode_duration_{ci}_{mi}', '').strip()
            count = post_data.get(f'mode_count_{ci}_{mi}', '1').strip()

            if name and current and duration:
                try:
                    ConsumptionMode.objects.create(
                        component=comp,
                        name=name,
                        current_ma=float(current),
                        duration_ms=float(duration),
                        count_per_cycle=int(count or 1),
                    )
                except (ValueError, TypeError):
                    pass
            mi += 1


def report(request, project_id):
    project = get_object_or_404(Project, id=project_id)

    result = None
    try:
        result = project.result
    except AnalysisResult.DoesNotExist:
        pass

    curve_json = '[]'
    states_json = '[]'

    if result and result.consumption_curve:
        curve_json = json.dumps(result.consumption_curve)
    if result and result.energy_profile:
        if 'states' in result.energy_profile:
            states_json = json.dumps(result.energy_profile['states'])

    return render(request, 'analyzer/report.html', {
        'project': project,
        'result': result,
        'curve_json': curve_json,
        'states_json': states_json,
    })


@login_required
def project_list(request):
    projects = Project.objects.all()
    return render(request, 'analyzer/project_list.html', {'projects': projects})


def register(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f"Compte créé avec succès ! Bienvenue {user.display_name}")
            return redirect('home')
    else:
        form = CustomUserCreationForm()
    return render(request, 'analyzer/auth/register.html', {'form': form})


@login_required
def profile(request):
    return render(request, 'analyzer/auth/profile.html')