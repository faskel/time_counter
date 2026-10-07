from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin, UserAdmin

# Register your models here.
from .models import (
    WorkDay, Action, User, MonthTransfer, Birthday, Holiday,
    Department, TodayPhrase, Task, TaskComment, TaskPriority,
    TaskTopic, TaskCoAssigneeApproval, TaskHistory, TaskDependency,
    ChatColor
)


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

# class UserAdmin(BaseUserAdmin):
#     fieldsets = (BaseUserAdmin.fieldsets + ('Личная информация',{'fields':('first_name','last_name')},'Тип учетной записи),'account_type')
#     # day_type = 'account_type'
#     admin.site.register(User, UserAdmin)

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'get_users_count', 'get_head')
    search_fields = ('name',)

    def get_users_count(self, obj):
        return obj.users.count()
    get_users_count.short_description = "Количество сотрудников"

    def get_head(self, obj):
        head = obj.users.filter(is_department_head=True).first()
        return head if head else "—"
    get_head.short_description = "Начальник подразделения"


from django import forms
from django.utils.safestring import mark_safe


class AdminColorPickerWidget(forms.Widget):
    """
    Виджет с нативным колорпикером браузера и текстовым HEX-полем.
    """
    def render(self, name, value, attrs=None, renderer=None):
        val = value or '#3b82f6'
        input_id = (attrs and attrs.get('id')) or f'id_{name}'
        picker_id = f'{input_id}_picker'
        color_val = val if (isinstance(val, str) and val.startswith('#') and len(val) == 7) else '#3b82f6'

        return mark_safe(f'''
        <div class="admin-color-picker-wrap" style="display: inline-flex; align-items: center; gap: 10px;">
            <input type="color" id="{picker_id}" value="{color_val}" style="width: 44px; height: 36px; padding: 2px; border: 1px solid var(--border-color, #cbd5e1); border-radius: 6px; cursor: pointer; background: transparent; vertical-align: middle;" />
            <input type="text" name="{name}" id="{input_id}" value="{value or ''}" placeholder="#3b82f6" style="width: 140px; font-family: monospace; font-size: 14px; text-transform: lowercase;" maxlength="20" />
        </div>
        <script>
            (function() {{
                const picker = document.getElementById("{picker_id}");
                const input = document.getElementById("{input_id}");
                if (picker && input) {{
                    picker.addEventListener('input', function() {{
                        input.value = picker.value.toLowerCase();
                    }});
                    input.addEventListener('input', function() {{
                        const val = input.value.trim();
                        if (/^#[0-9A-Fa-f]{{6}}$/.test(val)) {{
                            picker.value = val;
                        }}
                    }});
                }}
            }})();
        </script>
        ''')


class ChatColorAdminForm(forms.ModelForm):
    class Meta:
        model = ChatColor
        fields = '__all__'
        widgets = {
            'color_hex': AdminColorPickerWidget(),
        }


@admin.register(ChatColor)
class ChatColorAdmin(admin.ModelAdmin):
    form = ChatColorAdminForm
    list_display = ('color_preview', 'name', 'color_hex', 'order', 'is_active')
    list_editable = ('order', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'color_hex')
    ordering = ('order', 'name', 'id')

    @admin.display(description="Цвет")
    def color_preview(self, obj):
        return mark_safe(
            f'<div style="display:inline-flex;align-items:center;gap:8px;">'
            f'<span style="display:inline-block;width:22px;height:22px;border-radius:6px;'
            f'background-color:{obj.color_hex};border:1px solid rgba(128,128,128,0.3);'
            f'box-shadow:0 1px 3px rgba(0,0,0,0.2);"></span>'
            f'<code style="font-size:12px;opacity:0.85;">{obj.color_hex}</code>'
            f'</div>'
        )


