# accounts/urls.py

from django.urls import path
from . import views



urlpatterns = [
    path('', views.show_works_day, name='show_works_day'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('workdays/', views.show_works_day, name='show_works_day'),
    # Убедитесь, что URL для update_work_times существует
    path('update-work-times/', views.update_work_times, name='update_work_times'),
    path('import_data/', views.import_data, name='import_data'),
    # path('get-day-data/<int:day_id>/', views.get_day_data, name='get_day_data'), # Этот может не понадобиться с новой логикой
]