# accounts/views.py

import locale
import json
import calendar
import csv
import chardet # Добавляем новый импорт для определения кодировки

from django.shortcuts import render, redirect, get_object_or_404
from .utils import get_current_week_dates, get_week_range  # Убедитесь, что get_week_range есть в utils
from django.contrib.auth import login, logout, authenticate, get_user_model
from .forms import UserRegisterForm, UserLoginForm
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from datetime import datetime, timedelta, date
from django.utils import timezone
from .models import WorkDay, Action
from itertools import zip_longest

try:
    locale.setlocale(locale.LC_ALL, 'ru_RU.UTF-8')  # Для Linux/macOS
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, 'Russian_Russia.1251')  # Для Windows (или 'ru_RU')
    except locale.Error:
        print("Не удалось установить русскую локаль для strftime.")

User = get_user_model()


# --- Вспомогательная функция для расчета времени ---
def time_to_timedelta(time_obj):
    """Преобразует объект time в timedelta."""
    return timedelta(hours=time_obj.hour, minutes=time_obj.minute, seconds=time_obj.second)


def timedelta_to_hms_str(td):
    """Преобразует timedelta в строку HH:MM:SS."""
    total_seconds = int(td.total_seconds())
    sign = "-" if total_seconds < 0 else ""
    total_seconds = abs(total_seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{sign}{hours:02}:{minutes:02}:{seconds:02}"


# --- Функции аутентификации ---
# Оставляем без изменений, как в предыдущих ответах
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


# --- Вспомогательная функция для определения диапазона недели ---
def get_week_range(date):
    start_of_week = date - timedelta(days=date.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    return start_of_week, end_of_week


def calculate_day_balance(workday_total_duration, day_type):
    """
    Рассчитывает "Баланс за день" согласно правилам.
    Возвращает timedelta и флаг is_negative.
    """
    standard_day_target = timedelta(hours=8)
    short_day_target = timedelta(hours=7)
    unpaid_break_threshold = timedelta(minutes=45)  # 45 минут неоплачиваемого перерыва, обед

    target_duration = timedelta(0)

    if day_type == 'ND':  # Обычный день
        target_duration = standard_day_target
        # if workday_total_duration < unpaid_break_threshold and workday_total_duration.total_seconds() > 0:
        #     target_duration = standard_day_target + unpaid_break_threshold
    elif day_type == 'SMD':  # Короткий день
        target_duration = short_day_target
        # if workday_total_duration < unpaid_break_threshold and workday_total_duration.total_seconds() > 0:
        #     target_duration = short_day_target + unpaid_break_threshold
    elif day_type in ['WD', 'HD', 'VL']:  # Выходной, Праздник, Отпуск - баланс всегда 0
        return timedelta(0), False

    balance = workday_total_duration - target_duration
    is_negative = balance < timedelta(0)

    return balance, is_negative


# --- Вспомогательная функция для определения диапазона недели ---
def get_week_range(date):
    start_of_week = date - timedelta(days=date.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    return start_of_week, end_of_week


# accounts/views.py

def calculate_total_time_for_workday(workday):
    """
    Рассчитывает общее время на территории за рабочий день.
    Учитывает пары Вход-Выход.
    """
    actions = workday.actions.order_by('time_stamp', 'order')
    total_duration = timedelta()
    outside_time_delta = timedelta()
    last_entry_time = None

    entry_time = []
    exit_time = []

    half_day_target = timedelta(hours=4)
    six_day_target = timedelta(hours=6)
    unpaid_mini_break_threshold = timedelta(hours=0, minutes=30)
    unpaid_break_threshold = timedelta(hours=0, minutes=45)

    for action in actions:
        if action.status_gate == 'EG':
            last_entry_time = action.time_stamp
            entry_time.append(action.time_stamp)
        elif action.status_gate == 'OG':
            exit_time.append(action.time_stamp)
            if last_entry_time and action.time_stamp > last_entry_time:
                total_duration += (action.time_stamp - last_entry_time)
                last_entry_time = None

    # Исправляем логику вычисления времени вне территории
    # Итерируемся по exit_time, чтобы убедиться, что для каждого выхода есть следующий вход
    if len(entry_time) > 1 and len(exit_time) > 0:
        for i in range(len(exit_time)):
            # Проверяем, что существует следующий entry
            if i + 1 < len(entry_time):
                outside_time_delta += (entry_time[i + 1] - exit_time[i])
            else:
                # Если нет следующего входа, выходим из цикла, чтобы избежать ошибки
                break

    # Оставшаяся часть функции без изменений
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


# accounts/views.py
import csv
from datetime import datetime, timedelta
from django.shortcuts import render
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from .models import WorkDay, Action
import chardet


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

                combined_dt = datetime.combine(date_obj, time_obj) + timedelta(hours=3)
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
            WorkDay.objects.filter(user=user, date_stamp=date_stamp).delete()

            workday = WorkDay.objects.create(
                user=user,
                date_stamp=date_stamp,
                type='ND'
            )

            actions_list.sort(key=lambda x: x['time_stamp'])

            entry_actions = [a for a in actions_list if a['status_gate'] == 'EG']
            exit_actions = [a for a in actions_list if a['status_gate'] == 'OG']

            num_pairs = min(len(entry_actions), len(exit_actions))

            for i in range(num_pairs):
                Action.objects.create(
                    workday=workday,
                    time_stamp=entry_actions[i]['time_stamp'],
                    status_gate='EG',
                    order=i
                )
                Action.objects.create(
                    workday=workday,
                    time_stamp=exit_actions[i]['time_stamp'],
                    status_gate='OG',
                    order=i
                )

            for i in range(num_pairs, len(entry_actions)):
                Action.objects.create(
                    workday=workday,
                    time_stamp=entry_actions[i]['time_stamp'],
                    status_gate='EG',
                    order=i
                )
            for i in range(num_pairs, len(exit_actions)):
                Action.objects.create(
                    workday=workday,
                    time_stamp=exit_actions[i]['time_stamp'],
                    status_gate='OG',
                    order=i
                )

        return JsonResponse({'success': True, 'message': 'Данные успешно импортированы!'})

    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Произошла ошибка при обработке файла: {e}'})
# @login_required
# def show_works_day(request):
#     """
#     Отображает таблицу с рабочим временем пользователя за выбранный месяц, сгруппированную по неделям.
#     """
#     selected_date_str = request.GET.get('date', None)
#     if selected_date_str:
#         try:
#             selected_date = datetime.fromisoformat(selected_date_str).date()
#         except ValueError:
#             selected_date = timezone.localdate()
#     else:
#         selected_date = timezone.localdate()
#
#     # Определяем диапазон дат для всего месяца
#     month_start_date = date(selected_date.year, selected_date.month, 1)
#     month_end_date = date(selected_date.year, selected_date.month,
#                           calendar.monthrange(selected_date.year, selected_date.month)[1])
#
#     # Получаем все WorkDay объекты для месяца заранее
#     all_workdays_in_month_dict = {
#         wd.date_stamp: wd for wd in WorkDay.objects.filter(
#             user=request.user,
#             date_stamp__gte=month_start_date,
#             date_stamp__lte=month_end_date
#         ).order_by('date_stamp')
#     }
#
#     # Формируем недели месяца, включая дни из предыдущего и следующего
#     month_weeks_data = []
#     # Начинаем с понедельника недели, в которую попадает 1-е число месяца
#     first_day_of_week = month_start_date - timedelta(days=month_start_date.weekday())
#     current_day = first_day_of_week
#
#     while current_day < month_end_date + timedelta(days=7):  # Итерируемся до конца месяца
#         week_dates = []
#         for i in range(7):
#             day_in_week = current_day + timedelta(days=i)
#             # Включаем все дни недели, независимо от месяца
#             week_dates.append(day_in_week)
#
#         month_weeks_data.append(week_dates)
#         current_day = current_day + timedelta(days=7)  # Переходим к началу следующей недели
#
#     # Подготовка данных для таблицы
#     weekly_table_rows = []
#     total_month_balance_td = timedelta(0)
#     current_cumulative_balance = timedelta(0)
#
#     for week_days in month_weeks_data:
#         week_row_types = []
#         week_row_times = []
#         week_row_total_time = []
#         week_row_day_balance = []
#         week_row_cumulative_balance = []
#         week_row_actions = []
#
#         for date_obj in week_days:
#             is_current_month = date_obj.month == selected_date.month
#
#             workday = all_workdays_in_month_dict.get(date_obj)
#
#             # Определяем тип дня по умолчанию, если workday еще не существует
#             if date_obj.weekday() >= 5:
#                 default_day_type = 'WD'
#             else:
#                 default_day_type = 'ND'
#
#             # Если workday не найден, создаем его для дней текущего месяца
#             if not workday and is_current_month:
#                 workday, created = WorkDay.objects.get_or_create(
#                     user=request.user,
#                     date_stamp=date_obj,
#                     defaults={'type': default_day_type}
#                 )
#
#             # Для дней вне текущего месяца, не создаем WorkDay, используем 'WD'
#             if not is_current_month:
#                 # Создаем "заглушку" для дня, чтобы отобразить его
#                 workday_data = {
#                     'id': None,
#                     'type': 'WD',  # Это позволит скрыть данные
#                     'date_stamp': date_obj
#                 }
#                 workday = type('WorkDay', (object,), workday_data)()
#
#             # --- Данные для столбца "Тип дня" ---
#             week_row_types.append({
#                 'id': workday.id,
#                 'type': workday.type if workday else 'WD',
#                 'display': dict(WorkDay.DAY_TYPE_CHOICES).get(workday.type, workday.type),
#                 'is_current_month': is_current_month
#             })
#
#             # --- Данные для столбца "Время" ---
#             if workday and workday.type not in ['WD', 'HD', 'VL']:
#                 entries_by_order = {a.order: a for a in workday.actions.filter(status_gate='EG').order_by('order')}
#                 exits_by_order = {a.order: a for a in workday.actions.filter(status_gate='OG').order_by('order')}
#
#                 combined_times = []
#                 max_order = max(max(entries_by_order.keys(), default=-1), max(exits_by_order.keys(), default=-1))
#
#                 for i in range(max_order + 1):
#                     entry = entries_by_order.get(i)
#                     exit_action = exits_by_order.get(i)
#
#                     if entry or exit_action:
#                         combined_times.append({
#                             'entry_time_id': entry.id if entry else None,
#                             'entry_time': entry.time_stamp.strftime('%H:%M') if entry else '',
#                             'exit_time_id': exit_action.id if exit_action else None,
#                             'exit_time': exit_action.time_stamp.strftime('%H:%M') if exit_action else '',
#                             'order': i,
#                             'day_id': workday.id
#                         })
#                 if not combined_times:
#                     combined_times.append({
#                         'entry_time_id': None, 'entry_time': '',
#                         'exit_time_id': None, 'exit_time': '', 'order': 0,
#                         'day_id': workday.id
#                     })
#                 week_row_times.append(combined_times)
#             else:
#                 week_row_times.append(None)  # Не выводим для выходных и дней вне месяца
#
#             # --- Данные для столбца "Итого за день" и "Баланс за день" ---
#             if workday and workday.type not in ['WD', 'HD', 'VL']:
#                 workday_total_duration = calculate_total_time_for_workday(workday)
#                 day_balance_td, is_negative_balance = calculate_day_balance(workday_total_duration, workday.type)
#
#                 # Добавляем к общему балансу за месяц
#                 total_month_balance_td += day_balance_td
#
#                 week_row_total_time.append({
#                     'id': workday.id,
#                     'value': timedelta_to_hms_str(workday_total_duration)
#                 })
#                 week_row_day_balance.append({
#                     'id': workday.id,
#                     'value': timedelta_to_hms_str(day_balance_td),
#                     'is_negative': is_negative_balance
#                 })
#             else:
#                 week_row_total_time.append(None)
#                 week_row_day_balance.append(None)
#
#             # --- Расчет и добавление накопительного баланса ---
#             if is_current_month:  # Вычисляем только для дней текущего месяца
#                 if workday and workday.type not in ['WD', 'HD', 'VL']:
#                     day_balance_td, is_negative_balance = calculate_day_balance(
#                         calculate_total_time_for_workday(workday), workday.type)
#                     current_cumulative_balance += day_balance_td
#                 else:
#                     # Если день нерабочий, баланс не меняется
#                     pass
#
#             is_cumulative_negative = current_cumulative_balance < timedelta(0)
#             week_row_cumulative_balance.append({
#                 'id': workday.id if workday else None,
#                 'value': timedelta_to_hms_str(current_cumulative_balance),
#                 'is_negative': is_cumulative_negative,
#                 'is_current_month': is_current_month
#             })
#
#             # --- Действия (кнопки) ---
#             week_row_actions.append({'id': workday.id, 'is_current_month': is_current_month})
#
#         # Добавляем сгруппированные данные недели в общий список
#         weekly_table_rows.append({
#             'dates': [{'date_obj': d, 'is_current_month': d.month == selected_date.month} for d in week_days],
#             'types': week_row_types,
#             'times': week_row_times,
#             'total_time': week_row_total_time,
#             'day_balance': week_row_day_balance,
#             'cumulative_balance': week_row_cumulative_balance,
#             'actions': week_row_actions,
#         })
#
#     total_month_balance_str = timedelta_to_hms_str(total_month_balance_td)
#     is_month_balance_negative = total_month_balance_td < timedelta(0)
#
#     current_month_name_formatted = selected_date.strftime('%B %Y').capitalize()
#
#     context = {
#         'weekly_table_rows': weekly_table_rows,
#         'current_user': request.user,
#         'current_month_display': current_month_name_formatted,
#         'total_month_balance': total_month_balance_str,
#         'is_month_balance_negative': is_month_balance_negative,
#         'selected_date': selected_date.isoformat(),
#     }
#     return render(request, 'accounts/index.html', context)
@login_required
def show_works_day(request):
    """
    Отображает таблицу с рабочим временем пользователя за выбранный месяц, сгруппированную по неделям.
    Дни из соседних месяцев отображаются серым, а лишние недели не создаются.
    """
    selected_date_str = request.GET.get('date', None)
    if selected_date_str:
        try:
            selected_date = datetime.fromisoformat(selected_date_str).date()
        except ValueError:
            selected_date = timezone.localdate()
    else:
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

    # Подготовка данных для таблицы
    weekly_table_rows = []
    total_month_balance_td = timedelta(0)
    current_cumulative_balance = timedelta(0)

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

            if date_obj.weekday() >= 5:
                default_day_type = 'WD'
            else:
                default_day_type = 'ND'

            if not workday and is_current_month:
                workday, created = WorkDay.objects.get_or_create(
                    user=request.user,
                    date_stamp=date_obj,
                    defaults={'type': default_day_type}
                )

            if not is_current_month:
                workday_data = {
                    'id': None,
                    'type': 'WD',
                    'date_stamp': date_obj
                }
                workday = type('WorkDay', (object,), workday_data)()

            week_row_types.append({
                'id': workday.id,
                'type': workday.type if workday else 'WD',
                'display': dict(WorkDay.DAY_TYPE_CHOICES).get(workday.type, workday.type),
                'is_current_month': is_current_month
            })

            if workday and workday.type not in ['WD', 'HD', 'VL']:
                entries_by_order = {a.order: a for a in workday.actions.filter(status_gate='EG').order_by('order')}
                exits_by_order = {a.order: a for a in workday.actions.filter(status_gate='OG').order_by('order')}

                combined_times = []
                max_order = max(max(entries_by_order.keys(), default=-1), max(exits_by_order.keys(), default=-1))

                for i in range(max_order + 1):
                    entry = entries_by_order.get(i)
                    exit_action = exits_by_order.get(i)

                    if entry or exit_action:
                        combined_times.append({
                            'entry_time_id': entry.id if entry else None,
                            'entry_time': entry.time_stamp.strftime('%H:%M') if entry else '',
                            'exit_time_id': exit_action.id if exit_action else None,
                            'exit_time': exit_action.time_stamp.strftime('%H:%M') if exit_action else '',
                            'order': i,
                            'day_id': workday.id,
                            'entry_type': entry.entry_type if entry else 'default'

                        })
                if not combined_times:
                    combined_times.append({
                        'entry_time_id': None, 'entry_time': '',
                        'exit_time_id': None, 'exit_time': '', 'order': 0,
                        'day_id': workday.id
                    })
                week_row_times.append(combined_times)
            else:
                week_row_times.append(None)

            if workday and workday.type not in ['WD', 'HD', 'VL']:
                workday_total_duration = calculate_total_time_for_workday(workday)
                day_balance_td, is_negative_balance = calculate_day_balance(workday_total_duration, workday.type)
                total_month_balance_td += day_balance_td
                week_row_total_time.append({
                    'id': workday.id,
                    'value': timedelta_to_hms_str(workday_total_duration)
                })
                week_row_day_balance.append({
                    'id': workday.id,
                    'value': timedelta_to_hms_str(day_balance_td),
                    'is_negative': is_negative_balance
                })
            else:
                week_row_total_time.append(None)
                week_row_day_balance.append(None)

            if is_current_month:
                if workday and workday.type not in ['WD', 'HD', 'VL']:
                    day_balance_td, _ = calculate_day_balance(calculate_total_time_for_workday(workday), workday.type)
                    current_cumulative_balance += day_balance_td
                is_cumulative_negative = current_cumulative_balance < timedelta(0)
                week_row_cumulative_balance.append({
                    'id': workday.id if workday else None,
                    'value': timedelta_to_hms_str(current_cumulative_balance),
                    'is_negative': is_cumulative_negative,
                    'is_current_month': is_current_month
                })
            else:
                week_row_cumulative_balance.append(None)

            week_row_actions.append({'id': workday.id, 'is_current_month': is_current_month})

        weekly_table_rows.append({
            'dates': [{'date_obj': d, 'is_current_month': d.month == selected_date.month} for d in week_days],
            'types': week_row_types,
            'times': week_row_times,
            'total_time': week_row_total_time,
            'day_balance': week_row_day_balance,
            'cumulative_balance': week_row_cumulative_balance,
            'actions': week_row_actions,
        })

    total_month_balance_str = timedelta_to_hms_str(total_month_balance_td)
    is_month_balance_negative = total_month_balance_td < timedelta(0)
    current_month_name_formatted = selected_date.strftime('%B %Y').capitalize()

    context = {
        'weekly_table_rows': weekly_table_rows,
        'current_user': request.user,
        'current_month_display': current_month_name_formatted,
        'total_month_balance': total_month_balance_str,
        'is_month_balance_negative': is_month_balance_negative,
        'selected_date': selected_date.isoformat(),
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

        workday = get_object_or_404(WorkDay, id=day_id, user=request.user)

        workday.type = day_type
        workday.save()

        # Удаляем существующие действия и добавляем новые
        workday.actions.all().delete()

        for entry in time_entries:
            time_str = entry.get('time')
            if time_str:
                combined_datetime_str = f"{workday.date_stamp.isoformat()} {time_str}:00"
                correct_dt = datetime.fromisoformat(combined_datetime_str) + timedelta(hours=3)
                aware_dt = timezone.make_aware(correct_dt)
                entry_type = entry.get('entry_type', 'default') # Получаем entry_type из запроса

                Action.objects.create(
                    workday=workday,
                    status_gate=entry.get('type'),
                    time_stamp=aware_dt,
                    entry_type=entry_type, # Сохраняем entry_type в базу
                    order=entry.get('order', 0)
                )

        # Пересчитываем общее время и баланс за день для текущего обновляемого дня
        workday_total_duration = calculate_total_time_for_workday(workday)
        new_total_time_str = timedelta_to_hms_str(workday_total_duration)

        day_balance_td, is_negative_balance = calculate_day_balance(workday_total_duration, workday.type)
        new_day_balance_str = timedelta_to_hms_str(day_balance_td)

        # Для баланса за месяц, нужно пересчитать все дни месяца
        selected_date_for_month = workday.date_stamp
        month_start_date = date(selected_date_for_month.year, selected_date_for_month.month, 1)
        month_end_date = date(selected_date_for_month.year, selected_date_for_month.month,
                              calendar.monthrange(selected_date_for_month.year, selected_date_for_month.month)[1])

        total_month_balance_td = timedelta(0)
        current_cumulative_balance_td = timedelta(0)

        all_workdays_in_month = WorkDay.objects.filter(
            user=request.user,
            date_stamp__gte=month_start_date,
            date_stamp__lte=month_end_date
        ).order_by('date_stamp')

        for wd_for_month_iter in all_workdays_in_month:
            current_day_total_duration = calculate_total_time_for_workday(wd_for_month_iter)
            current_day_type = wd_for_month_iter.type

            monthly_day_balance_td = timedelta(0)
            if current_day_type not in ['WD', 'HD', 'VL']:
                monthly_day_balance_td, _ = calculate_day_balance(current_day_total_duration, current_day_type)

            total_month_balance_td += monthly_day_balance_td
            current_cumulative_balance_td += monthly_day_balance_td

            # Если это тот день, который мы редактируем, сохраняем его накопительный баланс
            if wd_for_month_iter.id == workday.id:
                new_cumulative_balance_str = timedelta_to_hms_str(current_cumulative_balance_td)

        total_month_balance_str = timedelta_to_hms_str(total_month_balance_td)
        is_month_balance_negative = total_month_balance_td < timedelta(0)
        is_cumulative_balance_negative = current_cumulative_balance_td < timedelta(0)

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