def get_chat_color_choices():
    choices = [('', 'Авто (по умолчанию)')]
    try:
        colors = ChatColor.objects.filter(is_active=True).order_by('order', 'name', 'id')
        for c in colors:
            choices.append((c.color_hex, c.name))
    except Exception:
        pass
    if len(choices) == 1:
        choices.extend(User.CHAT_COLOR_CHOICES)
    return choices


class ColorPaletteWidget(forms.Widget):
    template_name = None

    def __init__(self, choices=(), attrs=None):
        super().__init__(attrs)
        self.choices = choices

    def render(self, name, value, attrs=None, renderer=None):
        value = value or ''
        choices = list(self.choices) if self.choices else get_chat_color_choices()

        # Если у пользователя уже сохранен уникальный цвет, отсутствующий в текущих опциях
        if value and value not in [c[0] for c in choices]:
            choices.append((value, f'Текущий ({value})'))

        items_html = []
        for color_hex, label in choices:
            is_selected = (value.lower() == (color_hex or '').lower())
            is_empty = not color_hex
            check_icon = "✓" if is_selected else ("" if not is_empty else "—")
            empty_class = "is-empty" if is_empty else ""
            selected_class = "is-selected" if is_selected else ""
            circle_style = f"background-color: {color_hex};" if color_hex else ""

            item = f'''
            <label class="color-palette-card {selected_class}">
                <input type="radio" name="{name}" value="{color_hex}" {'checked' if is_selected else ''} />
                <span class="color-palette-circle {empty_class}" style="{circle_style}">
                    {check_icon}
                </span>
                <span class="color-palette-label">{label}</span>
            </label>
            '''
            items_html.append(item)

        container = f'''
        <style>
            .color-palette-grid {{
                display: flex;
                flex-wrap: wrap;
                gap: 10px;
                max-width: 720px;
                padding: 8px 0;
            }}
            .color-palette-card {{
                cursor: pointer;
                display: inline-flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: 6px;
                padding: 10px 12px;
                min-width: 105px;
                border-radius: 10px;
                border: 1px solid #cbd5e1;
                background: #ffffff;
                color: #334155;
                transition: all 0.15s ease-in-out;
                position: relative;
                user-select: none;
                box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
            }}
            .color-palette-card:hover {{
                border-color: #3b82f6;
                background: #f8fafc;
                transform: translateY(-1px);
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.08);
            }}
            .color-palette-card.is-selected {{
                border-color: #2563eb;
                background: #eff6ff;
                box-shadow: 0 0 0 2px #3b82f6;
            }}
            .color-palette-card input[type="radio"] {{
                position: absolute;
                opacity: 0;
                pointer-events: none;
                margin: 0;
            }}
            .color-palette-circle {{
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 32px;
                height: 32px;
                border-radius: 50%;
                color: #ffffff;
                font-weight: 700;
                font-size: 15px;
                text-shadow: 0 1px 2px rgba(0, 0, 0, 0.4);
                transition: transform 0.15s ease, box-shadow 0.15s ease;
                border: 1px solid rgba(0, 0, 0, 0.15);
            }}
            .color-palette-circle.is-empty {{
                border: 2px dashed #94a3b8;
                background: transparent;
                color: #64748b;
                font-size: 14px;
                text-shadow: none;
            }}
            .color-palette-card.is-selected .color-palette-circle {{
                transform: scale(1.08);
                box-shadow: 0 0 0 3px #ffffff, 0 0 0 5px #3b82f6;
            }}
            .color-palette-card.is-selected .color-palette-circle.is-empty {{
                border-color: #3b82f6;
                color: #3b82f6;
                box-shadow: 0 0 0 3px #ffffff, 0 0 0 5px #3b82f6;
            }}
            .color-palette-label {{
                font-size: 11px;
                font-weight: 500;
                color: #475569;
                text-align: center;
                line-height: 1.25;
            }}
            .color-palette-card.is-selected .color-palette-label {{
                font-weight: 700;
                color: #1d4ed8;
            }}

            /* === Поддержка тёмной темы Django Admin === */
            html[data-theme="dark"] .color-palette-card,
            @media (prefers-color-scheme: dark) {{
                :root:not([data-theme="light"]) .color-palette-card {{
                    border-color: #334155;
                    background: #1e293b;
                    color: #f1f5f9;
                    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
                }}
                :root:not([data-theme="light"]) .color-palette-card:hover {{
                    border-color: #60a5fa;
                    background: #27354a;
                    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.4);
                }}
                :root:not([data-theme="light"]) .color-palette-card.is-selected {{
                    border-color: #60a5fa;
                    background: rgba(59, 130, 246, 0.22);
                    box-shadow: 0 0 0 2px #60a5fa;
                }}
                :root:not([data-theme="light"]) .color-palette-card.is-selected .color-palette-circle {{
                    box-shadow: 0 0 0 3px #0f172a, 0 0 0 5px #60a5fa;
                }}
                :root:not([data-theme="light"]) .color-palette-circle.is-empty {{
                    border-color: #64748b;
                    color: #94a3b8;
                }}
                :root:not([data-theme="light"]) .color-palette-card.is-selected .color-palette-circle.is-empty {{
                    border-color: #60a5fa;
                    color: #60a5fa;
                    box-shadow: 0 0 0 3px #0f172a, 0 0 0 5px #60a5fa;
                }}
                :root:not([data-theme="light"]) .color-palette-label {{
                    color: #cbd5e1;
                }}
                :root:not([data-theme="light"]) .color-palette-card.is-selected .color-palette-label {{
                    color: #93c5fd;
                }}
            }}
            html[data-theme="dark"] .color-palette-card {{
                border-color: #334155;
                background: #1e293b;
                color: #f1f5f9;
                box-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
            }}
            html[data-theme="dark"] .color-palette-card:hover {{
                border-color: #60a5fa;
                background: #27354a;
                box-shadow: 0 2px 6px rgba(0, 0, 0, 0.4);
            }}
            html[data-theme="dark"] .color-palette-card.is-selected {{
                border-color: #60a5fa;
                background: rgba(59, 130, 246, 0.22);
                box-shadow: 0 0 0 2px #60a5fa;
            }}
            html[data-theme="dark"] .color-palette-card.is-selected .color-palette-circle {{
                box-shadow: 0 0 0 3px #0f172a, 0 0 0 5px #60a5fa;
            }}
            html[data-theme="dark"] .color-palette-circle.is-empty {{
                border-color: #64748b;
                color: #94a3b8;
            }}
            html[data-theme="dark"] .color-palette-card.is-selected .color-palette-circle.is-empty {{
                border-color: #60a5fa;
                color: #60a5fa;
                box-shadow: 0 0 0 3px #0f172a, 0 0 0 5px #60a5fa;
            }}
            html[data-theme="dark"] .color-palette-label {{
                color: #cbd5e1;
            }}
            html[data-theme="dark"] .color-palette-card.is-selected .color-palette-label {{
                color: #93c5fd;
            }}
        </style>

        <div class="color-palette-grid">
            {''.join(items_html)}
        </div>
        <script>
            (function() {{
                const radios = document.querySelectorAll('input[name="{name}"]');
                radios.forEach(radio => {{
                    radio.addEventListener('change', function() {{
                        radios.forEach(r => {{
                            const card = r.closest('.color-palette-card');
                            if (!card) return;
                            const circle = card.querySelector('.color-palette-circle');
                            const isEmpty = circle.classList.contains('is-empty');
                            if (r.checked) {{
                                card.classList.add('is-selected');
                                circle.textContent = '✓';
                            }} else {{
                                card.classList.remove('is-selected');
                                circle.textContent = isEmpty ? '—' : '';
                            }}
                        }});
                    }});
                }});
            }})();
        </script>
        '''
        return mark_safe(container)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        'username',
        'first_name',
        'last_name',
        'colored_chat_indicator',
        'department',
        'is_administrator',
        'is_department_head',
        'account_type',
        'tracker',
        'pk',
        'is_staff',
        'is_superuser',
    )
    list_filter = (
        'department',
        'is_administrator',
        'is_department_head',
        'account_type',
    )
    search_fields = (
        'username',
        'first_name',
        'last_name',
    )

    fieldsets = [
        ('Личная информация', {
            'fields': [
                'username', 'first_name', 'last_name', 'department', 'is_administrator', 'is_staff', 'is_superuser', 'is_department_head', 'account_type', 'tracker', 'chat_color', 'password',
            ],
        }),
    ]

    def formfield_for_dbfield(self, db_field, **kwargs):
        if db_field.name == 'chat_color':
            choices = get_chat_color_choices()
            kwargs['widget'] = ColorPaletteWidget(choices=choices)
        return super().formfield_for_dbfield(db_field, **kwargs)

    @admin.display(description="Цвет чата")
    def colored_chat_indicator(self, obj):
        color = obj.effective_chat_color
        display_name = obj.get_chat_color_display()
        return mark_safe(f'<span style="display:inline-block;width:16px;height:16px;border-radius:50%;background-color:{color};vertical-align:middle;margin-right:6px;border:1px solid rgba(128,128,128,0.3);box-shadow:0 1px 2px rgba(0,0,0,0.15);"></span>{display_name}')


