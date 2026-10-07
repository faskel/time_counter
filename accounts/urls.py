# accounts/urls.py

from django.urls import path
from django.conf.urls.static import static
from . import views


urlpatterns = [
    path('', views.show_works_day, name='show_works_day'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('workdays/', views.show_works_day, name='show_works_day'),
    path('set-vacation/', views.set_vacation, name='set_vacation'),

    path('update-work-times/', views.update_work_times, name='update_work_times'),
    path('calculate_exit_time/', views.calculate_exit_time_api, name='calculate_exit_time'),
    path('import_data/', views.import_data, name='import_data'),
    # path('get_suz_link/', views.get_suz_link, name='get_suz_link'),
    path('save-all-changes/', views.save_all_changes, name='save_all_changes'),
    path('save_theme_settings/', views.save_theme_settings, name='save_theme_settings'),
    path('transfer-time/', views.transfer_time, name='transfer_time'),
    path('delete-transfer/', views.delete_transfer, name='delete_transfer'),
    path('add-mk-slot/', views.add_mk_slot, name='add_mk_slot'),
    path('department/', views.department_stats, name='department_stats'),
    path('time-manager/', views.time_manager_view, name='time_manager'),
    path('time-manager/edit/<int:task_id>/', views.edit_task, name='edit_task'),
    path('time-manager/comment/<int:task_id>/', views.add_task_comment, name='add_task_comment'),
    path('time-manager/comment/edit/<int:comment_id>/', views.edit_task_comment, name='edit_task_comment'),
    path('time-manager/comment/delete/<int:comment_id>/', views.delete_task_comment, name='delete_task_comment'),
    path('time-manager/update-status/<int:task_id>/', views.update_task_status, name='update_task_status'),
    path('time-manager/clear-notifications/', views.clear_head_notifications, name='clear_head_notifications'),
    path('time-manager/delete/<int:task_id>/', views.delete_task, name='delete_task'),
    path('time-manager/approve-co-assignee/<int:task_id>/', views.approve_co_assignee, name='approve_co_assignee'),
    path('time-manager/history/<int:task_id>/', views.get_task_history, name='get_task_history'),
    path('time-manager/task/<int:task_id>/', views.get_task_details, name='get_task_details'),
    path('time-manager/task/<int:task_id>/comments/', views.get_task_comments_updates, name='get_task_comments_updates'),
    path('time-manager/comments/counts/', views.get_tasks_comments_counts, name='get_tasks_comments_counts'),
    path('time-manager/tasks/search/', views.search_tasks_for_dependencies, name='search_tasks_for_dependencies'),
]




