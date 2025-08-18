# accounts/models.py

from django.db import models
from django.contrib.auth.models import AbstractUser # Если используете кастомного User
from django.conf import settings
from django.utils import timezone



class User(AbstractUser):
    # Если у вас есть кастомные поля для пользователя, добавьте их здесь.
    # Например:
    # phone_number = models.CharField(max_length=20, blank=True, null=True)
    pass # Пока нет дополнительных полей

    def __str__(self):
        return self.username

#
# # accounts/models.py
#
# from django.db import models
# from django.contrib.auth.models import AbstractUser # Если используете кастомного User
# from django.conf import settings
# from django.utils import timezone # Добавьте этот импорт
#
# # Если вы еще не определили User, убедитесь, что ваш User унаследован от AbstractUser
# # class User(AbstractUser):
# #     pass
# # (Оставьте ваш текущий класс User, если он уже есть и работает)


# class WorkDay(models.Model):
#     user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='workdays')
#     date_stamp = models.DateField() # Unique per user, not globally unique
#     TYPE_CHOICES = [
#         ('ND', 'Обычный день'),
#         ('WD', 'Выходной/Праздник'),
#         ('SMD', 'Короткий день'),
#     ]
#     type = models.CharField(max_length=3, choices=TYPE_CHOICES, default='ND')
#
#     def __str__(self):
#         return f"{self.user.username} - {self.date_stamp} ({self.type})"
#
#     class Meta:
#         unique_together = ('user', 'date_stamp',) # Уникальная комбинация пользователя и даты
#         ordering = ['date_stamp'] # Добавим сортировку по дате для удобства
class WorkDay(models.Model):
    """
    Модель для хранения информации о рабочем дне пользователя.
    """
    DAY_TYPE_CHOICES = [
        ('ND', 'Обычный день'),
        ('WD', 'Выходной'),       # Изменено: теперь только "Выходной"
        ('HD', 'Праздник'),       # НОВЫЙ ТИП: Праздник
        ('VL', 'Отпуск'),         # НОВЫЙ ТИП: Отпуск
        ('SMD', 'Короткий день'),
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

    class Meta:
        verbose_name = "Действие"
        verbose_name_plural = "Действия"
        ordering = ['time_stamp', 'order']

    def __str__(self):
        return f"{self.workday.date_stamp.strftime('%d.%m.%Y')} - {self.get_status_gate_display()} в {self.time_stamp.strftime('%H:%M')}"
