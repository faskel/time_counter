from .models import TaskUserNotification


def planner_notifications(request):
    """
    Контекстный процессор для индикатора уведомлений около кнопки «Планировщик».
    - Персональные уведомления для каждого пользователя (и сотрудников, и руководителей).
    """
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return {
            'planner_unread_count': 0,
            'head_changed_tasks_count': 0,
            'total_planner_notifications': 0,
            'has_planner_notifications': False,
            'user_unread_tasks_count': 0,
        }

    user = request.user
    user_unread_count = TaskUserNotification.objects.filter(user=user, is_read=False).count()

    return {
        'planner_unread_count': user_unread_count,
        'head_changed_tasks_count': user_unread_count,
        'total_planner_notifications': user_unread_count,
        'has_planner_notifications': user_unread_count > 0,
        'user_unread_tasks_count': user_unread_count,
    }
