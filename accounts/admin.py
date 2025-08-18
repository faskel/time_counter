from django.contrib import admin

# Register your models here.
from .models import WorkDay, Action


def set_normal_day(modeladmin, request, queryset):
    """Устанавливает тип дня для выбранных записей на 'Обычный день'."""
    updated_count = queryset.update(type='ND')
    modeladmin.message_user(
        request,
        f"Успешно изменено {updated_count} записей на тип 'Обычный день'."
    )


set_normal_day.short_description = "Установить выбранным дням тип 'Обычный день'"


def set_weekend_day(modeladmin, request, queryset):
    """Устанавливает тип дня для выбранных записей на 'Выходной день'."""
    updated_count = queryset.update(type='WD')
    modeladmin.message_user(
        request,
        f"Успешно изменено {updated_count} записей на тип 'Выходной день'."
    )


set_weekend_day.short_description = "Установить выбранным дням тип 'Выходной день'"


def set_short_day(modeladmin, request, queryset):
    """Устанавливает тип дня для выбранных записей на 'Короткий день'."""
    updated_count = queryset.update(type='SMD')
    modeladmin.message_user(
        request,
        f"Успешно изменено {updated_count} записей на тип 'Короткий день'."
    )


set_short_day.short_description = "Установить выбранным дням тип 'Короткий день'"


def set_vacation_day(modeladmin, request, queryset):
    """Устанавливает тип дня для выбранных записей на 'Отпуск'."""
    updated_count = queryset.update(type='VL')
    modeladmin.message_user(
        request,
        f"Успешно изменено {updated_count} записей на тип 'Отпуск'."
    )


set_vacation_day.short_description = "Установить выбранным дням тип 'Отпуск'"


def set_holiday(modeladmin, request, queryset):
    """Устанавливает тип дня для выбранных записей на 'Праздник'."""
    updated_count = queryset.update(type='HD')
    modeladmin.message_user(
        request,
        f"Успешно изменено {updated_count} записей на тип 'Праздник'."
    )


set_holiday.short_description = "Установить выбранным дням тип 'Праздник'"


def set_mk_type(modeladmin, request, queryset):
    """Устанавливает entry_type для выбранных записей на 'mk'."""
    updated_count = queryset.update(entry_type='mk')
    modeladmin.message_user(
        request,
        f"Успешно изменено {updated_count} записей на тип 'МК'."
    )


# Добавляем короткое описание для действия, которое будет отображаться в админке
set_mk_type.short_description = "Установить выбранным записям тип 'МК'"


def set_default_type(modeladmin, request, queryset):
    """Устанавливает entry_type для выбранных записей на 'default'."""
    updated_count = queryset.update(entry_type='default')
    modeladmin.message_user(
        request,
        f"Успешно изменено {updated_count} записей на тип 'default'."
    )


set_default_type.short_description = "Установить выбранным записям тип 'default'"


@admin.register(WorkDay)
class WorkDayAdmin(admin.ModelAdmin):
    list_display = ('user', 'date_stamp', 'type')
    list_filter = ('user', 'type', 'date_stamp')
    search_fields = ('user__username', 'date_stamp')
    date_hierarchy = 'date_stamp'
    actions = [set_normal_day, set_weekend_day, set_short_day, set_vacation_day, set_holiday]


@admin.register(Action)
class ActionAdmin(admin.ModelAdmin):
    list_display = ('workday', 'time_stamp', 'status_gate', 'order', 'entry_type')
    list_filter = ('workday__user', 'time_stamp', 'status_gate', 'entry_type')
    search_fields = ('workday__user__username', 'time_stamp')
    raw_id_fields = ('workday',)
    date_hierarchy = 'time_stamp'
    actions = [set_mk_type, set_default_type]