@admin.register(MonthTransfer)
class MonthTransferAdmin(admin.ModelAdmin):
    list_display = ('user', 'from_year', 'from_month', 'to_year', 'to_month', 'amount_seconds', 'description', 'created_at')
    list_filter = ('user', 'from_year', 'to_year')
    search_fields = ('user__username', 'description')


@admin.register(Birthday)
class BirthdayAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'date')
    list_filter = ('date',)
    search_fields = ('full_name',)
    ordering = ('date',)


@admin.register(Holiday)
class HolidayAdmin(admin.ModelAdmin):
    list_display = ('date', 'day_type', 'description')
    list_filter = ('day_type', 'date')
    search_fields = ('description', 'date')
    ordering = ('date',)


@admin.register(TodayPhrase)
class TodayPhraseAdmin(admin.ModelAdmin):
    list_display = ('phrase', 'is_active')
    list_editable = ('is_active',)
    search_fields = ('phrase',)




@admin.register(TaskTopic)
class TaskTopicAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(TaskPriority)
class TaskPriorityAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'color_code')
    list_editable = ('name', 'color_code')
    ordering = ('code',)


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'topic', 'priority', 'assigned_to', 'created_by', 'due_date', 'schedule_type', 'status')
    list_filter = ('topic', 'priority', 'status', 'schedule_type', 'due_date', 'assigned_to', 'created_by')
    search_fields = ('title', 'description', 'assigned_to__username', 'created_by__username', 'schedule_number')
    filter_horizontal = ('co_assignees',)
    date_hierarchy = 'due_date'


@admin.register(TaskCoAssigneeApproval)
class TaskCoAssigneeApprovalAdmin(admin.ModelAdmin):
    list_display = ('task', 'user', 'is_approved', 'approved_at')
    list_filter = ('is_approved', 'user')
    search_fields = ('task__title', 'user__username')


@admin.register(TaskHistory)
class TaskHistoryAdmin(admin.ModelAdmin):
    list_display = ('task', 'actor', 'action_type', 'created_at', 'description')
    list_filter = ('action_type', 'created_at', 'actor')
    search_fields = ('task__title', 'description', 'actor__username')


@admin.register(TaskComment)
class TaskCommentAdmin(admin.ModelAdmin):
    list_display = ('task', 'author', 'created_at', 'text')
    list_filter = ('created_at', 'author')
    search_fields = ('text', 'task__title', 'author__username')


@admin.register(TaskDependency)
class TaskDependencyAdmin(admin.ModelAdmin):
    list_display = ('task', 'depends_on', 'relation_type', 'lag_lead_days', 'created_at')
    list_filter = ('relation_type', 'created_at')
    search_fields = ('task__title', 'depends_on__title')





