from django.db.models import Q
from django.contrib.auth import get_user_model
from .models import Task, TaskUserNotification

User = get_user_model()


def get_task_interested_users(task):
    """
    Возвращает список пользователей, заинтересованных в данной задаче:
    1. Исполнитель (assigned_to)
    2. Дополнительные исполнители (co_assignees)
    3. Создатель задачи (created_by)
    4. Руководители и администраторы подразделения задачи
    5. Глобальные администраторы и суперпользователи
    """
    user_ids = set()
    if task.assigned_to_id:
        user_ids.add(task.assigned_to_id)
    if task.created_by_id:
        user_ids.add(task.created_by_id)

    for u_id in task.co_assignees.values_list('id', flat=True):
        user_ids.add(u_id)

    if task.department_id:
        dept_supervisors = User.objects.filter(
            department_id=task.department_id
        ).filter(
            Q(is_department_head=True) | Q(is_administrator=True) | Q(is_staff=True)
        ).values_list('id', flat=True)
        user_ids.update(dept_supervisors)

    global_admins = User.objects.filter(
        Q(is_superuser=True) | (Q(is_administrator=True) & Q(department__isnull=True))
    ).values_list('id', flat=True)
    user_ids.update(global_admins)

    return User.objects.filter(id__in=user_ids)


def notify_task_changed(task, actor=None, change_detail=None):
    """
    Уведомляет заинтересованных пользователей об изменении или создании задачи.

    ПАРАМЕТР `actor`:
    Это пользователь, который совершил ТЕКУЩЕЕ действие прямо сейчас
    (написал комментарий в чат, сменил статус, отредактировал задачу и т.д.).

    ЛОГИКА УВЕДОМЛЕНИЙ:
    1. Для инициатора текущего действия (`actor`):
       Задача помечается как ПРОЧИТАННАЯ (`is_read=True`), чтобы автор своего
       же комментария или действия не получал уведомление при обновлении страницы.
    2. Для ВСЕХ ОСТАЛЬНЫХ участников (включая создателя задачи `created_by`,
       если действие совершил кто-то другой, например исполнитель):
       Задача помечается как НЕПРОЧИТАННАЯ (`is_read=False`), выводя плашку и яркую заливку.
    """
    if change_detail:
        task.last_change_detail = change_detail
        task.save(update_fields=['last_change_detail', 'updated_at'])

    interested_users = list(get_task_interested_users(task))
    actor_id = actor.id if actor and getattr(actor, 'is_authenticated', False) else None

    for u in interested_users:
        if actor_id and u.id == actor_id:
            # Инициатор текущего действия не должен уведомляться о собственном действии
            TaskUserNotification.objects.update_or_create(
                task=task,
                user=u,
                defaults={'is_read': True}
            )
        else:
            # Для всех других участников (в т.ч. создателя, если действие совершил исполнитель)
            TaskUserNotification.objects.update_or_create(
                task=task,
                user=u,
                defaults={'is_read': False}
            )

    if actor_id and not any(u.id == actor_id for u in interested_users):
        TaskUserNotification.objects.update_or_create(
            task=task,
            user=actor,
            defaults={'is_read': True}
        )

    # Синхронизация legacy-полей модели Task для обратной совместимости
    if actor_id and task.assigned_to_id and actor_id != task.assigned_to_id:
        task.is_read_by_assignee = False
    if actor_id:
        task.status_changed_for_head = True
    task.save(update_fields=['is_read_by_assignee', 'status_changed_for_head'])


def mark_task_read_for_user(task, user):
    """
    Отмечает конкретную задачу как прочитанную для указанного пользователя.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return
    TaskUserNotification.objects.filter(task=task, user=user).update(is_read=True)


def mark_all_tasks_read_for_user(user):
    """
    Сбрасывает все уведомления для конкретного пользователя.
    Не затрагивает уведомления и прочтения других пользователей!
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return
    TaskUserNotification.objects.filter(user=user, is_read=False).update(is_read=True)
    # Обратная совместимость для legacy-тестов
    Task.objects.filter(assigned_to=user, is_read_by_assignee=False).update(is_read_by_assignee=True)


def get_user_unread_tasks_count(user):
    """
    Возвращает количество активных непрочитанных задач для пользователя.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return 0
    return TaskUserNotification.objects.filter(user=user, is_read=False).count()
