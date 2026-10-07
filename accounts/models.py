# accounts/models.py

from django.db import models
from django.contrib.auth.models import AbstractUser # Если используете кастомного User
from django.conf import settings
from django.utils import timezone



class Department(models.Model):
    """
    Модель подразделения организации.
    """
    name = models.CharField(max_length=150, unique=True, verbose_name="Название подразделения")

    class Meta:
        verbose_name = "Подразделение"
        verbose_name_plural = "Подразделения"
        ordering = ['name']

    def __str__(self):
        return self.name


class ChatColor(models.Model):
    """
    Модель для управления доступными цветами сообщений в чате.
    Позволяет администраторам заводить новые цвета прямо из панели управления.
    """
    name = models.CharField(max_length=60, verbose_name="Название цвета")
    color_hex = models.CharField(
        max_length=20,
        unique=True,
        verbose_name="HEX-код цвета",
        help_text="Например: #3b82f6 или выберите из палитры"
    )
    order = models.IntegerField(default=0, verbose_name="Порядок сортировки")
    is_active = models.BooleanField(default=True, verbose_name="Активен")

    class Meta:
        verbose_name = "Цвет чата"
        verbose_name_plural = "Цвета чата"
        ordering = ['order', 'name', 'id']

    def __str__(self):
        return f"{self.name} ({self.color_hex})"


class User(AbstractUser):
    ACCOUNT_TYPE_CHOICES = [
        ('full_day', 'Полный день'),
        ('shortened', 'Сокращённый'),
        ('student', 'Студент'),
    ]
    account_type = models.CharField(
        max_length=15,
        choices=ACCOUNT_TYPE_CHOICES,
        default='full_day',
        verbose_name="Тип учетной записи"
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users',
        verbose_name="Подразделение"
    )
    is_department_head = models.BooleanField(
        default=False,
        verbose_name="Начальник подразделения"
    )
    is_administrator = models.BooleanField(
        default=False,
        verbose_name="Администратор"
    )
    tracker = models.CharField(
        max_length=100,
        default='Сегодня',
        verbose_name="Текст трекера"
    )

    CHAT_COLOR_CHOICES = [
        ('#2563eb', 'Синий (Классический)'),
        ('#4f46e5', 'Индиго'),
        ('#7c3aed', 'Фиолетовый'),
        ('#db2777', 'Розовый'),
        ('#059669', 'Изумрудный'),
        ('#0d9488', 'Морская волна'),
        ('#0891b2', 'Бирюзовый'),
        ('#d97706', 'Янтарный'),
        ('#ea580c', 'Оранжевый'),
        ('#e11d48', 'Коралловый'),
        ('#65a30d', 'Лайм'),
        ('#475569', 'Сланцевый'),
    ]
    chat_color = models.CharField(
        max_length=20,
        blank=True,
        default='',
        verbose_name="Цвет сообщений в чате"
    )

    def get_chat_color_display(self):
        if not self.chat_color:
            return "Автоматический"
        try:
            color = ChatColor.objects.filter(color_hex__iexact=self.chat_color).first()
            if color:
                return color.name
        except Exception:
            pass
        for hex_code, name in self.CHAT_COLOR_CHOICES:
            if hex_code.lower() == self.chat_color.lower():
                return name
        return self.chat_color

    @property
    def effective_chat_color(self):
        if self.chat_color:
            return self.chat_color
        try:
            active_colors = list(ChatColor.objects.filter(is_active=True).order_by('order', 'id').values_list('color_hex', flat=True))
        except Exception:
            active_colors = []
        if active_colors:
            palette = active_colors
        else:
            palette = [c[0] for c in self.CHAT_COLOR_CHOICES]
        user_id = self.id or 1
        return palette[user_id % len(palette)]

    def __str__(self):
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name if full_name else self.username


class WorkDay(models.Model):
    """
    Модель для хранения информации о рабочем дне пользователя.
    """
    DAY_TYPE_CHOICES = [
        ('ND', 'Рабочий день'),
        ('WD', 'Выходной'),
        ('HD', 'Праздник'),
        ('VL', 'Отпуск'),
        ('SMD', 'Короткий день'),
        ('ED', 'пустой день'),
        ('OT', 'Отгул'),
        ('MK','Больничный'),
        ('KMD','Командировка'),


    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='workdays', verbose_name="Пользователь")
    date_stamp = models.DateField(verbose_name="Дата")
    type = models.CharField(max_length=3, choices=DAY_TYPE_CHOICES, default='ND', verbose_name="Тип дня")

    class Meta:
        verbose_name = "Рабочий день"
        verbose_name_plural = "Рабочие дни"
        ordering = ['date_stamp']
        unique_together = ('user', 'date_stamp',) # Уникальность по пользователю и дате

    def __str__(self):
        return f"{self.user.username} - {self.date_stamp.strftime('%d.%m.%Y')} ({self.get_type_display()})"


