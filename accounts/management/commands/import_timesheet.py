import csv
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.contrib.auth import get_user_model
from accounts.models import WorkDay, Action

User = get_user_model()


class Command(BaseCommand):
    help = 'Импортирует данные о рабочем времени из TSV-файла.'

    def add_arguments(self, parser):
        parser.add_argument('filepath', type=str, help='Путь к TSV-файлу для импорта')
        parser.add_argument('username', type=str, help='Имя пользователя, для которого импортируются данные')
        parser.add_argument('--encoding', type=str, default='utf-8', help='Кодировка файла (например, utf-8, cp1251)')

    def handle(self, *args, **options):
        filepath = options['filepath']
        username = options['username']
        encoding = options['encoding']

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f'Пользователь "{username}" не существует.')

        self.stdout.write(
            f'Импорт данных для пользователя: {user.username} из файла: {filepath} с кодировкой: {encoding}')

        try:
            with open(filepath, 'r', encoding=encoding) as tsvfile:
                reader = csv.reader(tsvfile, delimiter='\t')

                header = next(reader)

                workdays_data = {}

                for row in reader:
                    if not any(row):
                        continue

                    if len(row) < 3:
                        self.stderr.write(self.style.WARNING(f"Пропущена строка из-за неполных данных: {row}"))
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
                        self.stderr.write(self.style.ERROR(f"Ошибка при парсинге строки: {row}. Ошибка: {e}"))
                        continue

                for date_stamp, actions_list in workdays_data.items():
                    # Удаляем старые данные для этой даты
                    print(WorkDay.objects.filter(user=user, date_stamp=date_stamp,WORK_TYPE_CHOICES = 'default'))
                    WorkDay.objects.filter(user=user, date_stamp=date_stamp,WORK_TYPE_CHOICES = 'default').delete()

                    # Создаем новый WorkDay
                    workday = WorkDay.objects.create(
                        user=user,
                        date_stamp=date_stamp,
                        type='ND'  # Устанавливаем тип дня "Нормальный день"
                    )

                    # Сортируем действия по времени и группируем их
                    actions_list.sort(key=lambda x: x['time_stamp'])

                    entry_actions = [a for a in actions_list if a['status_gate'] == 'EG']
                    exit_actions = [a for a in actions_list if a['status_gate'] == 'OG']

                    # Группируем в пары, используя наименьшее количество входов или выходов
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

                    # Добавляем оставшиеся незавершенные действия (если есть)
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

            self.stdout.write(self.style.SUCCESS('Импорт данных завершен успешно!'))

        except FileNotFoundError:
            raise CommandError(f'Файл по пути "{filepath}" не найден.')
        except Exception as e:
            raise CommandError(f'Произошла ошибка при обработке файла: {e}')