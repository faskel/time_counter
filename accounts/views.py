# accounts/views.py
import requests
import locale
import json
import calendar
import csv
import chardet
import os
import urllib.parse

from datetime import datetime, timedelta, date
from itertools import zip_longest
from django.db import transaction
from django.db.models import Sum, Q, Case, When, Value, IntegerField, Count, Max, Exists, OuterRef
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate, get_user_model
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.conf import settings

from collections import defaultdict
from .forms import UserRegisterForm, UserLoginForm
from .models import (
    WorkDay, Action, MonthTransfer, Birthday, Holiday, Department,
    TodayPhrase, Task, TaskComment, TaskPriority, TaskTopic,
    TaskCoAssigneeApproval, TaskHistory, TaskDependency, TaskUserNotification
)
# pyrefly: ignore [missing-import]
from .task_notifications import (
    notify_task_changed, mark_all_tasks_read_for_user,
    get_user_unread_tasks_count, mark_task_read_for_user
)

try:
    locale.setlocale(locale.LC_ALL, 'ru_RU.UTF-8')  # Для Linux/macOS
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, 'Russian_Russia.1251')  # Для Windows (или 'ru_RU')
    except locale.Error:
        print("Не удалось установить русскую локаль для strftime.")

User = get_user_model()


DEFAULT_PRIORITIES = [
    (0, "Критический", "#ef4444"),
    (1, "Высокий", "#f97316"),
    (2, "Средний", "#eab308"),
    (3, "Низкий", "#3b82f6"),
    (4, "Минимальный", "#6b7280"),
]


def is_admin_user(user):
    """Проверяет, является ли пользователь администратором или начальником отдела."""
    if not user or not user.is_authenticated:
        return False
    return bool(getattr(user, 'is_administrator', False) or getattr(user, 'is_department_head', False) or user.is_staff or user.is_superuser)


def is_head_user(user):
    """Проверяет, является ли пользователь начальником отдела."""
    if not user or not user.is_authenticated:
        return False
    return bool(getattr(user, 'is_department_head', False) or user.is_superuser)


def user_can_access_task(user, task):
    """
    Проверяет, имеет ли пользователь доступ к просмотру/управлению задачей
    с учетом разделения по отделам.
    """
    if not user or not user.is_authenticated:
        return False
    is_admin = is_admin_user(user)
    if is_admin:
        if user.department:
            return (task.department == user.department) or (task.department is None and (task.assigned_to == user or task.created_by == user))
        return True
    is_involved = (task.created_by == user or task.assigned_to == user or task.co_assignees.filter(pk=user.pk).exists())
    if not is_involved:
        return False
    if user.department and task.department:
        return task.department == user.department
    return True


def seed_task_priorities_if_empty():
    """Заполняет стандартные приоритеты задач, если они отсутствуют."""
    if not TaskPriority.objects.exists():
        TaskPriority.objects.bulk_create([
            TaskPriority(code=code, name=name, color_code=color)
            for code, name, color in DEFAULT_PRIORITIES
        ])


DEFAULT_TASK_TOPICS = [
    "Разработка",
    "Документация",
    "Тестирование",
    "Совещание",
    "Поддержка",
    "Разное",
]


def seed_task_topics_if_empty():
    """Заполняет стандартные темы задач, если они отсутствуют."""
    if not TaskTopic.objects.exists():
        TaskTopic.objects.bulk_create([
            TaskTopic(name=name) for name in DEFAULT_TASK_TOPICS
        ])


def log_task_history(task, actor, action_type, description):
    """Фиксирует запись в истории изменений задачи."""
    TaskHistory.objects.create(
        task=task,
        actor=actor,
        action_type=action_type,
        description=description
    )


def validate_dependencies_no_cycle(task_id, new_dependencies):
    """
    Проверяет список зависимостей на отсутствие циклов (Deadlock) и ссылок на себя.
    new_dependencies: list of dicts with 'depends_on_id'
    """
    if not new_dependencies:
        return

    target_ids = []
    for dep in new_dependencies:
        target_id = dep.get('depends_on_id')
        if not target_id:
            continue
        try:
            target_id = int(target_id)
        except (ValueError, TypeError):
            continue

        if task_id and target_id == task_id:
            raise ValueError("Невозможно создать связь: задача не может зависеть от самой себя.")

        target_ids.append(target_id)

    # Если задача новая (task_id is None), у неё нет предшествующих последователей,
    # поэтому циклов возникнуть не может (кроме self-link).
    if not task_id:
        return

    # Загружаем существующие связи для обхода графа (исключая старые связи самой task_id)
    existing_deps = TaskDependency.objects.exclude(task_id=task_id).values_list('task_id', 'depends_on_id')
    graph = defaultdict(set)
    for t_id, dep_on_id in existing_deps:
        graph[t_id].add(dep_on_id)

    # DFS: проверяем, может ли target_id достичь task_id (т.е. target_id уже прямо или косвенно зависит от task_id)
    for start_node in target_ids:
        visited = set()
        stack = [start_node]
        while stack:
            curr = stack.pop()
            if curr == task_id:
                raise ValueError("Невозможно создать связь: возникает циклическая зависимость между задачами.")
            if curr not in visited:
                visited.add(curr)
                for neighbor in graph.get(curr, []):
                    if neighbor not in visited:
                        stack.append(neighbor)




class MockQuerySet:
    """Имитирует функциональность QuerySet (filter, order_by, first) для TempAction."""

    def __init__(self, actions):
        self._actions = list(actions)

    def order_by(self, *args):
        # Сортировка по полю 'order', как в оригинальной функции расчета.
        if 'order' in args:
            sorted_actions = sorted(self._actions, key=lambda x: x.order)
            return MockQuerySet(sorted_actions)
        return self

    def __iter__(self):
        return iter(self._actions)

    def first(self):
        return self._actions[0] if self._actions else None


class MockWorkDay:
    """Имитирует объект WorkDay, чтобы 'подсунуть' ему временные действия."""

    def __init__(self, original_workday, actions_list):
        self.id = getattr(original_workday, 'id', None)
        self.date_stamp = original_workday.date_stamp
        self.type = original_workday.type
        self.user = original_workday.user
        self._actions_list = actions_list

    @property
    def actions(self):
        return self

    def order_by(self, *args):
        return MockQuerySet(self._actions_list).order_by(*args)

    def all(self):
        return MockQuerySet(self._actions_list)

    def filter(self, **kwargs):
        status_gate = kwargs.get('status_gate')
        filtered_actions = [a for a in self._actions_list if a.status_gate == status_gate]
        return MockQuerySet(filtered_actions)


MONTH_NAMES_RU = {
    'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4, 'мая': 5, 'июня': 6,
    'июля': 7, 'августа': 8, 'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12
}

DEFAULT_TODAY_PHRASES = [
    "Сегодня",
    "Today",
    "Aujourd'hui",
    "Hoy",
    "Heute",
    "Oggi",
    "Hoje",
    "Dzisiaj",
    "Vandaag",
    "Dnes",
]


def seed_today_phrases_if_empty():
    if not TodayPhrase.objects.exists():
        TodayPhrase.objects.bulk_create([
            TodayPhrase(phrase=p) for p in DEFAULT_TODAY_PHRASES
        ])


def get_random_today_phrase(user=None):
    if user and user.is_authenticated and user.tracker and user.tracker != 'Сегодня':
        return user.tracker
    try:
        seed_today_phrases_if_empty()
        phrases = list(TodayPhrase.objects.filter(is_active=True).values_list('phrase', flat=True))
        if phrases:
            import random
            return random.choice(phrases)
    except Exception:
        pass
    return "Сегодня"



def parse_birthday_line(line):
    """Парсит одну строку из файла др.txt."""
    line = line.strip()
    if not line or line.startswith('Дата'):
        return None
    # Заменяем все разделители (табы/множественные пробелы) на один пробел и разбиваем
    parts = line.replace('\t', ' ').split()

    # [span_0](start_span)Файл содержит ошибку 'опреля' вместо 'апреля'[span_0](end_span), которую нужно учесть
    month_name = parts[1].lower() if len(parts) > 1 else ''
    if month_name == 'опреля':
        month_name = 'апреля'

    if len(parts) < 4 or month_name not in MONTH_NAMES_RU:
        return None

    try:
        day = int(parts[0])
        month = MONTH_NAMES_RU.get(month_name)

        # Индекс, с которого начинается ФИО (учитываем, что год может отсутствовать)
        surname_index = 2
        year = 2000
        try:
            parsed_year = int(parts[2])
            if 1900 <= parsed_year <= 2100:
                year = parsed_year
                surname_index = 3
        except ValueError:
            pass

        fio_parts = parts[surname_index:surname_index + 3]
        full_name = " ".join(fio_parts).strip()

        if not full_name:
            return None

        return {
            'day': day,
            'month': month,
            'year': year,
            'full_name': full_name,
        }
    except Exception:
        return None


def seed_birthdays_if_empty():
    if Birthday.objects.exists():
        return
    file_path = os.path.join(settings.BASE_DIR, 'static', 'text', 'HB list.txt')
    if not os.path.exists(file_path):
        return
    try:
        with open(file_path, 'r', encoding='cp1251') as f:
            file_content = f.read()
    except Exception:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                file_content = f.read()
        except Exception:
            return

    birthdays_to_create = []
    for line in file_content.strip().split('\n'):
        data = parse_birthday_line(line)
        if data and data.get('month') and data.get('day') and data.get('full_name'):
            b_year = data.get('year', 2000)
            try:
                b_date = date(b_year, data['month'], data['day'])
                birthdays_to_create.append(Birthday(date=b_date, full_name=data['full_name']))
            except ValueError:
                pass
    if birthdays_to_create:
        Birthday.objects.bulk_create(birthdays_to_create)


def get_birthdays_for_month(target_month, target_day=None):
    """
    Получает данные о днях рождения из модели Birthday.
    При пустой таблице автоматически первично заполняет данные из HB list.txt.
    """
    seed_birthdays_if_empty()
    birthdays = []
    qs = Birthday.objects.filter(date__month=target_month).order_by('date__day')
    for item in qs:
        day = item.date.day
        is_today = (target_day is not None and day == target_day)
        dropdown_id = f"bday-dropdown-{day}-{item.full_name.replace(' ', '-')[:15]}"
        birthdays.append({
            'day': day,
            'month': target_month,
            'name': item.full_name,
            'is_today': is_today,
            'dropdown_id': dropdown_id
        })

    return birthdays


@login_required
@csrf_exempt
@require_POST
def set_vacation(request):
    """
    Принимает диапазон дат и переводит WorkDay в режим 'Отпуск' (VL)
    """
    try:
        data = json.loads(request.body)
        start_date_str = data.get('start_date')
        end_date_str = data.get('end_date')
        day_type = data.get('day_type', 'VL')
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()

        if start_date > end_date:
            return JsonResponse({'success': False, 'message': 'Начальная дата больше конечной'})

        user = request.user
        target_user_id = data.get('user_id')
        if target_user_id and (is_admin_user(user) or user.is_department_head):
            target_user = get_object_or_404(User, pk=target_user_id)
        else:
            target_user = user

        current_date = start_date
        while current_date <= end_date:
            wd, created = WorkDay.objects.get_or_create(
                user=target_user,
                date_stamp=current_date,
                defaults={'type': day_type} # Используем выбранный тип
            )
            wd.type = day_type
            wd.actions.all().delete()
            wd.save()

            current_date += timedelta(days=1)

        return JsonResponse({'success': True, 'message': 'Отпуск установлен'})

    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


@require_POST
@csrf_exempt
@login_required
def save_theme_settings(request):
    """Сохраняет пользовательскую тему оформления (light/dark) в сессии."""
    try:
        data = json.loads(request.body)
        theme_mode = data.get('theme_mode')

        if theme_mode in ['light', 'dark']:
            request.session['theme_mode'] = theme_mode
            try:
                request.session.modified = True
                request.session.save()
            except AttributeError:
                pass
            return JsonResponse({'success': True, 'theme_mode': theme_mode, 'message': 'Тема успешно сохранена.'})

        is_reset = data.get('reset', False)
        if is_reset:
            request.session.pop('theme_mode', None)
            try:
                request.session.modified = True
                request.session.save()
            except AttributeError:
                pass
            return JsonResponse({'success': True, 'message': 'Настройки темы сброшены.'})

        return JsonResponse({'success': False, 'message': 'Неверный параметр темы.'}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Неверный формат JSON.'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Произошла ошибка: {str(e)}'}, status=500)


@login_required
@require_POST
def transfer_time(request):
    """
    Переносит или добавляет указанное количество времени.
    Если type == 'addition', время добавляется из "неоткуда" без списания с другого месяца.
    """
    try:
        data = json.loads(request.body)
        transfer_type = data.get('type', 'transfer')
        to_year = int(data.get('to_year')) if data.get('to_year') else None
        to_month = int(data.get('to_month')) if data.get('to_month') else None
        time_str = data.get('time_amount')
        description = data.get('description', '').strip()

        if transfer_type == 'addition':
            if not to_year or not to_month or not time_str:
                return JsonResponse({'success': False, 'message': 'Укажите все параметры добавления'}, status=400)
            from_year = None
            from_month = None
        else:
            from_year = int(data.get('from_year')) if data.get('from_year') else None
            from_month = int(data.get('from_month')) if data.get('from_month') else None
            if not from_year or not from_month or not to_year or not to_month or not time_str:
                return JsonResponse({'success': False, 'message': 'Укажите все параметры переноса'}, status=400)

            # Проверка баланса месяца списания
            from_balance_td = get_user_month_balance(request.user, from_year, from_month)
            if from_balance_td < timedelta(0):
                balance_str = timedelta_to_hms_str(from_balance_td)
                return JsonResponse({
                    'success': False,
                    'message': f'Перенос заблокирован: баланс за {from_month:02d}.{from_year} отрицательный ({balance_str}). Списание из месяца с отрицательным балансом запрещено.'
                }, status=400)

        parts = time_str.split(':')
        hours = int(parts[0])
        minutes = int(parts[1]) if len(parts) > 1 else 0
        total_seconds = (hours * 3600) + (minutes * 60)

        if total_seconds <= 0:
            return JsonResponse({'success': False, 'message': 'Время должно быть больше 0'}, status=400)

        MonthTransfer.objects.create(
            user=request.user,
            from_year=from_year,
            from_month=from_month,
            to_year=to_year,
            to_month=to_month,
            amount_seconds=total_seconds,
            description=description
        )

        if transfer_type == 'addition':
            desc_text = f" ({description})" if description else ""
            msg = f'Добавлено {hours:02d}:{minutes:02d} в {to_month:02d}.{to_year}{desc_text}'
        else:
            msg = f'Перенесено {hours:02d}:{minutes:02d} из {from_month:02d}.{from_year} в {to_month:02d}.{to_year}'

        return JsonResponse({'success': True, 'message': msg})

    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Ошибка: {str(e)}'}, status=500)


