from django.shortcuts import (
    render, redirect, get_object_or_404,
)
from django.contrib import messages
from .models import (
    Project, ConsumptionMode,
    AnalysisResult,
)
from .forms import (
    ProjectForm, ComponentFormSet,
    FirmwareForm,
)
from .calculator import EnergyCalculator
import json


def home(request):
    projects = Project.objects.all()[:10]
    return render(
        request,
        'analyzer/home.html',
        {'projects': projects},
    )


def project_create(request):
    if request.method == 'POST':
        form = ProjectForm(request.POST)
        comp_formset = ComponentFormSet(
            request.POST, request.FILES,
            prefix='components',
        )
        firm_form = FirmwareForm(
            request.POST, request.FILES,
        )

        if (form.is_valid()
                and comp_formset.is_valid()
                and firm_form.is_valid()):

            project = form.save()

            comp_formset.instance = project
            saved_comps = comp_formset.save()

            # Sauvegarder les modes
            _save_modes(
                request.POST, saved_comps
            )

            firmware = firm_form.save(
                commit=False
            )
            firmware.project = project
            firmware.save()

            # Verifier les modes
            total_modes = 0
            for comp in project.components.all():
                total_modes += comp.modes.count()

            if total_modes == 0:
                messages.error(
                    request,
                    '❌ Aucun mode saisi ! '
                    'Vous devez saisir les modes '
                    'de consommation depuis la '
                    'datasheet de vos composants.'
                )
                return redirect(
                    'project_create'
                )

            # Calcul
            calculator = EnergyCalculator(
                project
            )
            results = calculator.analyze()

            # Sauvegarder
            result = AnalysisResult(
                project=project
            )
            result.summary = results.get(
                'summary'
            )
            result.energy_profile = results.get(
                'energy_profile'
            )
            result.consumption_curve = results.get(
                'consumption_curve'
            )
            result.battery_recommendation = (
                results.get(
                    'battery_recommendation'
                )
            )
            result.adapter_recommendation = (
                results.get(
                    'adapter_recommendation'
                )
            )
            result.solar_report = results.get(
                'solar_report'
            )
            result.daily_energy_mah = results.get(
                'daily_energy_mah'
            )
            result.daily_energy_mwh = results.get(
                'daily_energy_mwh'
            )
            result.full_report = results
            result.status = 'completed'
            result.save()

            project.status = 'completed'
            project.save()

            for w in results.get('warnings', []):
                messages.warning(request, w)

            messages.success(
                request,
                '✅ Analyse terminee !'
            )
            return redirect(
                'report',
                project_id=project.id,
            )
    else:
        form = ProjectForm()
        comp_formset = ComponentFormSet(
            prefix='components',
        )
        firm_form = FirmwareForm()

    return render(
        request,
        'analyzer/project_form.html',
        {
            'form': form,
            'comp_formset': comp_formset,
            'firm_form': firm_form,
        },
    )


def _save_modes(post_data, components):
    """Sauvegarde les modes dynamiques"""
    for comp_idx, comp in enumerate(components):
        mode_idx = 0
        while True:
            key_name = (
                f'mode_name_{comp_idx}_{mode_idx}'
            )
            if key_name not in post_data:
                break

            name = post_data.get(
                key_name, ''
            ).strip()
            current = post_data.get(
                f'mode_current_{comp_idx}'
                f'_{mode_idx}', ''
            ).strip()
            duration = post_data.get(
                f'mode_duration_{comp_idx}'
                f'_{mode_idx}', ''
            ).strip()
            count = post_data.get(
                f'mode_count_{comp_idx}'
                f'_{mode_idx}', '1'
            ).strip()

            if name and current and duration:
                try:
                    ConsumptionMode.objects.create(
                        component=comp,
                        name=name,
                        current_ma=float(current),
                        duration_ms=float(duration),
                        count_per_cycle=int(
                            count or 1
                        ),
                    )
                except (ValueError, TypeError):
                    pass

            mode_idx += 1


def report(request, project_id):
    project = get_object_or_404(
        Project, id=project_id,
    )

    result = None
    try:
        result = project.result
    except AnalysisResult.DoesNotExist:
        pass

    curve_json = '[]'
    states_json = '[]'
    summary_json = '{}'

    if result and result.consumption_curve:
        curve_json = json.dumps(
            result.consumption_curve
        )
    if result and result.energy_profile:
        if 'states' in result.energy_profile:
            states_json = json.dumps(
                result.energy_profile['states']
            )
    if result and result.summary:
        summary_json = json.dumps(
            result.summary
        )

    return render(
        request,
        'analyzer/report.html',
        {
            'project': project,
            'result': result,
            'curve_json': curve_json,
            'states_json': states_json,
            'summary_json': summary_json,
        },
    )


def project_list(request):
    projects = Project.objects.all()
    return render(
        request,
        'analyzer/project_list.html',
        {'projects': projects},
    )