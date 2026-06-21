from django.urls import path
from . import views

urlpatterns = [
    path(
        '', views.home, name='home',
    ),
    path(
        'project/new/',
        views.project_create,
        name='project_create',
    ),
    path(
        'projects/',
        views.project_list,
        name='project_list',
    ),
    path(
        'report/<uuid:project_id>/',
        views.report,
        name='report',
    ),
]