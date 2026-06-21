from django.shortcuts import (
    render,
    redirect,
    get_object_or_404,
)
from django.contrib import messages
from .models import Project, AnalysisResult
from .forms import (
    ProjectForm,
    ComponentFormSet,
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
            request.POST,
            request.FILES,
        )
        firm_form = FirmwareForm(
            request.POST,
            request.FILES,
        )

        if (form.is_valid()
                and comp_formset.is_valid()
                and firm_form.is_valid()):

            project = form.save()

            comp_formset.instance = project
            comp_formset.save()

            firmware = firm_form.save(
                commit=False
            )
            firmware.project = project
            firmware.save()

            calculator = EnergyCalculator(
                project
            )
            results = calculator.analyze()

            result = AnalysisResult(
                project=project
            )
            result.energy_profile = (
                results['energy_profile']
            )
            result.consumption_curve = (
                results['consumption_curve']
            )
            result.daily_energy_mah = (
                results['daily_energy_mah']
            )
            result.daily_energy_mwh = (
                results['daily_energy_mwh']
            )
            result.battery_recommendation = (
                results['battery_recommendation']
            )
            result.panel_recommendation = (
                results['panel_recommendation']
            )
            result.solar_report = (
                results['solar_report']
            )
            result.status = 'completed'
            result.save()

            project.status = 'completed'
            project.save()

            messages.success(
                request,
                'Analyse terminee !'
            )
            return redirect(
                'report',
                project_id=project.id,
            )
    else:
        form = ProjectForm()
        comp_formset = ComponentFormSet()
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


def report(request, project_id):
    project = get_object_or_404(
        Project,
        id=project_id,
    )

    result = None
    try:
        result = project.result
    except AnalysisResult.DoesNotExist:
        pass

    curve_json = '[]'
    states_json = '[]'

    if result and result.consumption_curve:
        curve_json = json.dumps(
            result.consumption_curve
        )

    if result and result.energy_profile:
        if 'states' in result.energy_profile:
            states_json = json.dumps(
                result.energy_profile['states']
            )

    return render(
        request,
        'analyzer/report.html',
        {
            'project': project,
            'result': result,
            'curve_json': curve_json,
            'states_json': states_json,
        },
    )


def project_list(request):
    projects = Project.objects.all()
    return render(
        request,
        'analyzer/project_list.html',
        {'projects': projects},
    )