@login_required
@require_POST
def delete_transfer(request):
    """
    Удаляет запись переноса или добавления времени.
    """
    try:
        data = json.loads(request.body)
        transfer_id = data.get('transfer_id')
        transfer = get_object_or_404(MonthTransfer, id=transfer_id, user=request.user)
        transfer.delete()
        return JsonResponse({'success': True, 'message': 'Запись успешно удалена'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Ошибка при удалении: {str(e)}'}, status=500)


def register_view(request):
    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('show_works_day')
    else:
        form = UserRegisterForm()
    return render(request, 'accounts/register.html', {'form': form})


def login_view(request):
    if request.method == 'POST':
        form = UserLoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('show_works_day')
    else:
        form = UserLoginForm()
    return render(request, 'accounts/login.html', {'form': form})


@login_required
def logout_view(request):
    logout(request)
    return redirect('login')


# --- Вспомогательная функция для расчета времени ---

def timedelta_to_hms_str(td):
    """Преобразует timedelta в строку HH:MM:SS."""
    total_seconds = int(td.total_seconds())
    sign = "-" if total_seconds < 0 else ""
    total_seconds = abs(total_seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{sign}{hours:02}:{minutes:02}:{seconds:02}"


def calculate_day_balance(workday_total_duration, day_type, user_account_type):
    """
    Рассчитывает "Баланс за день" согласно правилам.
    Возвращает timedelta и флаг is_negative.
    """

    if day_type in ['WD', 'HD', 'VL']: return timedelta(0), False

    required_work_duration = get_required_work_duration(user_account_type)
    # print('required_work_duration:', required_work_duration)

    standard_day_target = timedelta(hours=8)
    short_day_target = timedelta(hours=7)
    unpaid_break_threshold = timedelta(minutes=45)  # 45 минут неоплачиваемого перерыва, обед

    target_duration = timedelta(0)

    if day_type == 'ND':  # Обычный день
        target_duration = standard_day_target
        if workday_total_duration < unpaid_break_threshold and workday_total_duration.total_seconds() > 0:
            target_duration = standard_day_target + unpaid_break_threshold
    elif day_type == 'SMD':  # Короткий день
        target_duration = short_day_target
        if workday_total_duration < unpaid_break_threshold and workday_total_duration.total_seconds() > 0:
            target_duration = short_day_target + unpaid_break_threshold
    elif day_type in ['WD', 'HD', 'VL','ED','OT','MK','KMD']:  # Выходной, Праздник, Отпуск - баланс всегда 0
        return timedelta(0), False

    balance = workday_total_duration - required_work_duration
    is_negative = balance < timedelta(0)
    if day_type == 'SMD':
        # print('workday_total_duration: ', workday_total_duration)
        # print('required_work_duration: ', required_work_duration)
        balance += timedelta(hours=1)
        # print('balance: ', balance)

    # print('balance', balance,'workday_total_duration', workday_total_duration,'required_work_duration', required_work_duration)
    return balance, is_negative


# --- Вспомогательная функция для получения требуемого времени от типа пользователя ---
def get_required_work_duration(account_type):
    if account_type == 'full_day':
        return timedelta(hours=8)
    elif account_type == 'shortened':
        return timedelta(hours=7)
    elif account_type == 'student':
        return timedelta(hours=4)
    return timedelta(hours=8)


# --- Вспомогательная функция для определения диапазона недели ---
def get_week_range(date):
    start_of_week = date - timedelta(days=date.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    return start_of_week, end_of_week


def calculate_total_time_for_workday(workday):
    """
    Рассчитывает общее время на территории за рабочий день.
    Учитывает пары Вход-Выход. Игнорирует любые выходы до первого входа.
    """
    actions = list(workday.actions.order_by('time_stamp', 'order'))

    first_entry = next((a for a in actions if a.status_gate == 'EG'), None)
    if not first_entry:
        return timedelta(0)

    valid_actions = [a for a in actions if a.time_stamp >= first_entry.time_stamp]

    total_duration = timedelta()
    outside_time_delta = timedelta()
    last_entry_time = None

    entry_time = []
    exit_time = []

    half_day_target = timedelta(hours=4)
    six_day_target = timedelta(hours=6)
    unpaid_mini_break_threshold = timedelta(hours=0, minutes=30)
    unpaid_break_threshold = timedelta(hours=0, minutes=45)

    for action in valid_actions:
        if action.status_gate == 'EG':
            last_entry_time = action.time_stamp
            entry_time.append(action.time_stamp)
        elif action.status_gate == 'OG':
            if last_entry_time and action.time_stamp > last_entry_time:
                exit_time.append(action.time_stamp)
                total_duration += (action.time_stamp - last_entry_time)
                last_entry_time = None

    if len(entry_time) > 1 and len(exit_time) > 0:
        for i in range(min(len(exit_time), len(entry_time) - 1)):
            if i + 1 < len(entry_time) and entry_time[i + 1] > exit_time[i]:
                outside_time_delta += (entry_time[i + 1] - exit_time[i])

    if total_duration < half_day_target:
        return total_duration
    elif half_day_target < total_duration < six_day_target:
        if outside_time_delta > unpaid_mini_break_threshold:
            return total_duration
        else:
            time_lunch = unpaid_break_threshold - outside_time_delta
            total_duration -= time_lunch
            return total_duration
    elif six_day_target < total_duration:
        if outside_time_delta > unpaid_break_threshold:
            return total_duration
        else:
            time_lunch = unpaid_break_threshold - outside_time_delta
            total_duration -= time_lunch
            return total_duration

    return total_duration


def get_user_month_balance(user, year, month):
    """
    Вычисляет итоговый баланс времени для пользователя за указанный месяц и год.
    """
    days_in_month = calendar.monthrange(year, month)[1]
    month_start = date(year, month, 1)
    month_end = date(year, month, days_in_month)

    workdays = WorkDay.objects.filter(
        user=user,
        date_stamp__gte=month_start,
        date_stamp__lte=month_end
    )

    month_balance_td = timedelta(0)
    for wd in workdays:
        wd_duration = calculate_total_time_for_workday(wd)
        day_bal, _ = calculate_day_balance(wd_duration, wd.type, user.account_type)
        month_balance_td += day_bal

    outgoing = MonthTransfer.objects.filter(
        user=user,
        from_year=year,
        from_month=month
    ).aggregate(Sum('amount_seconds'))['amount_seconds__sum'] or 0

    incoming = MonthTransfer.objects.filter(
        user=user,
        to_year=year,
        to_month=month
    ).aggregate(Sum('amount_seconds'))['amount_seconds__sum'] or 0

    month_balance_td += timedelta(seconds=incoming - outgoing)
    return month_balance_td


@login_required  # Убедитесь, что пользователь авторизован
@csrf_exempt
@require_POST
def save_all_changes(request):
    """
    Обрабатывает единый POST-запрос с данными обо всех изменениях за месяц.
    """
    try:
        data = json.loads(request.body)
        changes = data.get('data', [])

        user = request.user
        is_admin_or_head = is_admin_user(user) or user.is_department_head

        # Используем транзакцию для обеспечения атомарности: либо все сохраняется, либо ничего
        with transaction.atomic():
            for day_data in changes:
                day_id = day_data.get('day_id')
                new_day_type = day_data.get('day_type')
                time_pairs = day_data.get('time_pairs', [])

                try:
                    # 1. Находим объект WorkDay
                    if is_admin_or_head:
                        workday = WorkDay.objects.get(id=day_id)
                    else:
                        workday = WorkDay.objects.get(id=day_id, user=user)
                except WorkDay.DoesNotExist:
                    continue

                # 2. Обновляем тип дня (WorkDay.type)
                if workday.type != new_day_type:
                    workday.type = new_day_type
                    workday.save()

                # 3. Удаляем все старые действия (Action) для этого дня
                workday.actions.all().delete()

                # 4. Создаем новые действия (Action)
                new_actions = []
                for pair in time_pairs:
                    order = int(pair.get('order'))
                    entry_time_str = pair.get('entry_time')
                    exit_time_str = pair.get('exit_time')
                    entry_type = pair.get('entry_type', 'default')  # Учитываем тип MK
                    is_calculated = pair.get('is_calculated', False)

                    # Обработка времени Входа
                    if entry_time_str:
                        entry_time_obj = datetime.strptime(entry_time_str, '%H:%M').time()
                        entry_dt = datetime.combine(workday.date_stamp, entry_time_obj)
                        entry_dt_aware = timezone.make_aware(entry_dt)

                        new_actions.append(Action(
                            workday=workday,
                            time_stamp=entry_dt_aware,
                            status_gate='EG',
                            order=order,
                            entry_type=entry_type,
                            is_calculated=is_calculated
                        ))

                    # Обработка времени Выхода
                    if exit_time_str:
                        exit_time_obj = datetime.strptime(exit_time_str, '%H:%M').time()
                        exit_dt = datetime.combine(workday.date_stamp, exit_time_obj)
                        exit_dt_aware = timezone.make_aware(exit_dt)
                        new_actions.append(Action(
                            workday=workday,
                            time_stamp=exit_dt_aware,
                            status_gate='OG',
                            order=order,
                            entry_type=entry_type,
                            is_calculated=is_calculated
                        ))

                # Сортируем по времени, чтобы убедиться, что порядок действий (EG/OG) правильный
                new_actions.sort(key=lambda x: x.time_stamp)
                Action.objects.bulk_create(new_actions)

                # 5. Пересчет итогов дня
                # Вызываем ваши существующие функции для пересчета итогов
                workday_total_duration = calculate_total_time_for_workday(workday)
                day_balance_td, _ = calculate_day_balance(workday_total_duration, workday.type,
                                                          workday.user.account_type)

                # Сохранение пересчитанных значений (предполагая, что WorkDay имеет поля total_time и day_balance)
                workday.total_time = workday_total_duration
                workday.day_balance = day_balance_td
                # Накопительный баланс (cumulative_balance) будет пересчитан при перезагрузке страницы (во view show_works_day)
                workday.save()

            # После успешного сохранения всех дней
            return JsonResponse({'status': 'success', 'message': 'Все изменения успешно сохранены!'}, status=200)

    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Неверный формат JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'Ошибка сервера при сохранении: {str(e)}'}, status=500)


@login_required
@csrf_exempt
@require_POST
def calculate_exit_time_api(request):
    try:
        data = json.loads(request.body)
        day_id = data.get('day_id')
        time_pairs = data.get('time_pairs', [])
        target_zero = bool(data.get('target_zero', False))
        user = request.user
        is_admin_or_head = is_admin_user(user) or user.is_department_head
        if is_admin_or_head:
            workday = get_object_or_404(WorkDay, id=day_id)
        else:
            workday = get_object_or_404(WorkDay, id=day_id, user=user)

        # 1. Создаем список временных объектов Action из переданных данных
        temp_actions = []

        def create_temp_action(time_str, status_gate, order, date_stamp):
            """Создает объект, имитирующий Action, из строки времени."""
            if time_str:
                try:
                    time_obj = datetime.strptime(time_str, '%H:%M').time()
                    dt = datetime.combine(date_stamp, time_obj)
                    dt_aware = timezone.make_aware(dt)

                    return type('TempAction', (object,), {
                        'time_stamp': dt_aware,
                        'status_gate': status_gate,
                        'order': order,
                        'entry_type': 'default',
                        'is_calculated': False
                    })
                except ValueError:
                    pass
            return None

        # Создаем временные действия для всех пар
        for pair in time_pairs:
            order = int(pair.get('order', 0))
            entry_action = create_temp_action(pair.get('entry_time'), 'EG', order, workday.date_stamp)
            exit_action = create_temp_action(pair.get('exit_time'), 'OG', order, workday.date_stamp)

            if entry_action: temp_actions.append(entry_action)
            if exit_action: temp_actions.append(exit_action)

        # 2. Создаем Mock-объект WorkDay, который будет использовать temp_actions
        mock_workday = MockWorkDay(workday, temp_actions)

        # 3. Вычисляем время выхода, используя Mock-объект
        exit_timestamp = calculate_required_exit_time(mock_workday, target_zero=target_zero)

        if not exit_timestamp:
            return JsonResponse(
                {'success': False, 'message': 'Не найдено время входа для расчета (нет открытой пары).'})

        required_exit_time = exit_timestamp.strftime('%H:%M')

        return JsonResponse({
            'success': True,
            'required_exit_time': required_exit_time,
            'target_zero': target_zero
        })

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Неверный формат JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


def calculate_required_exit_time(workday, target_zero=False):
    """
    Рассчитывает требуемое время выхода для последней пары времени,
    учитывая уже отработанное время в предыдущих парах и неоплачиваемый обед.
    Если target_zero=True, учитывает имеющийся баланс месяца так, чтобы выйти в 0.
    """
    entries = list(workday.actions.filter(status_gate='EG').order_by('order'))
    if not entries:
        return None

    first_entry_time = entries[0].time_stamp
    exits = list(workday.actions.filter(status_gate='OG', time_stamp__gte=first_entry_time).order_by('order'))

    last_entry_time = entries[-1].time_stamp

    total_duration = timedelta(0)
    num_completed_prior_pairs = min(len(entries) - 1, len(exits))

    for i in range(num_completed_prior_pairs):
        entry = entries[i]
        exit_action = exits[i]
        if entry and exit_action and exit_action.time_stamp > entry.time_stamp:
            total_duration += (exit_action.time_stamp - entry.time_stamp)

    outside_time_delta = timedelta(0)
    if len(entries) > 1 and len(exits) > 0:
        for i in range(min(len(exits), len(entries) - 1)):
            if i + 1 < len(entries):
                if entries[i + 1].time_stamp > exits[i].time_stamp:
                    outside_time_delta += (entries[i + 1].time_stamp - exits[i].time_stamp)

    required_duration = get_required_work_duration(workday.user.account_type)

    if target_zero:
        year = workday.date_stamp.year
        month = workday.date_stamp.month
        month_start = date(year, month, 1)

        other_workdays = WorkDay.objects.filter(
            user=workday.user,
            date_stamp__gte=month_start,
            date_stamp__lt=workday.date_stamp
        )

        prior_balance_td = timedelta(0)
        for wd in other_workdays:
            if wd.type not in ['WD', 'HD', 'VL', 'ED']:
                wd_dur = calculate_total_time_for_workday(wd)
                day_bal, _ = calculate_day_balance(wd_dur, wd.type, workday.user.account_type)
                prior_balance_td += day_bal

        outgoing = MonthTransfer.objects.filter(
            user=workday.user,
            from_year=year,
            from_month=month
        ).aggregate(Sum('amount_seconds'))['amount_seconds__sum'] or 0

        incoming = MonthTransfer.objects.filter(
            user=workday.user,
            to_year=year,
            to_month=month
        ).aggregate(Sum('amount_seconds'))['amount_seconds__sum'] or 0

        prior_balance_td += timedelta(seconds=incoming - outgoing)
        if prior_balance_td < timedelta(0):
            required_duration += abs(prior_balance_td)

    unpaid_break_threshold = timedelta(minutes=45)

    remaining_seconds = required_duration.total_seconds() - total_duration.total_seconds()
    if remaining_seconds <= 0:
        return last_entry_time

    if outside_time_delta < unpaid_break_threshold:
        exit_time = last_entry_time + timedelta(seconds=remaining_seconds) + (unpaid_break_threshold - outside_time_delta)
        if workday.type == 'SMD':
            if workday.user.account_type == 'student':
                exit_time -= timedelta(hours=1, minutes=45)
            else:
                exit_time -= timedelta(hours=1)
        return exit_time
    else:
        exit_time = last_entry_time + timedelta(seconds=remaining_seconds)
        if workday.type == 'SMD':
            exit_time -= timedelta(hours=1)
        return exit_time


@login_required
@require_POST
def import_data(request):
    try:
        if 'file' not in request.FILES:
            return JsonResponse({'success': False, 'message': 'Файл не был загружен.'})

        uploaded_file = request.FILES['file']

        if not uploaded_file.name.endswith('.tsv'):
            return JsonResponse({'success': False, 'message': 'Поддерживается только формат .tsv.'})

        user = request.user

        # Автоматическое определение кодировки
        raw_data = uploaded_file.read()
        detected_encoding = chardet.detect(raw_data)['encoding']

        file_data = raw_data.decode(detected_encoding).splitlines()
        reader = csv.reader(file_data, delimiter='\t')

        header = next(reader, None)
        if header is None:
            return JsonResponse({'success': False, 'message': 'Файл пуст или имеет неверный формат.'})

        workdays_data = {}
        for row in reader:
            if not any(row):
                continue

            if len(row) < 3:
                continue

            direction_str = row[0].strip()
            time_str = row[1].strip()
            date_str = row[2].strip()

            try:
                action_type = 'EG' if 'Вход' in direction_str else 'OG'
                date_obj = datetime.strptime(date_str, '%d.%m.%Y').date()
                time_obj = datetime.strptime(time_str, '%H:%M').time()

                combined_dt = datetime.combine(date_obj, time_obj)
                datetime_obj = timezone.make_aware(combined_dt)

                if date_obj not in workdays_data:
                    workdays_data[date_obj] = []

                workdays_data[date_obj].append({
                    'time_stamp': datetime_obj,
                    'status_gate': action_type
                })
            except ValueError as e:
                return JsonResponse({
                    'success': False,
                    'message': f'Ошибка парсинга данных в строке: {row}. Ошибка: {e}'
                })

        for date_stamp, actions_list in workdays_data.items():
            workday, _ = WorkDay.objects.get_or_create(
                user=user,
                date_stamp=date_stamp,
                defaults={'type': 'ND'}
            )

            # Перезаписываем обычные и рассчитанные действия, но сохраняем действия с типом МК (entry_type='mk')
            Action.objects.filter(workday=workday).exclude(entry_type='mk').delete()

            actions_list.sort(key=lambda x: x['time_stamp'])

            entry_actions = [a for a in actions_list if a['status_gate'] == 'EG']
            exit_actions = [a for a in actions_list if a['status_gate'] == 'OG']

            num_pairs = min(len(entry_actions), len(exit_actions))

            for i in range(num_pairs):
                Action.objects.create(
                    workday=workday,
                    time_stamp=entry_actions[i]['time_stamp'],
                    status_gate='EG',
                    order=i,
                    entry_type='default',
                    is_calculated=False
                )
                Action.objects.create(
                    workday=workday,
                    time_stamp=exit_actions[i]['time_stamp'],
                    status_gate='OG',
                    order=i,
                    entry_type='default',
                    is_calculated=False
                )

            for i in range(num_pairs, len(entry_actions)):
                Action.objects.create(
                    workday=workday,
                    time_stamp=entry_actions[i]['time_stamp'],
                    status_gate='EG',
                    order=i,
                    entry_type='default',
                    is_calculated=False
                )
            for i in range(num_pairs, len(exit_actions)):
                Action.objects.create(
                    workday=workday,
                    time_stamp=exit_actions[i]['time_stamp'],
                    status_gate='OG',
                    order=i,
                    entry_type='default',
                    is_calculated=False
                )

        return JsonResponse({'success': True, 'message': 'Данные успешно импортированы!'})

    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Произошла ошибка при обработке файла: {e}'})


@login_required
def show_works_day(request, year=None, month=None, day=None):
    """
    Отображает таблицу с рабочим временем пользователя за выбранный месяц, сгруппированную по неделям.
    """
    selected_date_str = request.GET.get('date', None)

    if selected_date_str:
        try:
            # 1. Попытка разобрать новый формат YYYY-MM (и установить 1-е число месяца)
            selected_date = datetime.strptime(selected_date_str, '%Y-%m').date().replace(day=1)

        except ValueError:
            try:
                # 2. Попытка разобрать старый формат YYYY-MM-DD
                selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
            except ValueError:
                # 3. Возврат к текущей дате, если парсинг не удался
                selected_date = timezone.localdate()
    else:
        # По умолчанию - текущая дата
        selected_date = timezone.localdate()

    # Определяем диапазон дат для всего месяца
    month_start_date = date(selected_date.year, selected_date.month, 1)
    month_end_date = date(selected_date.year, selected_date.month,
                          calendar.monthrange(selected_date.year, selected_date.month)[1])

    # Получаем все WorkDay объекты для месяца заранее
    all_workdays_in_month_dict = {
        wd.date_stamp: wd for wd in WorkDay.objects.filter(
            user=request.user,
            date_stamp__gte=month_start_date,
            date_stamp__lte=month_end_date
        ).order_by('date_stamp')
    }

    # Формируем недели месяца, включая дни из предыдущего и следующего
    month_weeks_data = []
    first_day_of_week = month_start_date - timedelta(days=month_start_date.weekday())
    current_day = first_day_of_week
    today = date.today()
    while True:
        week_dates = []
        is_week_in_month = False
        for i in range(7):
            day_in_week = current_day + timedelta(days=i)
            week_dates.append(day_in_week)
            if day_in_week.month == selected_date.month:
                is_week_in_month = True

        if is_week_in_month:
            month_weeks_data.append(week_dates)

        current_day = current_day + timedelta(days=7)

        if current_day > month_end_date:
            break
        # 1. Получаем список всех дней рождения в текущем месяце
        birthdays_data = get_birthdays_for_month(selected_date.month)

        # 2. Создаем словарь для быстрого поиска по дню месяца
        birthday_lookup = {bday['day']: bday['name'] for bday in birthdays_data}

        # 3. Формируем строку для верхнего списка ("5.10 - Сидельников | 14.10 - Петров")
        top_birthday_list_items = []
        month_num = selected_date.month

        for bday in birthdays_data:
            # Используем только фамилию (первое слово в полном имени)
            name_parts = bday['name'].split()
            name_for_list = name_parts[0] if name_parts else '—'
            top_birthday_list_items.append(f"{bday['day']}.{month_num:02d} - {name_for_list}")

        top_birthday_list_string = ' | '.join(top_birthday_list_items)

    # Получаем праздники и сокращённые дни из модели Holiday
    holidays_objs_dict = {h.date: h for h in Holiday.objects.all()}
    holidays_dict = {h.date: h.day_type for h in holidays_objs_dict.values()}

    # Подготовка данных для таблицы
    weekly_table_rows = []
    total_month_balance_td = timedelta(0)

    curr_outgoing = MonthTransfer.objects.filter(
        user=request.user,
        from_year=selected_date.year,
        from_month=selected_date.month
    ).aggregate(Sum('amount_seconds'))['amount_seconds__sum'] or 0

    curr_incoming = MonthTransfer.objects.filter(
        user=request.user,
        to_year=selected_date.year,
        to_month=selected_date.month
    ).aggregate(Sum('amount_seconds'))['amount_seconds__sum'] or 0

    current_cumulative_balance = timedelta(seconds=curr_incoming - curr_outgoing)

    for week_days in month_weeks_data:
        week_row_types = []
        week_row_times = []
        week_row_total_time = []
        week_row_day_balance = []
        week_row_cumulative_balance = []
        week_row_actions = []

        for date_obj in week_days:
            is_current_month = date_obj.month == selected_date.month
            workday = all_workdays_in_month_dict.get(date_obj)
            is_today = date_obj == date.today()
            hol_obj = holidays_objs_dict.get(date_obj)

            if date_obj in holidays_dict:
                default_day_type = holidays_dict[date_obj]
            elif date_obj.weekday() >= 5:
                default_day_type = 'WD'
            else:
                default_day_type = 'ND'

            if date_obj in holidays_dict:
                holiday_type = holidays_dict[date_obj]
                if workday:
                    if workday.type != holiday_type:
                        workday.type = holiday_type
                        workday.save()
                elif is_current_month:
                    workday, created = WorkDay.objects.get_or_create(
                        user=request.user,
                        date_stamp=date_obj,
                        defaults={'type': holiday_type}
                    )
            else:
                if not workday and is_current_month:
                    workday, created = WorkDay.objects.get_or_create(
                        user=request.user,
                        date_stamp=date_obj,
                        defaults={'type': default_day_type}
                    )

            if not is_current_month:
                workday_data = {
                    'id': None,
                    'type': 'ED',
                    'date_stamp': date_obj
                }
                workday = type('WorkDay', (object,), workday_data)()

            is_today = (date_obj == timezone.localdate())

            holiday_desc = hol_obj.description if (hol_obj and hol_obj.description) else ("Праздник" if (hol_obj or date_obj in holidays_dict) else "")

            week_row_types.append({
                'id': workday.id if workday else None,
                'type': workday.type if workday else 'WD',
                'display': dict(WorkDay.DAY_TYPE_CHOICES).get(workday.type, workday.type) if workday else 'WD',
                'is_current_month': is_current_month,
                'is_today': is_today,
                'holiday_desc': holiday_desc
            })

            if workday and workday.type not in ['WD', 'HD', 'VL', 'ED']:
                entries_by_order = {a.order: a for a in workday.actions.filter(status_gate='EG').order_by('order')}
                exits_by_order = {a.order: a for a in workday.actions.filter(status_gate='OG').order_by('order')}

                combined_times = []
                max_order = max(max(entries_by_order.keys(), default=-1), max(exits_by_order.keys(), default=-1))

                for i in range(max_order + 1):
                    entry = entries_by_order.get(i)
                    exit_action = exits_by_order.get(i)

                    if entry or exit_action:
                        is_calculated_flag = exit_action.is_calculated if exit_action else False
                        combined_times.append({
                            'entry_time_id': entry.id if entry else None,
                            'entry_time': timezone.localtime(entry.time_stamp).strftime('%H:%M') if entry else '',
                            'exit_time_id': exit_action.id if exit_action else None,
                            'exit_time': timezone.localtime(exit_action.time_stamp).strftime('%H:%M') if exit_action else '',
                            'order': i,
                            'day_id': workday.id,
                            'entry_type': entry.entry_type if entry else 'default',
                            'is_calculated': is_calculated_flag,
                            'is_today': is_today
                        })
                if not combined_times:
                    combined_times.append({
                        'entry_time_id': None, 'entry_time': '',
                        'exit_time_id': None, 'exit_time': '', 'order': 0,
                        'day_id': workday.id,
                        'is_today': is_today
                    })
                week_row_times.append({'id': workday.id if workday else None, 'pairs': combined_times, 'is_today': is_today})
            else:
                week_row_times.append({'id': workday.id if workday else None, 'pairs': None, 'is_today': is_today})

            if workday and workday.type not in ['WD', 'HD', 'VL', 'ED']:
                workday_total_duration = calculate_total_time_for_workday(workday)
                # day_balance_td, is_negative_balance = calculate_day_balance(workday_total_duration, workday.type)
                day_balance_td, is_negative_balance = calculate_day_balance(
                    workday_total_duration,
                    workday.type,
                    request.user.account_type
                )
                total_month_balance_td += day_balance_td
                week_row_total_time.append({
                    'id': workday.id,
                    'value': timedelta_to_hms_str(workday_total_duration),
                    'is_today': is_today
                })
                week_row_day_balance.append({
                    'id': workday.id,
                    'value': timedelta_to_hms_str(day_balance_td),
                    'is_negative': is_negative_balance,
                    'is_today': is_today
                })
            else:
                week_row_total_time.append({'id': workday.id if workday else None, 'value': None, 'is_today': is_today})
                week_row_day_balance.append({'id': workday.id if workday else None, 'value': None, 'is_today': is_today})

            if is_current_month:
                if workday and workday.type not in ['WD', 'HD', 'VL']:
                    # day_balance_td, _ = calculate_day_balance(calculate_total_time_for_workday(workday), workday.type)
                    day_balance_td, _ = calculate_day_balance(
                        workday_total_duration,
                        workday.type,
                        request.user.account_type
                    )
                    current_cumulative_balance += day_balance_td
                is_cumulative_negative = current_cumulative_balance < timedelta(0)

                week_row_cumulative_balance.append({
                    'id': workday.id if workday else None,
                    'value': timedelta_to_hms_str(current_cumulative_balance),
                    'is_negative': is_cumulative_negative,
                    'is_current_month': is_current_month,
                    'is_today': is_today
                })
            else:
                week_row_cumulative_balance.append({'id': workday.id if workday else None, 'value': None, 'is_today': is_today})

            week_row_actions.append({'id': workday.id if workday else None, 'is_current_month': is_current_month, 'is_today': is_today})

        RU_WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
        weekly_table_rows.append({
            'dates': [
                {
                    'date_obj': d,
                    'day_name_ru': RU_WEEKDAYS[d.weekday()],
                    'is_current_month': d.month == selected_date.month,
                    'is_today': (d == timezone.localdate()),
                    'is_birthday': birthday_lookup.get(d.day) is not None and d.month == selected_date.month,
                    'birthday_person': birthday_lookup.get(d.day) if d.month == selected_date.month else None,
                    'is_holiday': (holidays_objs_dict.get(d) is not None or d in holidays_dict),
                    'holiday_desc': (holidays_objs_dict.get(d).description if (holidays_objs_dict.get(d) and holidays_objs_dict.get(d).description) else ("Праздник" if (holidays_objs_dict.get(d) or d in holidays_dict) else ""))
                }
                for d in week_days
            ],
            'types': week_row_types,
            'times': week_row_times,
            'total_time': week_row_total_time,
            'day_balance': week_row_day_balance,
            'cumulative_balance': week_row_cumulative_balance,
            'actions': week_row_actions,
        })

        next_year = selected_date.year
        next_month = selected_date.month + 1
        if next_month > 12:
            next_month = 1
            next_year += 1
        next_date = selected_date.replace(day=1, month=next_month, year=next_year)
        current_next_month_name_formatted = next_date.strftime('%B').capitalize()
        prev_year = selected_date.year
        prev_month = selected_date.month - 1

        if prev_month < 1:
            prev_month = 12
            prev_year -= 1
        prev_date = selected_date.replace(day=1, month=prev_month, year=prev_year)
        current_prev_month_name_formatted = prev_date.strftime('%B').capitalize()

    # Учет переносов баланса между месяцами для текущего просматриваемого месяца
    curr_outgoing = MonthTransfer.objects.filter(
        user=request.user,
        from_year=selected_date.year,
        from_month=selected_date.month
    ).aggregate(Sum('amount_seconds'))['amount_seconds__sum'] or 0

    curr_incoming = MonthTransfer.objects.filter(
        user=request.user,
        to_year=selected_date.year,
        to_month=selected_date.month
    ).aggregate(Sum('amount_seconds'))['amount_seconds__sum'] or 0

    total_month_balance_td += timedelta(seconds=curr_incoming - curr_outgoing)

    total_month_balance_str = timedelta_to_hms_str(total_month_balance_td)
    is_month_balance_negative = total_month_balance_td < timedelta(0)
    previous_month_name_formatted = 0
    current_month_name_formatted = selected_date.strftime('%B %Y').capitalize()
    next_month_name_formatted = 0

    today = date.today()

    month_start_date = date(today.year, today.month, 1)
    today_workday = WorkDay.objects.filter(user=request.user, date_stamp=today).first()
    today_balance_str = "00:00"
    total_month_balance_td_tmp = timedelta(0)

    all_workdays_to_today = WorkDay.objects.filter(
        user=request.user,
        date_stamp__gte=month_start_date,
        date_stamp__lte=today
    ).order_by('date_stamp')

    is_today_balance_negative = False

    if today_workday:
        for wd_for_month_iter in all_workdays_to_today:
            current_day_total_duration = calculate_total_time_for_workday(wd_for_month_iter)
            current_day_type = wd_for_month_iter.type
            monthly_day_balance_td, _ = calculate_day_balance(
                current_day_total_duration,
                current_day_type,
                wd_for_month_iter.user.account_type
            )
            total_month_balance_td_tmp += monthly_day_balance_td

        # Учитываем переносы и добавления времени в текущем месяце для баланса "Сегодня"
        today_incoming = MonthTransfer.objects.filter(
            user=request.user,
            to_year=today.year,
            to_month=today.month
        ).aggregate(Sum('amount_seconds'))['amount_seconds__sum'] or 0

        today_outgoing = MonthTransfer.objects.filter(
            user=request.user,
            from_year=today.year,
            from_month=today.month
        ).aggregate(Sum('amount_seconds'))['amount_seconds__sum'] or 0

        total_month_balance_td_tmp += timedelta(seconds=today_incoming - today_outgoing)

        today_balance_str = timedelta_to_hms_str(total_month_balance_td_tmp)
        is_today_balance_negative = total_month_balance_td_tmp < timedelta(0)

    month_choices = []
    for i in range(1, 13):
        month_name = calendar.month_name[i].capitalize()
        month_choices.append((i, month_name))

    current_year = selected_date.year
    birthdays_this_month = get_birthdays_for_month(selected_date.month, selected_date.day)
    top_birthdays_list_items = []
    month_num = selected_date.month
    for bday in birthdays_this_month:
        name_parts = bday['name'].split()
        if len(name_parts) >= 3:
            name_show = name_parts[0] + ' ' + name_parts[1][0] + '.' + name_parts[2][0] + '.'
        elif len(name_parts) == 2:
            name_show = name_parts[0] + ' ' + name_parts[1][0] + '.'
        elif name_parts:
            name_show = name_parts[0]
        else:
            name_show = '--'
        name_for_list = name_show if bday['name'] else '--'
        top_birthdays_list_items.append(f"{bday['day']}.{month_num:02d} - {name_for_list}")
    top_birthday_list_string = ' | '.join(top_birthdays_list_items)

    birthday_lookup = {
        bday['day']: bday['name']
        for bday in birthdays_this_month
    }
    user_bg_color = request.session.get('user_bg_color', None)

    # баланс за прошлый месяц
    first_day_selcted_month = selected_date.replace(day=1)
    last_day_prev_month = first_day_selcted_month - timedelta(days=1)
    first_day_prev_month = last_day_prev_month.replace(day=1)

    prev_month_workdays = WorkDay.objects.filter(
        user=request.user,
        date_stamp__gte=first_day_prev_month,
        date_stamp__lte=last_day_prev_month
    )

    prev_month_balance_td = timedelta(0)

    for wd in prev_month_workdays:
        wd_duration = calculate_total_time_for_workday(wd)
        day_bal, _ = calculate_day_balance(
            wd_duration,
            wd.type,
            request.user.account_type
        )
        prev_month_balance_td += day_bal

    # Учет переносов баланса для прошлого месяца
    prev_outgoing = MonthTransfer.objects.filter(
        user=request.user,
        from_year=first_day_prev_month.year,
        from_month=first_day_prev_month.month
    ).aggregate(Sum('amount_seconds'))['amount_seconds__sum'] or 0

    prev_incoming = MonthTransfer.objects.filter(
        user=request.user,
        to_year=first_day_prev_month.year,
        to_month=first_day_prev_month.month
    ).aggregate(Sum('amount_seconds'))['amount_seconds__sum'] or 0

    prev_month_balance_td += timedelta(seconds=prev_incoming - prev_outgoing)

    prev_month_balance_str = timedelta_to_hms_str(prev_month_balance_td)
    is_prev_month_balance_negative = prev_month_balance_td < timedelta(0)

    # Раздельный расчет перенесенного и добавленного времени для выбранного месяца
    curr_transfers_out = MonthTransfer.objects.filter(
        user=request.user,
        from_year=selected_date.year,
        from_month=selected_date.month,
        from_year__isnull=False
    ).aggregate(Sum('amount_seconds'))['amount_seconds__sum'] or 0

    curr_transfers_in = MonthTransfer.objects.filter(
        user=request.user,
        to_year=selected_date.year,
        to_month=selected_date.month,
        from_year__isnull=False
    ).aggregate(Sum('amount_seconds'))['amount_seconds__sum'] or 0

    curr_additions_in = MonthTransfer.objects.filter(
        user=request.user,
        to_year=selected_date.year,
        to_month=selected_date.month,
        from_year__isnull=True
    ).aggregate(Sum('amount_seconds'))['amount_seconds__sum'] or 0

    transferred_td = timedelta(seconds=curr_transfers_in - curr_transfers_out)
    added_td = timedelta(seconds=curr_additions_in)

    month_transferred_time_str = timedelta_to_hms_str(transferred_td)
    is_transferred_negative = transferred_td < timedelta(0)

    month_added_time_str = timedelta_to_hms_str(added_td)
    is_added_negative = added_td < timedelta(0)

    # Список переносов и добавлений для модального окна
    month_transfers_qs = MonthTransfer.objects.filter(
        Q(user=request.user) & (
            Q(to_year=selected_date.year, to_month=selected_date.month) |
            Q(from_year=selected_date.year, from_month=selected_date.month)
        )
    ).order_by('-created_at')

    month_transfers_list = []
    for tr in month_transfers_qs:
        hours = abs(tr.amount_seconds) // 3600
        minutes = (abs(tr.amount_seconds) % 3600) // 60
        is_add = tr.from_year is None
        month_transfers_list.append({
            'id': tr.id,
            'is_addition': is_add,
            'amount_str': f"{hours:02d}:{minutes:02d}",
            'from_display': f"{tr.from_month:02d}.{tr.from_year}" if tr.from_year else "—",
            'to_display': f"{tr.to_month:02d}.{tr.to_year}",
            'description': tr.description or ("Добавление времени" if is_add else "Перенос между месяцами"),
            'created_at': tr.created_at.strftime('%d.%m.%Y %H:%M')
        })

    context = {
        'current_user_first_name': request.user.first_name,
        'current_user_pk': request.user.pk,
        'current_user_last_name': request.user.last_name,
        'weekly_table_rows': weekly_table_rows,
        'current_user': request.user,
        'current_month_display': current_month_name_formatted,
        'next_month_display': current_next_month_name_formatted,
        'prev_month_display': current_prev_month_name_formatted,
        'total_month_balance': total_month_balance_str,
        'is_month_balance_negative': is_month_balance_negative,

        'today_balance': today_balance_str,
        'is_today_balance_negative': is_today_balance_negative,
        'prev_month_balance': prev_month_balance_str,
        'is_prev_month_balance_negative': is_prev_month_balance_negative,

        'month_transferred_time': month_transferred_time_str,
        'is_transferred_negative': is_transferred_negative,
        'month_added_time': month_added_time_str,
        'is_added_negative': is_added_negative,
        'month_transfers_list': month_transfers_list,

        'selected_date': selected_date.isoformat(),
        'month_choices': month_choices,
        'current_year': current_year,
        'birthdays_this_month': birthdays_this_month,
        'top_birthdays_list': top_birthdays_list_items,
        'top_birthday_string': top_birthday_list_string,
        'theme_mode': request.session.get('theme_mode', 'dark'),
        'today_phrase': get_random_today_phrase(request.user),
    }

    return render(request, 'accounts/index.html', context)


@login_required
@csrf_exempt
@require_POST
def update_work_times(request):
    try:
        data = json.loads(request.body)
        day_id = data.get('dayId')
        day_type = data.get('day_type')
        time_entries = data.get('time_entries', [])

        user = request.user
        is_admin_or_head = is_admin_user(user) or user.is_department_head
        if is_admin_or_head:
            workday = get_object_or_404(WorkDay, id=day_id)
        else:
            workday = get_object_or_404(WorkDay, id=day_id, user=user)

        target_user = workday.user

        workday.type = day_type
        workday.save()
        workday.actions.all().delete()

        for entry in time_entries:
            time_str = entry.get('time')
            if time_str:
                combined_datetime_str = f"{workday.date_stamp.isoformat()} {time_str}:00"
                correct_dt = datetime.fromisoformat(combined_datetime_str)
                aware_dt = timezone.make_aware(correct_dt)
                entry_type = entry.get('entry_type', 'default')
                is_calculated = entry.get('is_calculated', False)

                Action.objects.create(
                    workday=workday,
                    status_gate=entry.get('type'),
                    time_stamp=aware_dt,
                    entry_type=entry_type,
                    order=entry.get('order', 0),
                    is_calculated=is_calculated
                )

        workday_total_duration = calculate_total_time_for_workday(workday)
        new_total_time_str = timedelta_to_hms_str(workday_total_duration)

        # Вызываем calculate_day_balance с аккаунт-типом владельца табеля
        day_balance_td, is_negative_balance = calculate_day_balance(
            workday_total_duration,
            workday.type,
            target_user.account_type
        )
        new_day_balance_str = timedelta_to_hms_str(day_balance_td)

        selected_date_for_month = workday.date_stamp
        month_start_date = date(selected_date_for_month.year, selected_date_for_month.month, 1)
        month_end_date = date(selected_date_for_month.year, selected_date_for_month.month,
                              calendar.monthrange(selected_date_for_month.year, selected_date_for_month.month)[1])

        total_month_balance_td = timedelta(0)

        curr_outgoing_ajax = MonthTransfer.objects.filter(
            user=target_user,
            from_year=month_start_date.year,
            from_month=month_start_date.month
        ).aggregate(Sum('amount_seconds'))['amount_seconds__sum'] or 0

        curr_incoming_ajax = MonthTransfer.objects.filter(
            user=target_user,
            to_year=month_start_date.year,
            to_month=month_start_date.month
        ).aggregate(Sum('amount_seconds'))['amount_seconds__sum'] or 0

        current_cumulative_balance_td = timedelta(seconds=curr_incoming_ajax - curr_outgoing_ajax)

        all_workdays_in_month = WorkDay.objects.filter(
            user=target_user,
            date_stamp__gte=month_start_date,
            date_stamp__lte=month_end_date
        ).order_by('date_stamp')

        for wd_for_month_iter in all_workdays_in_month:
            current_day_total_duration = calculate_total_time_for_workday(wd_for_month_iter)
            current_day_type = wd_for_month_iter.type
            monthly_day_balance_td = timedelta(0)

            if current_day_type not in ['WD', 'HD', 'VL']:
                # Вызываем calculate_day_balance с новым аргументом
                monthly_day_balance_td, _ = calculate_day_balance(
                    current_day_total_duration,
                    current_day_type,
                    wd_for_month_iter.user.account_type
                )

            total_month_balance_td += monthly_day_balance_td
            current_cumulative_balance_td += monthly_day_balance_td

            if wd_for_month_iter.id == workday.id:
                new_cumulative_balance_str = timedelta_to_hms_str(current_cumulative_balance_td)

        total_month_balance_str = timedelta_to_hms_str(total_month_balance_td)
        is_month_balance_negative = total_month_balance_td < timedelta(0)
        is_cumulative_balance_negative = current_cumulative_balance_td < timedelta(0)

        # print(
        #     'new_total_time', new_total_time_str,
        #     'new_day_balance', new_day_balance_str,
        #     'is_negative_day_balance', is_negative_balance,
        #     'total_month_balance', total_month_balance_str,
        #     'is_month_balance_negative', is_month_balance_negative,
        #     'new_cumulative_balance', new_cumulative_balance_str,
        #     'is_cumulative_balance_negative', is_cumulative_balance_negative
        # )

        return JsonResponse({
            'success': True,
            'message': 'Данные успешно сохранены',
            'new_total_time': new_total_time_str,
            'new_day_balance': new_day_balance_str,
            'is_negative_day_balance': is_negative_balance,
            'total_month_balance': total_month_balance_str,
            'is_month_balance_negative': is_month_balance_negative,
            'new_cumulative_balance': new_cumulative_balance_str,
            'is_cumulative_balance_negative': is_cumulative_balance_negative,
        })

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Неверный формат JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)

# #воруем данные из СУЗ
# @csrf_exempt
# def get_suz_link(request):
#     try:
#         data = json.loads(request.body)
#         suz_cookies_str = data.get('cookies', '')
#     except Exception:
#         suz_cookies_str = ''
#
#     cookies_dict = {}
#     if suz_cookies_str:
#         for item in suz_cookies_str.split('; '):
#             if '=' in item:
#                 k, v = item.split('=', 1)
#                 cookies_dict[k] = v
#
#     api_url = "https://suz.sukhoi.company/api/v1/auth/check/"
#
#     # Имитируем реальный браузер, чтобы СУЗ не заблокировал запрос со стороны Python
#     headers = {
#         'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
#         'Accept': 'application/json, text/plain, */*',
#         'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
#     }
#
#     try:
#         # Передаем куки и заголовки браузера
#         response = requests.get(api_url, cookies=cookies_dict, headers=headers, timeout=5, verify=False)
#         print(response.status_code)
#         if response.status_code == 200:
#             suz_data = response.json()
#             user_data = suz_data.get('content', {}).get('user', {})
#
#             crypted_id = user_data.get('crypted_id')
#             identifier = user_data.get('identifier')
#
#             if crypted_id and identifier:
#                 clean_crypted_id = urllib.parse.quote(crypted_id)
#                 final_url = f"https://msk-ouz-apps.sukhoi.company:1562/?user_id={clean_crypted_id}&user_page_id={identifier}"
#
#                 return JsonResponse({'success': True, 'url': final_url})
#             else:
#                 print("Ключи crypted_id или identifier не найдены в JSON СУЗ")
#         else:
#             print(f"СУЗ ответил кодом {response.status_code}: {response.text}")
#
#     except Exception as e:
#         print(f"Ошибка проксирования запроса к СУЗ: {e}")
#
#
#     # Фолбэк, если что-то пошло не так
#     return JsonResponse({'success': False, 'url': 'https://suz.sukhoi.company'})
#

@login_required
def department_stats(request):
    """
    Отображает статистику посещаемости и рабочего времени для сотрудников отдела.
    Доступно для начальников отделов (is_department_head=True), администраторов или суперпользователей.
    """
    user = request.user
    if not (user.is_department_head or user.is_superuser or user.is_staff):
        return render(request, 'accounts/permission_denied.html', {
            'message': 'Доступ к статистике отдела ограничен. Вы не являетесь начальником отдела.'
        }, status=403)

    all_departments = Department.objects.all()
    dept_id = request.GET.get('department_id')

    if dept_id and (user.is_superuser or user.is_staff or (user.department and str(user.department.id) == dept_id)):
        department = get_object_or_404(Department, id=dept_id)
    elif user.department:
        department = user.department
    elif all_departments.exists():
        department = all_departments.first()
    else:
        department = None

    date_param = request.GET.get('date', None)
    if date_param:
        try:
            selected_date = datetime.strptime(date_param, '%Y-%m').date().replace(day=1)
        except ValueError:
            selected_date = timezone.localdate().replace(day=1)
    else:
        selected_date = timezone.localdate().replace(day=1)

    month_start_date = date(selected_date.year, selected_date.month, 1)
    days_in_month_count = calendar.monthrange(selected_date.year, selected_date.month)[1]
    month_end_date = date(selected_date.year, selected_date.month, days_in_month_count)

    days_list = [date(selected_date.year, selected_date.month, d) for d in range(1, days_in_month_count + 1)]

    employees_data = []
    total_dept_worked_td = timedelta(0)
    total_dept_balance_td = timedelta(0)

    if department:
        employees = User.objects.filter(department=department).order_by('last_name', 'first_name', 'username')

        for emp in employees:
            emp_workdays = WorkDay.objects.filter(
                user=emp,
                date_stamp__gte=month_start_date,
                date_stamp__lte=month_end_date
            ).order_by('date_stamp')

            workday_dict = {wd.date_stamp: wd for wd in emp_workdays}

            emp_worked_td = timedelta(0)
            emp_balance_td = timedelta(0)

            # Накопительный баланс на начало просматриваемого месяца (входящие переносы с плюсом)
            emp_outgoing = MonthTransfer.objects.filter(
                user=emp,
                from_year=selected_date.year,
                from_month=selected_date.month
            ).aggregate(Sum('amount_seconds'))['amount_seconds__sum'] or 0

            emp_incoming = MonthTransfer.objects.filter(
                user=emp,
                to_year=selected_date.year,
                to_month=selected_date.month
            ).aggregate(Sum('amount_seconds'))['amount_seconds__sum'] or 0

            running_cumulative_td = timedelta(seconds=emp_incoming - emp_outgoing)

            day_types_count = {
                'ND': 0, 'WD': 0, 'HD': 0, 'VL': 0,
                'SMD': 0, 'MK': 0, 'KMD': 0, 'OT': 0, 'ED': 0
            }

            daily_records = []

            for d in days_list:
                wd = workday_dict.get(d)
                if wd:
                    day_type = wd.type
                    total_dur = calculate_total_time_for_workday(wd)
                    day_bal, _ = calculate_day_balance(total_dur, day_type, emp.account_type)

                    emp_worked_td += total_dur
                    emp_balance_td += day_bal
                    running_cumulative_td += day_bal

                    day_types_count[day_type] = day_types_count.get(day_type, 0) + 1

                    daily_records.append({
                        'day': d.day,
                        'weekday_ru': ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'][d.weekday()],
                        'is_weekend': d.weekday() in [5, 6],
                        'type': day_type,
                        'display_type': wd.get_type_display(),
                        'worked_str': timedelta_to_hms_str(total_dur) if total_dur.total_seconds() > 0 else '—',
                        'day_balance_str': timedelta_to_hms_str(day_bal),
                        'is_day_balance_negative': day_bal < timedelta(0),
                        'cumulative_balance_str': timedelta_to_hms_str(running_cumulative_td),
                        'is_cumulative_balance_negative': running_cumulative_td < timedelta(0),
                        'has_actions': wd.actions.exists()
                    })
                else:
                    is_weekend = d.weekday() in [5, 6]
                    default_type = 'WD' if is_weekend else 'ND'
                    day_types_count[default_type] = day_types_count.get(default_type, 0) + 1
                    daily_records.append({
                        'day': d.day,
                        'weekday_ru': ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'][d.weekday()],
                        'is_weekend': is_weekend,
                        'type': default_type,
                        'display_type': 'Выходной' if is_weekend else 'Рабочий день',
                        'worked_str': '—',
                        'day_balance_str': '00:00',
                        'is_day_balance_negative': False,
                        'cumulative_balance_str': timedelta_to_hms_str(running_cumulative_td),
                        'is_cumulative_balance_negative': running_cumulative_td < timedelta(0),
                        'has_actions': False
                    })

            curr_transfers_out = MonthTransfer.objects.filter(
                user=emp,
                from_year=selected_date.year,
                from_month=selected_date.month,
                from_year__isnull=False
            ).aggregate(Sum('amount_seconds'))['amount_seconds__sum'] or 0

            curr_transfers_in = MonthTransfer.objects.filter(
                user=emp,
                to_year=selected_date.year,
                to_month=selected_date.month,
                from_year__isnull=False
            ).aggregate(Sum('amount_seconds'))['amount_seconds__sum'] or 0

            curr_additions_in = MonthTransfer.objects.filter(
                user=emp,
                to_year=selected_date.year,
                to_month=selected_date.month,
                from_year__isnull=True
            ).aggregate(Sum('amount_seconds'))['amount_seconds__sum'] or 0

            transferred_td = timedelta(seconds=curr_transfers_in - curr_transfers_out)
            added_td = timedelta(seconds=curr_additions_in)

            emp_transferred_str = timedelta_to_hms_str(transferred_td)
            is_emp_transferred_negative = transferred_td < timedelta(0)

            emp_added_str = timedelta_to_hms_str(added_td)
            is_emp_added_negative = added_td < timedelta(0)

            emp_balance_td += timedelta(seconds=(curr_transfers_in + curr_additions_in) - curr_transfers_out)

            total_dept_worked_td += emp_worked_td
            total_dept_balance_td += emp_balance_td

            employees_data.append({
                'user': emp,
                'full_name': f"{emp.last_name} {emp.first_name}".strip() or emp.username,
                'username': emp.username,
                'account_type_display': emp.get_account_type_display(),
                'is_head': emp.is_department_head,
                'total_worked_str': timedelta_to_hms_str(emp_worked_td),
                'month_balance_str': timedelta_to_hms_str(emp_balance_td),
                'is_balance_negative': emp_balance_td < timedelta(0),
                'transferred_str': emp_transferred_str,
                'is_transferred_negative': is_emp_transferred_negative,
                'added_str': emp_added_str,
                'is_added_negative': is_emp_added_negative,
                'day_types_count': day_types_count,
                'daily_records': daily_records
            })

    daily_rows = []
    if employees_data:
        for day_idx, d in enumerate(days_list):
            row_employees = []
            for emp_data in employees_data:
                rec = emp_data['daily_records'][day_idx]
                row_employees.append({
                    'emp': emp_data['user'],
                    'full_name': emp_data['full_name'],
                    'record': rec
                })

            daily_rows.append({
                'day': d.day,
                'date': d,
                'weekday_ru': ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'][d.weekday()],
                'is_weekend': d.weekday() in [5, 6],
                'row_employees': row_employees
            })

    next_year, next_month = (selected_date.year + 1, 1) if selected_date.month == 12 else (selected_date.year, selected_date.month + 1)
    prev_year, prev_month = (selected_date.year - 1, 12) if selected_date.month == 1 else (selected_date.year, selected_date.month - 1)

    next_date_str = f"{next_year}-{next_month:02d}"
    prev_date_str = f"{prev_year}-{prev_month:02d}"

    month_choices = [(i, calendar.month_name[i].capitalize()) for i in range(1, 13)]

    # Вычисление недельной таблицы для выбранного сотрудника (для табеля)
    user_id_param = request.GET.get('user_id')
    selected_user = None
    selected_user_weekly_rows = []
    selected_user_month_worked_td = timedelta(0)
    selected_user_month_balance_td = timedelta(0)

    if department:
        employees_qs = User.objects.filter(department=department).order_by('last_name', 'first_name', 'username')
        if user_id_param and employees_qs.filter(id=user_id_param).exists():
            selected_user = employees_qs.get(id=user_id_param)
        elif employees_qs.exists():
            selected_user = employees_qs.first()

        if selected_user:
            cal = calendar.Calendar(firstweekday=0)
            month_days_list = list(cal.itermonthdates(selected_date.year, selected_date.month))
            selected_user_month_weeks = [month_days_list[i:i + 7] for i in range(0, len(month_days_list), 7)]

            month_start_range = selected_user_month_weeks[0][0]
            month_end_range = selected_user_month_weeks[-1][-1]

            user_workdays_dict = {
                wd.date_stamp: wd for wd in WorkDay.objects.filter(
                    user=selected_user,
                    date_stamp__gte=month_start_range,
                    date_stamp__lte=month_end_range
                )
            }

            holidays_dict = {h.date: h.day_type for h in Holiday.objects.all()}
            birthday_lookup = {b.date.day: b.full_name for b in Birthday.objects.filter(date__month=selected_date.month)}

            curr_outgoing = MonthTransfer.objects.filter(
                user=selected_user,
                from_year=selected_date.year,
                from_month=selected_date.month
            ).aggregate(Sum('amount_seconds'))['amount_seconds__sum'] or 0

            curr_incoming = MonthTransfer.objects.filter(
                user=selected_user,
                to_year=selected_date.year,
                to_month=selected_date.month
            ).aggregate(Sum('amount_seconds'))['amount_seconds__sum'] or 0

            running_cumulative = timedelta(seconds=curr_incoming - curr_outgoing)

            for week_days in selected_user_month_weeks:
                week_row_types = []
                week_row_times = []
                week_row_total_time = []
                week_row_day_balance = []
                week_row_cumulative_balance = []
                week_row_actions = []

                for date_obj in week_days:
                    is_current_month = (date_obj.month == selected_date.month)
                    workday = user_workdays_dict.get(date_obj)
                    is_today = (date_obj == timezone.localdate())

                    if date_obj in holidays_dict:
                        default_day_type = holidays_dict[date_obj]
                    elif date_obj.weekday() >= 5:
                        default_day_type = 'WD'
                    else:
                        default_day_type = 'ND'

                    if date_obj in holidays_dict:
                        holiday_type = holidays_dict[date_obj]
                        if workday:
                            if workday.type != holiday_type:
                                workday.type = holiday_type
                                workday.save()
                        elif is_current_month:
                            workday, _ = WorkDay.objects.get_or_create(
                                user=selected_user,
                                date_stamp=date_obj,
                                defaults={'type': holiday_type}
                            )
                    else:
                        if not workday and is_current_month:
                            workday, _ = WorkDay.objects.get_or_create(
                                user=selected_user,
                                date_stamp=date_obj,
                                defaults={'type': default_day_type}
                            )

                    if not is_current_month:
                        workday_data = {'id': None, 'type': 'ED', 'date_stamp': date_obj}
                        workday = type('WorkDay', (object,), workday_data)()

                    week_row_types.append({
                        'id': workday.id if workday else None,
                        'type': workday.type if workday else 'WD',
                        'display': dict(WorkDay.DAY_TYPE_CHOICES).get(workday.type, workday.type) if workday else 'WD',
                        'is_current_month': is_current_month,
                        'is_today': is_today
                    })

                    if workday and workday.type not in ['WD', 'HD', 'VL', 'ED']:
                        entries_by_order = {a.order: a for a in workday.actions.filter(status_gate='EG').order_by('order')}
                        exits_by_order = {a.order: a for a in workday.actions.filter(status_gate='OG').order_by('order')}

                        combined_times = []
                        max_order = max(max(entries_by_order.keys(), default=-1), max(exits_by_order.keys(), default=-1))

                        for i in range(max_order + 1):
                            entry = entries_by_order.get(i)
                            exit_action = exits_by_order.get(i)

                            if entry or exit_action:
                                is_calculated_flag = exit_action.is_calculated if exit_action else False
                                combined_times.append({
                                    'entry_time_id': entry.id if entry else None,
                                    'entry_time': timezone.localtime(entry.time_stamp).strftime('%H:%M') if entry else '',
                                    'exit_time_id': exit_action.id if exit_action else None,
                                    'exit_time': timezone.localtime(exit_action.time_stamp).strftime('%H:%M') if exit_action else '',
                                    'order': i,
                                    'day_id': workday.id,
                                    'entry_type': entry.entry_type if entry else 'default',
                                    'is_calculated': is_calculated_flag,
                                    'is_today': is_today
                                })
                        if not combined_times:
                            combined_times.append({
                                'entry_time_id': None, 'entry_time': '',
                                'exit_time_id': None, 'exit_time': '', 'order': 0,
                                'day_id': workday.id,
                                'is_today': is_today
                            })
                        week_row_times.append({'id': workday.id if workday else None, 'pairs': combined_times, 'is_today': is_today})
                    else:
                        week_row_times.append({'id': workday.id if workday else None, 'pairs': None, 'is_today': is_today})

                    if workday and workday.type not in ['WD', 'HD', 'VL', 'ED']:
                        workday_total_duration = calculate_total_time_for_workday(workday)
                        day_balance_td, is_negative_balance = calculate_day_balance(
                            workday_total_duration,
                            workday.type,
                            selected_user.account_type
                        )
                        if is_current_month:
                            selected_user_month_worked_td += workday_total_duration
                            selected_user_month_balance_td += day_balance_td
                        week_row_total_time.append({
                            'id': workday.id,
                            'value': timedelta_to_hms_str(workday_total_duration),
                            'is_today': is_today
                        })
                        week_row_day_balance.append({
                            'id': workday.id,
                            'value': timedelta_to_hms_str(day_balance_td),
                            'is_negative': is_negative_balance,
                            'is_today': is_today
                        })
                    else:
                        week_row_total_time.append({'id': workday.id if workday else None, 'value': None, 'is_today': is_today})
                        week_row_day_balance.append({'id': workday.id if workday else None, 'value': None, 'is_today': is_today})

                    if is_current_month:
                        if workday and workday.type not in ['WD', 'HD', 'VL']:
                            day_balance_td, _ = calculate_day_balance(
                                workday_total_duration,
                                workday.type,
                                selected_user.account_type
                            )
                            running_cumulative += day_balance_td
                        is_cumulative_negative = running_cumulative < timedelta(0)

                        week_row_cumulative_balance.append({
                            'id': workday.id if workday else None,
                            'value': timedelta_to_hms_str(running_cumulative),
                            'is_negative': is_cumulative_negative,
                            'is_current_month': is_current_month,
                            'is_today': is_today
                        })
                    else:
                        week_row_cumulative_balance.append({'id': workday.id if workday else None, 'value': None, 'is_today': is_today})

                    week_row_actions.append({'id': workday.id if workday else None, 'is_current_month': is_current_month, 'is_today': is_today})

                RU_WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
                selected_user_weekly_rows.append({
                    'dates': [
                        {
                            'date_obj': d,
                            'day_name_ru': RU_WEEKDAYS[d.weekday()],
                            'is_current_month': d.month == selected_date.month,
                            'is_today': (d == timezone.localdate()),
                            'is_birthday': birthday_lookup.get(d.day) is not None and d.month == selected_date.month,
                            'birthday_person': birthday_lookup.get(d.day) if d.month == selected_date.month else None,
                        }
                        for d in week_days
                    ],
                    'types': week_row_types,
                    'times': week_row_times,
                    'total_time': week_row_total_time,
                    'day_balance': week_row_day_balance,
                    'cumulative_balance': week_row_cumulative_balance,
                    'actions': week_row_actions,
                })

    context = {
        'department': department,
        'all_departments': all_departments,
        'employees_data': employees_data,
        'daily_rows': daily_rows,
        'selected_user': selected_user,
        'selected_user_weekly_rows': selected_user_weekly_rows,
        'selected_user_month_worked_str': timedelta_to_hms_str(selected_user_month_worked_td),
        'selected_user_month_balance_str': timedelta_to_hms_str(selected_user_month_balance_td),
        'is_selected_user_balance_negative': selected_user_month_balance_td < timedelta(0),
        'selected_date_str': selected_date.strftime('%Y-%m'),
        'current_month_display': selected_date.strftime('%B %Y').capitalize(),
        'prev_date_str': prev_date_str,
        'next_date_str': next_date_str,
        'days_list': days_list,
        'month_choices': month_choices,
        'current_year': selected_date.year,
        'total_dept_worked_str': timedelta_to_hms_str(total_dept_worked_td),
        'total_dept_balance_str': timedelta_to_hms_str(total_dept_balance_td),
        'is_dept_balance_negative': total_dept_balance_td < timedelta(0),
        'theme_mode': request.session.get('theme_mode', 'dark'),
    }

    return render(request, 'accounts/department_stats.html', context)


@login_required
@csrf_exempt
@require_POST
def add_mk_slot(request):
    """
    Добавляет интервал МК (больничного) для выбранной даты из модального окна.
    """
    try:
        data = json.loads(request.body)
        date_str = data.get('date')
        entry_time_str = data.get('entry_time', '').strip()
        exit_time_str = data.get('exit_time', '').strip()

        if not date_str or not entry_time_str or not exit_time_str:
            return JsonResponse({'success': False, 'message': 'Заполните дату и время входа/выхода'})

        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        user = request.user
        target_user_id = data.get('user_id')
        if target_user_id and (is_admin_user(user) or user.is_department_head):
            target_user = get_object_or_404(User, pk=target_user_id)
        else:
            target_user = user

        workday, _ = WorkDay.objects.get_or_create(user=target_user, date_stamp=date_obj)

        existing_orders = list(workday.actions.values_list('order', flat=True))
        new_order = (max(existing_orders) + 1) if existing_orders else 0

        entry_time_obj = datetime.strptime(entry_time_str, '%H:%M').time()
        exit_time_obj = datetime.strptime(exit_time_str, '%H:%M').time()

        entry_dt = datetime.combine(date_obj, entry_time_obj)
        exit_dt = datetime.combine(date_obj, exit_time_obj)

        try:
            entry_dt = timezone.make_aware(entry_dt)
        except Exception:
            pass

        try:
            exit_dt = timezone.make_aware(exit_dt)
        except Exception:
            pass

        Action.objects.create(
            workday=workday,
            time_stamp=entry_dt,
            status_gate='EG',
            order=new_order,
            entry_type='mk'
        )
        Action.objects.create(
            workday=workday,
            time_stamp=exit_dt,
            status_gate='OG',
            order=new_order,
            entry_type='mk'
        )

        return JsonResponse({
            'success': True,
            'message': f'МК успешно добавлен за {date_obj.strftime("%d.%m.%Y")} ({entry_time_str} - {exit_time_str})',
            'day_id': workday.id
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'message': f'Ошибка при сохранении: {str(e)}'})


@login_required
def time_manager_view(request):
    """
    Планировщик задач для пользователей (/accounts/time-manager).
    """
    seed_task_priorities_if_empty()
    seed_task_topics_if_empty()
    user = request.user
    is_admin = is_admin_user(user)
    department = user.department
    error_message = None

    if user.department:
        department_employees = User.objects.filter(department=user.department).order_by('last_name', 'first_name', 'username')
    else:
        department_employees = User.objects.all().order_by('last_name', 'first_name', 'username')

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        due_date_str = request.POST.get('due_date', '').strip()
        assigned_to_id = request.POST.get('assigned_to')
        priority_id = request.POST.get('priority')
        topic_id = request.POST.get('topic')
        schedule_type = request.POST.get('schedule_type', 'off_schedule')
        schedule_number = request.POST.get('schedule_number', '').strip()
        archive_url = request.POST.get('archive_url', '').strip()
        co_assignees_ids = request.POST.getlist('co_assignees') if is_admin else []

        if not title or not due_date_str:
            error_message = "Пожалуйста, заполните заголовок и дату выполнения задачи."
        else:
            try:
                if '.' in due_date_str:
                    due_date = datetime.strptime(due_date_str, '%d.%m.%Y').date()
                else:
                    due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()

                if is_admin and assigned_to_id:
                    if user.department:
                        assigned_user = get_object_or_404(User, pk=assigned_to_id, department=user.department)
                    else:
                        assigned_user = get_object_or_404(User, pk=assigned_to_id)
                else:
                    assigned_user = user

                priority_obj = None
                if priority_id:
                    priority_obj = TaskPriority.objects.filter(pk=priority_id).first()
                if not priority_obj:
                    priority_obj = TaskPriority.objects.filter(code=2).first()

                topic_obj = None
                if topic_id:
                    topic_obj = TaskTopic.objects.filter(pk=topic_id).first()

                task_department = user.department or getattr(assigned_user, 'department', None)

                task = Task.objects.create(
                    title=title,
                    description=description,
                    due_date=due_date,
                    created_by=user,
                    assigned_to=assigned_user,
                    department=task_department,
                    priority=priority_obj,
                    topic=topic_obj,
                    schedule_type=schedule_type,
                    schedule_number=schedule_number,
                    archive_url=archive_url,
                    status='assigned',
                    is_read_by_assignee=(assigned_user == user)
                )

                if is_admin and co_assignees_ids:
                    if user.department:
                        co_users = User.objects.filter(pk__in=co_assignees_ids, department=user.department)
                    else:
                        co_users = User.objects.filter(pk__in=co_assignees_ids)
                    task.co_assignees.set(co_users)
                    for cu in co_users:
                        TaskCoAssigneeApproval.objects.get_or_create(task=task, user=cu, defaults={'is_approved': False})

                # Хронология: создание задачи
                creator_name = f"{user.first_name} {user.last_name}".strip() or user.username
                assignee_name = f"{assigned_user.first_name} {assigned_user.last_name}".strip() or assigned_user.username
                co_names = ", ".join([f"{u.first_name} {u.last_name}".strip() or u.username for u in task.co_assignees.all()])
                prio_name = priority_obj.name if priority_obj else "Средний"
                desc_log = f"Задача создана пользователем {creator_name}. Ответственный: {assignee_name}. Приоритет: {prio_name}."
                if topic_obj:
                    desc_log += f" Тема: {topic_obj.name}."
                if co_names:
                    desc_log += f" Дополнительные исполнители: {co_names}."
                # Хронологические зависимости
                dependencies_raw = request.POST.get('dependencies', '').strip()
                if dependencies_raw:
                    try:
                        new_deps = json.loads(dependencies_raw)
                        validate_dependencies_no_cycle(None, new_deps)
                        deps_created = []
                        for d in new_deps:
                            t_id = d.get('depends_on_id')
                            if t_id:
                                target_t = Task.objects.filter(pk=t_id).first()
                                if target_t:
                                    rel_type = d.get('relation_type', TaskDependency.RELATION_FS)
                                    if rel_type not in dict(TaskDependency.RELATION_CHOICES):
                                        rel_type = TaskDependency.RELATION_FS
                                    lag_lead = int(d.get('lag_lead_days', 0))
                                    TaskDependency.objects.create(
                                        task=task,
                                        depends_on=target_t,
                                        relation_type=rel_type,
                                        lag_lead_days=lag_lead
                                    )
                                    offset_str = f" ({lag_lead:+d} дн.)" if lag_lead != 0 else ""
                                    deps_created.append(f"#{target_t.id} [{rel_type}]{offset_str}")
                        if deps_created:
                            desc_log += f" Установлены зависимости: {', '.join(deps_created)}."
                    except Exception:
                        pass

                log_task_history(task, user, "Создание задачи", desc_log)
                notify_task_changed(task, actor=user, change_detail="Создана новая задача")

                return redirect('time_manager')
            except ValueError:
                error_message = "Неверный формат даты выполнения (используйте ДД.ММ.ГГГГ или выбор даты)."

    # Подзапрос непрочитанных / изменённых задач для текущего пользователя
    unread_subquery = TaskUserNotification.objects.filter(
        task=OuterRef('pk'),
        user=user,
        is_read=False
    )

    priorities = TaskPriority.objects.all().order_by('code')
    topics = TaskTopic.objects.all().order_by('name')

    if is_admin:
        if user.department:
            tasks = Task.objects.filter(department=user.department)
        elif user.is_superuser:
            tasks = Task.objects.all()
        else:
            tasks = Task.objects.none()
        tasks = tasks.select_related(
            'created_by', 'assigned_to', 'assigned_to__department', 'department', 'priority', 'topic'
        ).prefetch_related(
            'comments__author', 'co_assignees', 'co_assignee_approvals__user',
            'dependencies__depends_on', 'blocking_dependencies__task'
        ).distinct()
    else:
        user_tasks_q = Q(assigned_to=user) | Q(co_assignees=user) | Q(created_by=user)
        if user.department:
            user_tasks_q &= (Q(department=user.department) | Q(department__isnull=True))
        tasks = Task.objects.filter(user_tasks_q).select_related(
            'created_by', 'assigned_to', 'department', 'priority', 'topic'
        ).prefetch_related(
            'comments__author', 'co_assignees', 'co_assignee_approvals__user',
            'dependencies__depends_on', 'blocking_dependencies__task'
        ).distinct()

    # Сбор уникальных месяцев для фильтра по месяцам
    MONTH_NAMES_RU_LIST = [
        'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
        'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
    ]
    base_dates = tasks.values_list('due_date', flat=True)
    unique_months = sorted(list({(d.year, d.month) for d in base_dates}), reverse=True)
    month_choices = [
        {
            'value': f"{y}-{m:02d}",
            'label': f"{MONTH_NAMES_RU_LIST[m-1]} {y}"
        }
        for y, m in unique_months
    ]

    status_filter = request.GET.get('status', 'all')
    if status_filter == 'all':
        # Требование 5: Все выполненные задачи убираются из графы "все задачи" и отображаются только в "выполнено"
        tasks = tasks.exclude(status='done')
    elif status_filter in ['assigned', 'pending_review', 'rework', 'done']:
        tasks = tasks.filter(status=status_filter)

    assignee_filter = request.GET.get('assignee', 'all')
    if is_admin and assignee_filter != 'all' and assignee_filter.isdigit():
        tasks = tasks.filter(assigned_to_id=int(assignee_filter))

    month_filter = request.GET.get('month', 'all')
    if month_filter != 'all' and '-' in month_filter:
        try:
            y, m = map(int, month_filter.split('-'))
            tasks = tasks.filter(due_date__year=y, due_date__month=m)
        except ValueError:
            pass

    priority_filter = request.GET.get('priority', 'all')
    if priority_filter != 'all' and priority_filter.isdigit():
        tasks = tasks.filter(priority_id=int(priority_filter))

    topic_filter = request.GET.get('topic', 'all')
    if topic_filter != 'all' and topic_filter.isdigit():
        tasks = tasks.filter(topic_id=int(topic_filter))

    # Аннотируем флаг is_updated и сортируем: обновлённые задачи идут первыми внутри месяца
    tasks = tasks.annotate(
        is_updated=Case(
            When(Exists(unread_subquery), then=Value(1)),
            default=Value(0),
            output_field=IntegerField()
        )
    ).order_by('due_date', '-is_updated', 'priority__code', '-created_at')

    today_date_str = timezone.localdate().strftime('%Y-%m-%d')
    today_date_display = timezone.localdate().strftime('%d.%m.%Y')
    theme_mode = request.session.get('theme_mode', 'dark')

    context = {
        'tasks': tasks,
        'priorities': priorities,
        'topics': topics,
        'is_admin': is_admin,
        'is_head': is_head_user(user),
        'department': department,
        'department_employees': department_employees,
        'today_date_str': today_date_str,
        'today_date_display': today_date_display,
        'status_filter': status_filter,
        'assignee_filter': assignee_filter,
        'month_filter': month_filter,
        'priority_filter': priority_filter,
        'topic_filter': topic_filter,
        'month_choices': month_choices,
        'error_message': error_message,
        'theme_mode': theme_mode,
        'today_phrase': get_random_today_phrase(user),
        'user_unread_tasks_count': get_user_unread_tasks_count(user),
    }
    return render(request, 'accounts/time_manager.html', context)


@login_required
@require_POST
def edit_task(request, task_id):
    """
    Редактирование задачи — доступно администраторам и создателю задачи.
    """
    task = get_object_or_404(Task, pk=task_id)
    user = request.user
    if not user_can_access_task(user, task):
        return JsonResponse({'success': False, 'message': 'Нет доступа к этой задаче.'}, status=403)

    is_admin = is_admin_user(user)

    if not (is_admin or task.created_by == user):
        return JsonResponse({'success': False, 'message': 'Только администратор или создатель задачи может её редактировать.'}, status=403)

    title = request.POST.get('title', '').strip()
    description = request.POST.get('description', '').strip()
    due_date_str = request.POST.get('due_date', '').strip()
    assigned_to_id = request.POST.get('assigned_to')
    priority_id = request.POST.get('priority')
    topic_id = request.POST.get('topic')
    schedule_type = request.POST.get('schedule_type', 'off_schedule')
    schedule_number = request.POST.get('schedule_number', '').strip()
    archive_url = request.POST.get('archive_url', '').strip()
    co_assignees_ids = request.POST.getlist('co_assignees') if is_admin else []

    if not title or not due_date_str:
        return JsonResponse({'success': False, 'message': 'Заполните заголовок и дату выполнения.'}, status=400)

    try:
        if '.' in due_date_str:
            due_date = datetime.strptime(due_date_str, '%d.%m.%Y').date()
        else:
            due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()

        changes_list = []

        if task.title != title:
            changes_list.append(f"Заголовок: «{task.title}» ➔ «{title}»")
            task.title = title

        if task.description != description:
            changes_list.append("Обновлено описание задачи")
            task.description = description

        if task.due_date != due_date:
            changes_list.append(f"Срок выполнения: {task.due_date.strftime('%d.%m.%Y')} ➔ {due_date.strftime('%d.%m.%Y')}")
            task.due_date = due_date

        if priority_id:
            new_priority = TaskPriority.objects.filter(pk=priority_id).first()
            if new_priority and task.priority != new_priority:
                old_p = task.priority.name if task.priority else "Не указан"
                changes_list.append(f"Приоритет: «{old_p}» ➔ «{new_priority.name}»")
                task.priority = new_priority

        if 'topic' in request.POST:
            new_topic = TaskTopic.objects.filter(pk=topic_id).first() if topic_id else None
            if task.topic != new_topic:
                old_t = task.topic.name if task.topic else "Без темы"
                new_t = new_topic.name if new_topic else "Без темы"
                changes_list.append(f"Тема: «{old_t}» ➔ «{new_t}»")
                task.topic = new_topic

        if task.schedule_type != schedule_type or task.schedule_number != schedule_number or task.archive_url != archive_url:
            changes_list.append(f"Обновлены настройки графика (График: {dict(Task.SCHEDULE_CHOICES).get(schedule_type, schedule_type)})")
            task.schedule_type = schedule_type
            task.schedule_number = schedule_number
            task.archive_url = archive_url

        if is_admin and assigned_to_id:
            if user.department:
                assigned_user = get_object_or_404(User, pk=assigned_to_id, department=user.department)
            else:
                assigned_user = get_object_or_404(User, pk=assigned_to_id)
            if task.assigned_to != assigned_user:
                changes_list.append(f"Ответственный: «{task.assigned_to}» ➔ «{assigned_user}»")
                task.assigned_to = assigned_user

        # Дополнительные исполнители (выбирает только администратор)
        if is_admin:
            if co_assignees_ids:
                if user.department:
                    co_users = list(User.objects.filter(pk__in=co_assignees_ids, department=user.department))
                else:
                    co_users = list(User.objects.filter(pk__in=co_assignees_ids))
            else:
                co_users = []
            current_co = set(task.co_assignees.all())
            new_co = set(co_users)
            if current_co != new_co:
                task.co_assignees.set(co_users)
                TaskCoAssigneeApproval.objects.filter(task=task).exclude(user__in=co_users).delete()
                for cu in co_users:
                    TaskCoAssigneeApproval.objects.get_or_create(task=task, user=cu, defaults={'is_approved': False})

        # Хронологические зависимости
        if 'dependencies' in request.POST:
            dependencies_raw = request.POST.get('dependencies', '').strip()
            try:
                new_deps = json.loads(dependencies_raw) if dependencies_raw else []
                validate_dependencies_no_cycle(task.id, new_deps)

                valid_new = []
                for d in new_deps:
                    t_id = d.get('depends_on_id')
                    if t_id:
                        try:
                            t_id = int(t_id)
                        except (ValueError, TypeError):
                            continue
                        if t_id == task.id:
                            continue
                        target_t = Task.objects.filter(pk=t_id).first()
                        if target_t:
                            rel_type = d.get('relation_type', TaskDependency.RELATION_FS)
                            if rel_type not in dict(TaskDependency.RELATION_CHOICES):
                                rel_type = TaskDependency.RELATION_FS
                            lag_lead = int(d.get('lag_lead_days', 0))
                            valid_new.append((target_t, rel_type, lag_lead))

                existing_deps = list(task.dependencies.all())
                existing_map = {dep.depends_on_id: dep for dep in existing_deps}
                new_target_ids = {t.id for t, _, _ in valid_new}

                deps_changed = False
                for dep in existing_deps:
                    if dep.depends_on_id not in new_target_ids:
                        dep.delete()
                        deps_changed = True

                for target_t, rel_type, lag_lead in valid_new:
                    dep = existing_map.get(target_t.id)
                    if dep:
                        if dep.relation_type != rel_type or dep.lag_lead_days != lag_lead:
                            dep.relation_type = rel_type
                            dep.lag_lead_days = lag_lead
                            dep.save()
                            deps_changed = True
                    else:
                        TaskDependency.objects.create(
                            task=task,
                            depends_on=target_t,
                            relation_type=rel_type,
                            lag_lead_days=lag_lead
                        )
                        deps_changed = True

                if deps_changed:
                    dep_desc = []
                    for t, r, l in valid_new:
                        off_str = f" ({l:+d} дн.)" if l != 0 else ""
                        dep_desc.append(f"#{t.id} [{r}]{off_str}")
                    changes_list.append(f"Обновлены связи и зависимости: {', '.join(dep_desc) if dep_desc else 'удалены все'}")
            except ValueError as ve:
                return JsonResponse({'success': False, 'message': str(ve)}, status=400)
            except Exception as e:
                return JsonResponse({'success': False, 'message': f'Ошибка при обработке связей: {str(e)}'}, status=400)

        task.save()

        if changes_list:
            actor_name = f"{user.first_name} {user.last_name}".strip() or user.username
            log_task_history(task, user, "Редактирование задачи", f"Пользователь {actor_name} изменил: " + "; ".join(changes_list))
            notify_task_changed(task, actor=user, change_detail=f"Изменения от {actor_name}")

        return JsonResponse({'success': True, 'message': 'Задача успешно обновлена.'})
    except ValueError as e:
        msg = str(e) if str(e) else 'Неверный формат даты выполнения.'
        return JsonResponse({'success': False, 'message': msg}, status=400)


@login_required
@require_POST
def add_task_comment(request, task_id):
    """
    Добавление комментария к задаче — доступно создателю, исполнителю, ДИ и администратору.
    """
    task = get_object_or_404(Task, pk=task_id)
    user = request.user
    if not user_can_access_task(user, task):
        return JsonResponse({'success': False, 'message': 'Нет прав для комментирования этой задачи.'}, status=403)

    is_admin = is_admin_user(user)

    can_comment = (
        task.created_by == user or
        task.assigned_to == user or
        user in task.co_assignees.all() or
        is_admin
    )
    if not can_comment:
        return JsonResponse({'success': False, 'message': 'Нет прав для комментирования этой задачи.'}, status=403)

    text = request.POST.get('text', '').strip()
    if not text:
        return JsonResponse({'success': False, 'message': 'Текст комментария не может быть пустым.'}, status=400)

    comment = TaskComment.objects.create(
        task=task,
        author=user,
        text=text
    )

    author_name = f"{comment.author.first_name} {comment.author.last_name}".strip() or comment.author.username

    log_task_history(task, user, "Добавлен комментарий", f"{author_name}: «{text}»")

    notify_task_changed(task, actor=user, change_detail=f"Новый комментарий от {author_name}")

    return JsonResponse({
        'success': True,
        'comment_id': comment.id,
        'author_id': comment.author.id,
        'author_name': author_name,
        'author_color': comment.author.effective_chat_color,
        'created_at': comment.created_at.strftime('%d.%m.%Y %H:%M'),
        'text': comment.text
    })


@login_required
@require_POST
def edit_task_comment(request, comment_id):
    """
    Редактирование комментария к задаче — доступно автору комментария
    до тех пор, пока нет более новых комментариев.
    """
    comment = get_object_or_404(TaskComment, pk=comment_id)
    user = request.user

    if comment.author != user:
        return JsonResponse({'success': False, 'message': 'Вы можете редактировать только свои комментарии.'}, status=403)

    has_newer = TaskComment.objects.filter(task=comment.task, id__gt=comment.id).exists()
    if has_newer:
        return JsonResponse({'success': False, 'message': 'Нельзя редактировать комментарий, если уже есть более новые комментарии.'}, status=400)

    text = request.POST.get('text', '').strip()
    if not text:
        return JsonResponse({'success': False, 'message': 'Текст комментария не может быть пустым.'}, status=400)

    comment.text = text
    comment.save()

    author_name = f"{user.first_name} {user.last_name}".strip() or user.username
    log_task_history(comment.task, user, "Отредактирован комментарий", f"{author_name}: «{text}»")
    notify_task_changed(comment.task, actor=user, change_detail=f"Отредактирован комментарий: {author_name}")

    return JsonResponse({
        'success': True,
        'comment_id': comment.id,
        'text': comment.text
    })


@login_required
@require_POST
def delete_task_comment(request, comment_id):
    """
    Удаление комментария к задаче — доступно автору комментария
    до тех пор, пока нет более новых комментариев.
    """
    comment = get_object_or_404(TaskComment, pk=comment_id)
    user = request.user

    if comment.author != user:
        return JsonResponse({'success': False, 'message': 'Вы можете удалять только свои комментарии.'}, status=403)

    has_newer = TaskComment.objects.filter(task=comment.task, id__gt=comment.id).exists()
    if has_newer:
        return JsonResponse({'success': False, 'message': 'Нельзя удалить комментарий, если уже есть более новые комментарии.'}, status=400)

    task = comment.task
    comment.delete()

    author_name = f"{user.first_name} {user.last_name}".strip() or user.username
    log_task_history(task, user, "Удален комментарий", f"Комментарий автора {author_name} удален")

    return JsonResponse({
        'success': True,
        'task_id': task.id,
        'comments_count': task.comments.count()
    })


@login_required
@require_POST
def update_task_status(request, task_id):
    """
    Изменение статуса задачи (AJAX / POST).
    """
    task = get_object_or_404(Task, pk=task_id)
    user = request.user
    if not user_can_access_task(user, task):
        return JsonResponse({'success': False, 'message': 'Нет доступа к этой задаче.'}, status=403)

    is_assignee = (task.assigned_to == user)
    is_creator = (task.created_by == user)
    is_co_assignee = task.co_assignees.filter(pk=user.pk).exists()
    is_admin = is_admin_user(user)
    is_head = is_head_user(user)

    # Доп. исполнитель не может менять статус задачи, он может только согласовать за себя
    if is_co_assignee and not (is_assignee or is_creator or is_admin):
        return JsonResponse({'success': False, 'message': 'Дополнительные исполнители не могут менять статус задачи, а только согласовать её.'}, status=403)

    can_interact = is_assignee or is_creator or is_admin
    if not can_interact:
        return JsonResponse({'success': False, 'message': 'Нет прав для изменения этой задачи.'}, status=403)

    new_status = request.POST.get('status')
    if new_status not in ['assigned', 'pending_review', 'rework', 'done']:
        return JsonResponse({'success': False, 'message': 'Недопустимый статус.'}, status=400)

    # Отправить на проверку может только ответственный исполнитель (или начальник подразделения)
    if new_status == 'pending_review' and not is_assignee and not is_head:
        return JsonResponse({'success': False, 'message': 'Только ответственный исполнитель может отправить задачу на проверку.'}, status=403)

    # Только начальник подразделения может перевести задачу в выполнено (Администратор НЕ может)
    if new_status == 'done' and not is_head:
        return JsonResponse({'success': False, 'message': 'Только начальник подразделения может перевести задачу в статус "Выполнено".'}, status=403)

    # Если есть ДИ и они не все согласовали — передавать на проверку/завершать нельзя!
    if new_status in ['pending_review', 'done']:
        if not task.co_assignees_all_approved:
            pending_co = task.co_assignee_approvals.filter(is_approved=False).select_related('user')
            names = ", ".join([f"{a.user.first_name} {a.user.last_name}".strip() or a.user.username for a in pending_co])
            return JsonResponse({
                'success': False,
                'message': f'Нельзя передать задачу на проверку или завершить, пока все дополнительные исполнители не согласуют её. Ожидается от: {names}.'
            }, status=403)

    old_status_display = task.get_status_display()

    if is_assignee and not is_creator and not is_admin:
        if task.status in ['pending_review', 'done']:
            return JsonResponse({'success': False, 'message': 'Задача находится на проверке или уже выполнена. Изменение статуса недоступно.'}, status=403)

        if new_status in ['pending_review', 'done']:
            task.status = 'pending_review'
            task.last_change_detail = "Отправлено на проверку"
        else:
            task.status = new_status
            task.last_change_detail = f"Статус изменён на «{task.get_status_display()}»"
    else:
        task.status = new_status
        if new_status == 'done':
            task.last_change_detail = "Выполнение подтверждено (Выполнено)"
        elif new_status == 'rework':
            task.last_change_detail = "Возвращено на доработку"
        elif new_status == 'pending_review':
            task.last_change_detail = "Отправлено на проверку"
        else:
            task.last_change_detail = f"Статус изменён на «{task.get_status_display()}»"

    # При переходе в статус на доработке согласование доп исполнителями сбрасывается
    if new_status == 'rework':
        task.co_assignee_approvals.update(is_approved=False, approved_at=None)

    actor_name = f"{user.first_name} {user.last_name}".strip() or user.username
    new_status_display = task.get_status_display()
    log_task_history(task, user, "Изменение статуса", f"Пользователь {actor_name} изменил статус с «{old_status_display}» на «{new_status_display}».")

    notify_task_changed(task, actor=user, change_detail=task.last_change_detail)

    return JsonResponse({'success': True, 'status': task.status, 'status_display': task.get_status_display()})


@login_required
@require_POST
def delete_task(request, task_id):
    """
    Удаление задачи.
    """
    task = get_object_or_404(Task, pk=task_id)
    user = request.user
    if not user_can_access_task(user, task):
        return JsonResponse({'success': False, 'message': 'Нет прав для удаления этой задачи.'}, status=403)

    is_admin = is_admin_user(user)

    can_delete = (
        task.created_by == user or
        task.assigned_to == user or
        is_admin
    )
    if not can_delete:
        return JsonResponse({'success': False, 'message': 'Нет прав для удаления этой задачи.'}, status=403)

    log_task_history(task, user, "Удаление задачи", f"Задача «{task.title}» была удалена пользователем {user}.")
    task.delete()
    return JsonResponse({'success': True, 'message': 'Задача удалена.'})


@login_required
@require_POST
def approve_co_assignee(request, task_id):
    """
    Согласование задачи дополнительным исполнителем.
    """
    task = get_object_or_404(Task, pk=task_id)
    user = request.user
    if not user_can_access_task(user, task):
        return JsonResponse({'success': False, 'message': 'Нет доступа к этой задаче.'}, status=403)

    is_admin = is_admin_user(user)
    is_co = task.co_assignees.filter(pk=user.pk).exists()

    if not is_co and not is_admin:
        return JsonResponse({'success': False, 'message': 'Вы не являетесь дополнительным исполнителем этой задачи.'}, status=403)

    target_user = user
    if is_admin and not is_co:
        # Если администратор согласовывает за сотрудника или себя
        task.co_assignees.add(user)

    approval, created = TaskCoAssigneeApproval.objects.get_or_create(task=task, user=target_user)
    approval.is_approved = True
    approval.approved_at = timezone.now()
    approval.save()

    actor_name = f"{user.first_name} {user.last_name}".strip() or user.username
    log_task_history(task, user, "Согласование дополнительного исполнителя", f"Дополнительный исполнитель {actor_name} согласовал задачу.")

    notify_task_changed(task, actor=user, change_detail=f"Согласовано доп. исполнителем: {actor_name}")

    return JsonResponse({'success': True, 'message': 'Задача успешно согласована.'})


@login_required
def get_task_history(request, task_id):
    """
    Получение хронологии (истории) по задаче.
    """
    task = get_object_or_404(Task, pk=task_id)
    user = request.user
    if not user_can_access_task(user, task):
        return JsonResponse({'success': False, 'message': 'Нет доступа к истории этой задачи.'}, status=403)

    history_qs = task.history.select_related('actor').order_by('created_at')
    history_list = []
    for item in history_qs:
        actor_name = (f"{item.actor.first_name} {item.actor.last_name}".strip() or item.actor.username) if item.actor else "Система"
        local_time = timezone.localtime(item.created_at)
        history_list.append({
            'created_at': local_time.strftime('%d.%m.%Y %H:%M'),
            'date': local_time.strftime('%d.%m.%Y %H:%M'),
            'actor_name': actor_name,
            'actor': actor_name,
            'action_type': item.action_type,
            'description': item.description,
        })

    return JsonResponse({'success': True, 'task_title': task.title, 'history': history_list})


@login_required
@require_POST
def clear_head_notifications(request):
    """
    Сброс всех уведомлений и меток об изменении задач для текущего пользователя.
    Не затрагивает уведомления других пользователей!
    """
    user = request.user
    mark_all_tasks_read_for_user(user)
    return JsonResponse({'success': True})


@login_required
def get_task_details(request, task_id):
    """
    Получение полных данных по задаче для отображения в полноэкранном режиме с чатом.
    """
    task = get_object_or_404(
        Task.objects.select_related('created_by', 'assigned_to', 'priority', 'department', 'topic')
                    .prefetch_related(
                        'comments__author', 'co_assignees', 'co_assignee_approvals__user',
                        'dependencies__depends_on', 'blocking_dependencies__task'
                    ),
        pk=task_id
    )
    user = request.user
    if not user_can_access_task(user, task):
        return JsonResponse({'success': False, 'message': 'Нет доступа к этой задаче.'}, status=403)

    is_admin = is_admin_user(user)
    is_head = is_head_user(user)

    is_assignee = (task.assigned_to == user)
    is_creator = (task.created_by == user)
    is_co_assignee = task.co_assignees.filter(pk=user.pk).exists()

    # Сбор комментариев
    comments_data = []
    comments_list = list(task.comments.all())
    total_comments = len(comments_list)
    for idx, c in enumerate(comments_list):
        c_author_name = f"{c.author.first_name} {c.author.last_name}".strip() or c.author.username
        c_time = timezone.localtime(c.created_at).strftime('%d.%m.%Y %H:%M')
        is_last = (idx == total_comments - 1)
        comments_data.append({
            'id': c.id,
            'author_id': c.author.id,
            'author_name': c_author_name,
            'author_color': c.author.effective_chat_color,
            'is_current_user': (c.author == user),
            'is_last': is_last,
            'created_at': c_time,
            'text': c.text,
        })

    # Согласования ДИ
    approvals_data = []
    for app in task.co_assignee_approvals.all():
        app_user_name = f"{app.user.first_name} {app.user.last_name}".strip() or app.user.username
        approvals_data.append({
            'user_id': app.user.id,
            'user_name': app_user_name,
            'is_approved': app.is_approved,
            'is_current_user': (app.user == user),
            'approved_at': timezone.localtime(app.approved_at).strftime('%d.%m.%Y %H:%M') if app.approved_at else None,
        })

    # Доп. исполнители
    co_assignees_data = []
    for ca in task.co_assignees.all():
        ca_name = f"{ca.first_name} {ca.last_name}".strip() or ca.username
        co_assignees_data.append({
            'id': ca.id,
            'name': ca_name,
        })

    # Зависимости
    dependencies_data = []
    for dep in task.dependencies.select_related('depends_on').all():
        d_task = dep.depends_on
        dependencies_data.append({
            'id': dep.id,
            'target_task_id': d_task.id,
            'target_task_title': d_task.title,
            'target_task_status': d_task.status,
            'target_task_status_display': d_task.get_status_display(),
            'target_task_due_date': d_task.due_date.strftime('%d.%m.%Y') if d_task.due_date else '',
            'target_task_due_date_iso': d_task.due_date.strftime('%Y-%m-%d') if d_task.due_date else '',
            'relation_type': dep.relation_type,
            'relation_type_display': dep.get_relation_type_display(),
            'lag_lead_days': dep.lag_lead_days,
        })

    blocked_tasks_data = []
    for dep in task.blocking_dependencies.select_related('task').all():
        b_task = dep.task
        blocked_tasks_data.append({
            'id': dep.id,
            'task_id': b_task.id,
            'task_title': b_task.title,
            'task_status': b_task.status,
            'task_status_display': b_task.get_status_display(),
            'task_due_date': b_task.due_date.strftime('%d.%m.%Y') if b_task.due_date else '',
            'relation_type': dep.relation_type,
            'relation_type_display': dep.get_relation_type_display(),
            'lag_lead_days': dep.lag_lead_days,
        })

    # Права на действия
    can_approve = is_co_assignee and not task.co_assignee_approvals.filter(user=user, is_approved=True).exists()
    can_comment = is_creator or is_assignee or is_co_assignee or is_admin
    can_edit = is_admin or is_creator
    can_delete = is_admin or is_creator

    # Доступные кнопки изменения статуса
    status_actions = []
    if is_head:
        if task.status == 'pending_review':
            status_actions.append({'status': 'done', 'label': 'Подтвердить', 'class': 'bg-emerald-600 hover:bg-emerald-700', 'icon': 'check_circle'})
            status_actions.append({'status': 'rework', 'label': 'Вернуть на доработку', 'class': 'bg-orange-600 hover:bg-orange-700', 'icon': 'replay'})
        elif task.status in ['assigned', 'rework']:
            status_actions.append({'status': 'done', 'label': 'Выполнено', 'class': 'bg-emerald-600 hover:bg-emerald-700', 'icon': 'check_circle'})
        elif task.status == 'done':
            status_actions.append({'status': 'rework', 'label': 'На доработку', 'class': 'bg-orange-600 hover:bg-orange-700', 'icon': 'replay'})
    elif is_assignee:
        if task.status in ['assigned', 'rework']:
            status_actions.append({'status': 'pending_review', 'label': 'Отправить на проверку', 'class': 'bg-purple-600 hover:bg-purple-700', 'icon': 'send'})
    elif is_admin or is_creator:
        if task.status == 'pending_review':
            status_actions.append({'status': 'rework', 'label': 'Вернуть на доработку', 'class': 'bg-orange-600 hover:bg-orange-700', 'icon': 'replay'})

    creator_name = (f"{task.created_by.first_name} {task.created_by.last_name}".strip() or task.created_by.username) if task.created_by else "—"
    assignee_name = (f"{task.assigned_to.first_name} {task.assigned_to.last_name}".strip() or task.assigned_to.username) if task.assigned_to else "Не назначен"

    return JsonResponse({
        'success': True,
        'task': {
            'id': task.id,
            'title': task.title,
            'description': task.description or '',
            'status': task.status,
            'status_display': task.get_status_display(),
            'department': {
                'id': task.department.id,
                'name': task.department.name,
            } if task.department else None,
            'topic': {
                'id': task.topic.id,
                'name': task.topic.name,
            } if task.topic else None,
            'priority': {
                'id': task.priority.id,
                'name': task.priority.name,
                'color_code': task.priority.color_code,
            } if task.priority else None,
            'schedule_type': task.schedule_type,
            'schedule_type_display': dict(Task.SCHEDULE_CHOICES).get(task.schedule_type, task.schedule_type),
            'schedule_number': task.schedule_number or '',
            'archive_url': task.archive_url or '',
            'due_date': task.due_date.strftime('%d.%m.%Y') if task.due_date else '—',
            'due_date_iso': task.due_date.strftime('%Y-%m-%d') if task.due_date else '',
            'created_at': timezone.localtime(task.created_at).strftime('%d.%m.%Y %H:%M') if task.created_at else '—',
            'days_left': task.days_left if task.due_date else 999,
            'overdue_days': task.overdue_days if task.due_date else 0,
            'is_updated': TaskUserNotification.objects.filter(task=task, user=user, is_read=False).exists(),
            'last_change_detail': task.last_change_detail or '',
            'creator': {
                'id': task.created_by.id if task.created_by else None,
                'name': creator_name,
            },
            'assignee': {
                'id': task.assigned_to.id if task.assigned_to else None,
                'name': assignee_name,
                'is_current_user': is_assignee,
            },
            'co_assignees': co_assignees_data,
            'approvals': approvals_data,
            'dependencies': dependencies_data,
            'blocked_tasks': blocked_tasks_data,
            'comments': comments_data,
            'comments_count': total_comments,
            'permissions': {
                'can_approve': can_approve,
                'can_comment': can_comment,
                'can_edit': can_edit,
                'can_delete': can_delete,
                'is_admin': is_admin,
                'is_head': is_head,
                'is_assignee': is_assignee,
                'is_creator': is_creator,
                'status_actions': status_actions,
            }
        }
    })


@login_required
def get_task_comments_updates(request, task_id):
    """
    Легковесный эндпоинт для smart polling комментариев конкретной задачи.
    Возвращает новые комментарии (с id > since_id) и актуальное общее количество.
    """
    task = get_object_or_404(Task, pk=task_id)
    user = request.user
    if not user_can_access_task(user, task):
        return JsonResponse({'success': False, 'message': 'Нет доступа.'}, status=403)

    try:
        since_id = int(request.GET.get('since_id', 0))
    except (ValueError, TypeError):
        since_id = 0

    total_count = task.comments.count()
    new_comments_qs = task.comments.filter(id__gt=since_id).select_related('author').order_by('created_at', 'id')
    
    new_comments_data = []
    for c in new_comments_qs:
        c_author_name = (f"{c.author.first_name} {c.author.last_name}".strip() or c.author.username) if c.author else "Аноним"
        new_comments_data.append({
            'id': c.id,
            'author_id': c.author.id if c.author else None,
            'author_name': c_author_name,
            'author_color': c.author.effective_chat_color if c.author else '#2563eb',
            'is_current_user': (c.author == user),
            'created_at': timezone.localtime(c.created_at).strftime('%d.%m.%Y %H:%M'),
            'text': c.text,
        })

    return JsonResponse({
        'success': True,
        'task_id': task.id,
        'total_count': total_count,
        'new_comments': new_comments_data,
    })


@login_required
def get_tasks_comments_counts(request):
    """
    Легковесный опрос счетчиков и новых сообщений по всем видимым пользователю задачам
    для фонового обновления карточек на доске.
    """
    user = request.user
    is_admin = is_admin_user(user)

    if is_admin:
        if user.department:
            tasks = Task.objects.filter(department=user.department)
        elif user.is_superuser:
            tasks = Task.objects.all()
        else:
            tasks = Task.objects.none()
    else:
        user_tasks_q = Q(assigned_to=user) | Q(co_assignees=user) | Q(created_by=user)
        if user.department:
            user_tasks_q &= (Q(department=user.department) | Q(department__isnull=True))
        tasks = Task.objects.filter(user_tasks_q).distinct()

    counts = dict(tasks.annotate(c_count=Count('comments')).values_list('id', 'c_count'))

    try:
        since_id = int(request.GET.get('since_id', 0))
    except (ValueError, TypeError):
        since_id = 0

    latest_comment_id = TaskComment.objects.filter(task__in=tasks).aggregate(Max('id'))['id__max'] or 0

    new_comments_data = []
    if since_id > 0:
        new_comments_qs = TaskComment.objects.filter(
            task__in=tasks,
            id__gt=since_id
        ).select_related('author', 'task').order_by('created_at', 'id')

        for c in new_comments_qs:
            c_author_name = (f"{c.author.first_name} {c.author.last_name}".strip() or c.author.username) if c.author else "Аноним"
            new_comments_data.append({
                'id': c.id,
                'task_id': c.task_id,
                'author_id': c.author.id if c.author else None,
                'author_name': c_author_name,
                'author_color': c.author.effective_chat_color if c.author else '#2563eb',
                'is_current_user': (c.author == user),
                'created_at': timezone.localtime(c.created_at).strftime('%d.%m.%Y %H:%M'),
                'text': c.text,
            })

    return JsonResponse({
        'success': True,
        'counts': counts,
        'latest_comment_id': latest_comment_id,
        'new_comments': new_comments_data,
    })


@login_required
def search_tasks_for_dependencies(request):
    """
    Живой поиск задач для автокомплита в блоке зависимостей.
    """
    q = request.GET.get('q', '').strip()
    exclude_id = request.GET.get('exclude_id', '').strip()

    user = request.user
    is_admin = is_admin_user(user)

    if is_admin:
        if user.department:
            tasks_qs = Task.objects.filter(department=user.department)
        else:
            tasks_qs = Task.objects.all()
    else:
        user_tasks_q = Q(assigned_to=user) | Q(co_assignees=user) | Q(created_by=user)
        if user.department:
            user_tasks_q &= (Q(department=user.department) | Q(department__isnull=True))
        tasks_qs = Task.objects.filter(user_tasks_q)

    if exclude_id and exclude_id.isdigit():
        tasks_qs = tasks_qs.exclude(pk=int(exclude_id))

    if q:
        clean_q = q.lstrip('#').strip()
        q_filter = Q(title__icontains=q)
        if clean_q.isdigit():
            q_filter |= Q(pk=int(clean_q))
        tasks_qs = tasks_qs.filter(q_filter)

    tasks_qs = tasks_qs.select_related('assigned_to', 'priority').order_by(
        Case(When(status='done', then=Value(1)), default=Value(0), output_field=IntegerField()),
        '-created_at'
    )[:30]

    data = [
        {
            'id': t.id,
            'title': t.title,
            'status': t.status,
            'status_display': t.get_status_display(),
            'is_done': (t.status == 'done'),
            'due_date': t.due_date.strftime('%d.%m.%Y') if t.due_date else '',
            'due_date_iso': t.due_date.strftime('%Y-%m-%d') if t.due_date else '',
        }
        for t in tasks_qs
    ]

    return JsonResponse({'success': True, 'tasks': data})








