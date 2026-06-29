from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Routes principales
    path('', views.home, name='home'),
    path('project/new/', views.project_create, name='project_create'),
    path('projects/', views.project_list, name='project_list'),
    path('report/<uuid:project_id>/', views.report, name='report'),

    # Authentification
    path('login/', auth_views.LoginView.as_view(
            template_name='analyzer/auth/login.html'), 
            name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('register/', views.register, name='register'),
    path('profile/', views.profile, name='profile'),
]