class Action(models.Model):
    """
    Модель для хранения действий входа/выхода для каждого рабочего дня.
    """
    STATUS_GATE_CHOICES = [
        ('EG', 'Вход'),
        ('OG', 'Выход'),
    ]
    WORK_TYPE_CHOICES = [
        ('default', 'Обычное время'),
        ('mk', 'МК-время'),
    ]

    workday = models.ForeignKey(WorkDay, on_delete=models.CASCADE, related_name='actions', verbose_name="Рабочий день")
    time_stamp = models.DateTimeField(verbose_name="Время")
    status_gate = models.CharField(max_length=2, choices=STATUS_GATE_CHOICES, verbose_name="Статус")
    order = models.IntegerField(default=0, verbose_name="Порядок")
    entry_type = models.CharField(max_length=10, choices=WORK_TYPE_CHOICES, default='default', verbose_name="тип записи")
    is_calculated = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Действие"
        verbose_name_plural = "Действия"
        ordering = ['time_stamp', 'order']

    def __str__(self):
        local_time = timezone.localtime(self.time_stamp)
        return f"{self.workday.date_stamp.strftime('%d.%m.%Y')} - {self.get_status_gate_display()} в {local_time.strftime('%H:%M')}"


class MonthTransfer(models.Model):
    """
    Модель для переноса и добавления баланса времени между месяцами.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='month_transfers', verbose_name="Пользователь")
    from_year = models.IntegerField(verbose_name="Год списания", null=True, blank=True)
    from_month = models.IntegerField(verbose_name="Месяц списания", null=True, blank=True)
    to_year = models.IntegerField(verbose_name="Год зачисления")
    to_month = models.IntegerField(verbose_name="Месяц зачисления")
    amount_seconds = models.IntegerField(verbose_name="Секунды переноса")
    description = models.CharField(max_length=255, blank=True, default="", verbose_name="Описание / Комментарий")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Перенос / Добавление времени"
        verbose_name_plural = "Переносы и добавления времени"

    def __str__(self):
        hours = abs(self.amount_seconds) // 3600
        minutes = (abs(self.amount_seconds) % 3600) // 60
        if self.from_year and self.from_month:
            return f"{self.user.username}: {hours:02d}:{minutes:02d} ({self.from_month:02d}.{self.from_year} -> {self.to_month:02d}.{self.to_year})"
        desc_str = f" ({self.description})" if self.description else ""
        return f"{self.user.username}: +{hours:02d}:{minutes:02d} в {self.to_month:02d}.{self.to_year}{desc_str}"


class Birthday(models.Model):
    """
    Модель для хранения дней рождения сотрудников.
    """
    date = models.DateField(verbose_name="Дата рождения")
    full_name = models.CharField(max_length=255, verbose_name="ФИО")

    class Meta:
        verbose_name = "День рождения"
        verbose_name_plural = "Дни рождения"
        ordering = ['date']

    def __str__(self):
        return f"{self.full_name} ({self.date.strftime('%d.%m')})"


class Holiday(models.Model):
    """
    Модель для праздников и сокращенных дней,
    меняющая тип дня у всех пользователей.
    """
    HOLIDAY_TYPE_CHOICES = [
        ('HD', 'Праздник'),
        ('SMD', 'Короткий день'),
    ]

    date = models.DateField(unique=True, verbose_name="Дата")
    day_type = models.CharField(
        max_length=5,
        choices=HOLIDAY_TYPE_CHOICES,
        default='HD',
        verbose_name="Тип дня"
    )
    description = models.CharField(max_length=255, blank=True, null=True, verbose_name="Описание")

    class Meta:
        verbose_name = "Праздник / Сокращённый день"
        verbose_name_plural = "Праздники и сокращённые дни"
        ordering = ['date']

    def __str__(self):
        return f"{self.date.strftime('%d.%m.%Y')} - {self.get_day_type_display()}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Обновляем типа дня у всех существующих WorkDay за эту дату
        WorkDay.objects.filter(date_stamp=self.date).update(type=self.day_type)
        # Создаем WorkDay для пользователей, у которых его ещё нет
        existing_user_ids = WorkDay.objects.filter(date_stamp=self.date).values_list('user_id', flat=True)
        users_to_create = User.objects.exclude(id__in=existing_user_ids)
        new_workdays = [
            WorkDay(user=user, date_stamp=self.date, type=self.day_type)
            for user in users_to_create
        ]
        if new_workdays:
            WorkDay.objects.bulk_create(new_workdays)

    def delete(self, *args, **kwargs):
        date_to_reset = self.date
        super().delete(*args, **kwargs)
        default_type = 'WD' if date_to_reset.weekday() >= 5 else 'ND'
        WorkDay.objects.filter(date_stamp=date_to_reset).update(type=default_type)


class TodayPhrase(models.Model):
    """
    Модель для хранения вариантов наименований фразы «Сегодня» на разных языках.
    """
    phrase = models.CharField(max_length=100, verbose_name="Фраза")
    is_active = models.BooleanField(default=True, verbose_name="Активна")

    class Meta:
        verbose_name = "Фраза «Сегодня»"
        verbose_name_plural = "Фразы «Сегодня»"

    def __str__(self):
        return self.phrase


class TaskPriority(models.Model):
    """
    Модель приоритетов задач (от 0 до 4).
    0 - Наивысший приоритет.
    """
    code = models.IntegerField(unique=True, verbose_name="Код приоритета (0-4)")
    name = models.CharField(max_length=100, verbose_name="Название приоритета")
    color_code = models.CharField(max_length=30, default="#ef4444", verbose_name="Цвет (HEX / CSS)")

    class Meta:
        verbose_name = "Приоритет задачи"
        verbose_name_plural = "Приоритеты задач"
        ordering = ['code']

    def __str__(self):
        return f"[{self.code}] {self.name}"


class TaskTopic(models.Model):
    """
    Модель тем задач.
    """
    name = models.CharField(max_length=100, unique=True, verbose_name="Название темы")

    class Meta:
        verbose_name = "Тема задачи"
        verbose_name_plural = "Темы задач"
        ordering = ['name']

    def __str__(self):
        return self.name


class Task(models.Model):
    """
    Модель для задач планировщика (Time Manager).
    """
    STATUS_CHOICES = [
        ('assigned', 'Назначено'),
        ('pending_review', 'На проверке'),
        ('rework', 'На доработке'),
        ('done', 'Выполнено'),
    ]

    SCHEDULE_CHOICES = [
        ('off_schedule', 'Не по графику'),
        ('on_schedule', 'По графику'),
    ]

    title = models.CharField(max_length=255, verbose_name="Заголовок")
    description = models.TextField(blank=True, verbose_name="Краткое описание")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    due_date = models.DateField(verbose_name="Дата выполнения")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_tasks',
        verbose_name="Создатель"
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='assigned_tasks',
        verbose_name="Ответственный"
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='tasks',
        verbose_name="Подразделение"
    )
    co_assignees = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='co_assigned_tasks',
        blank=True,
        verbose_name="Дополнительные исполнители"
    )
    topic = models.ForeignKey(
        TaskTopic,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tasks',
        verbose_name="Тема задачи"
    )
    priority = models.ForeignKey(
        TaskPriority,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Приоритет"
    )
    schedule_type = models.CharField(
        max_length=20,
        choices=SCHEDULE_CHOICES,
        default='off_schedule',
        verbose_name="График"
    )
    schedule_number = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Номер графика"
    )
    archive_url = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name="Ссылка на архив"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='assigned',
        verbose_name="Статус"
    )
    is_read_by_assignee = models.BooleanField(
        default=False,
        verbose_name="Прочитано исполнителем"
    )
    status_changed_for_head = models.BooleanField(
        default=False,
        verbose_name="Статус изменён для начальника"
    )
    last_change_detail = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Детали последнего изменения"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления"
    )

    class Meta:
        verbose_name = "Задача"
        verbose_name_plural = "Задачи"
        ordering = ['due_date', 'priority__code', '-created_at']

    def __str__(self):
        return f"{self.title} -> {self.assigned_to}"

    @property
    def days_left(self):
        return (self.due_date - timezone.localdate()).days

    @property
    def overdue_days(self):
        return abs(self.days_left)

    @property
    def co_assignees_all_approved(self):
        approvals = self.co_assignee_approvals.all()
        if not approvals.exists():
            return True
        return not approvals.filter(is_approved=False).exists()


class TaskCoAssigneeApproval(models.Model):
    """
    Статус согласования задачи дополнительным исполнителем (ДИ).
    """
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name='co_assignee_approvals',
        verbose_name="Задача"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name="Доп. исполнитель"
    )
    is_approved = models.BooleanField(
        default=False,
        verbose_name="Согласовано"
    )
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дата и время согласования"
    )

    class Meta:
        verbose_name = "Согласование ДИ"
        verbose_name_plural = "Согласования ДИ"
        unique_together = ('task', 'user')

    def __str__(self):
        status_str = "Согласовано" if self.is_approved else "Ожидает"
        return f"{self.user} - {status_str} ({self.task.title})"


class TaskHistory(models.Model):
    """
    Модель хронологии (истории изменений) задачи.
    """
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name='history',
        verbose_name="Задача"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Кто совершил действие"
    )
    action_type = models.CharField(
        max_length=100,
        verbose_name="Тип действия"
    )
    description = models.TextField(
        verbose_name="Подробное описание изменения"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата и время"
    )

    class Meta:
        verbose_name = "История задачи"
        verbose_name_plural = "История задач"
        ordering = ['created_at']

    def __str__(self):
        local_time = timezone.localtime(self.created_at)
        return f"{local_time.strftime('%d.%m.%Y %H:%M')} [{self.action_type}] - {self.task.title}"


class TaskComment(models.Model):
    """
    Комментарий к задаче планировщика.
    """
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name='comments',
        verbose_name="Задача"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='task_comments',
        verbose_name="Автор"
    )
    text = models.TextField(verbose_name="Текст комментария")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Комментарий к задаче"
        verbose_name_plural = "Комментарии к задачам"
        ordering = ['created_at', 'id']

    def __str__(self):
        return f"Комм. от {self.author} к {self.task.title}"


class TaskDependency(models.Model):
    """
    Хронологическая зависимость (связь) между задачами.
    `task` зависит от `depends_on` (предшественника).
    """
    RELATION_FS = 'FS'  # Finish-to-Start (Окончание -> Начало)
    RELATION_SS = 'SS'  # Start-to-Start (Начало -> Начало)
    RELATION_FF = 'FF'  # Finish-to-Finish (Окончание -> Окончание)
    RELATION_SF = 'SF'  # Start-to-Finish (Начало -> Окончание)

    RELATION_CHOICES = [
        (RELATION_FS, 'Окончание → Начало (FS)'),
        (RELATION_SS, 'Начало → Начало (SS)'),
        (RELATION_FF, 'Окончание → Окончание (FF)'),
        (RELATION_SF, 'Начало → Окончание (SF)'),
    ]

    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name='dependencies',
        verbose_name="Текущая задача"
    )
    depends_on = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name='blocking_dependencies',
        verbose_name="Связанная задача (предшественник)"
    )
    relation_type = models.CharField(
        max_length=2,
        choices=RELATION_CHOICES,
        default=RELATION_FS,
        verbose_name="Тип связи"
    )
    lag_lead_days = models.IntegerField(
        default=0,
        verbose_name="Сдвиг (дней)"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания"
    )

    class Meta:
        verbose_name = "Хронологическая зависимость"
        verbose_name_plural = "Хронологические зависимости"
        unique_together = ('task', 'depends_on')

    def __str__(self):
        offset_str = f" ({self.lag_lead_days:+d} дн.)" if self.lag_lead_days != 0 else ""
        return f"#{self.task.id} -> #{self.depends_on.id} [{self.relation_type}]{offset_str}"


class TaskUserNotification(models.Model):
    """
    Персональное состояние уведомления и прочтения задачи для каждого пользователя.
    У каждого пользователя свои независимые от других уведомления.
    """
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name='user_notifications',
        verbose_name="Задача"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='task_notifications',
        verbose_name="Пользователь"
    )
    is_read = models.BooleanField(
        default=False,
        verbose_name="Прочитано"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления"
    )

    class Meta:
        verbose_name = "Уведомление пользователя по задаче"
        verbose_name_plural = "Уведомления пользователей по задачам"
        unique_together = ('task', 'user')
        indexes = [
            models.Index(fields=['user', 'is_read']),
        ]

    def __str__(self):
        status_str = "Прочитано" if self.is_read else "Новое/Изменено"
        return f"{self.user} - #{self.task_id} {self.task.title} ({status_str})"








