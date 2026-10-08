from django.urls import path
from django.contrib.auth import views as auth_views

from . import views


urlpatterns = [
    # ==========================
    # Routes principales
    # ==========================

    path(
        '',
        views.home,
        name='home'
    ),

    path(
        'project/new/',
        views.wizard_project,
        name='project_create'
    ),

    path('workflow/', views.workflow_intro, name='workflow_intro'),
    path('wizard/project/', views.wizard_project, name='wizard_project'),
    path('wizard/<uuid:project_id>/project/', views.wizard_project, name='wizard_project_edit'),
    path('wizard/<uuid:project_id>/mcu/', views.wizard_mcu, name='wizard_mcu'),
    path('wizard/<uuid:project_id>/peripherals/', views.wizard_peripherals, name='wizard_peripherals'),
    path('wizard/<uuid:project_id>/actuators/', views.wizard_actuators, name='wizard_actuators'),
    path('wizard/<uuid:project_id>/firmware/', views.wizard_firmware, name='wizard_firmware'),
    path('wizard/<uuid:project_id>/energy/', views.wizard_energy, name='wizard_energy'),
    path('wizard/<uuid:project_id>/review/', views.wizard_review, name='wizard_review'),
    path('project/legacy-create/', views.project_create, name='project_analyze'),

    path(
        'projects/',
        views.project_list,
        name='project_list'
    ),

    path(
        'report/<uuid:project_id>/',
        views.report,
        name='report'
    ),

    # ==========================
    # Authentification
    # ==========================

    path(
        'login/',
        auth_views.LoginView.as_view(
            template_name='analyzer/auth/login.html'
        ),
        name='login'
    ),

    path(
        'logout/',
        auth_views.LogoutView.as_view(),
        name='logout'
    ),

    path(
        'register/',
        views.register,
        name='register'
    ),

    path(
        'profile/',
        views.profile,
        name='profile'
    ),

    # ==========================
    # Réinitialisation avec code à 6 chiffres
    # ==========================

    path(
        'password-reset/',
        views.forgot_password,
        name='forgot_password'
    ),

    path(
        'verify-reset-code/',
        views.verify_reset_code,
        name='verify_reset_code'
    ),

    path(
        'new-password/',
        views.new_password,
        name='new_password'
    ),
]
