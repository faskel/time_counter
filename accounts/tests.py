from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from .models import Task, TaskComment, TaskPriority, ChatColor

User = get_user_model()

class TaskCommentPermissionsTestCase(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username='user1', password='password123')
        self.user2 = User.objects.create_user(username='user2', password='password123')
        
        self.priority = TaskPriority.objects.create(code=1, name='Средний')
        self.task = Task.objects.create(
            title='Тестовая задача',
            description='Описание задачи',
            created_by=self.user1,
            assigned_to=self.user2,
            priority=self.priority,
            due_date='2026-10-02'
        )

    def test_author_can_edit_latest_comment(self):
        self.client.login(username='user1', password='password123')
        comment = TaskComment.objects.create(task=self.task, author=self.user1, text='Первый коммент')

        url = reverse('edit_task_comment', kwargs={'comment_id': comment.id})
        response = self.client.post(url, {'text': 'Измененный коммент'})
        
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get('success'))
        comment.refresh_from_db()
        self.assertEqual(comment.text, 'Измененный коммент')

    def test_author_cannot_edit_comment_if_newer_exists(self):
        self.client.login(username='user1', password='password123')
        comment1 = TaskComment.objects.create(task=self.task, author=self.user1, text='Первый коммент')
        comment2 = TaskComment.objects.create(task=self.task, author=self.user2, text='Второй коммент')

        url = reverse('edit_task_comment', kwargs={'comment_id': comment1.id})
        response = self.client.post(url, {'text': 'Попытка изменения'})
        
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json().get('success'))
        comment1.refresh_from_db()
        self.assertEqual(comment1.text, 'Первый коммент')

    def test_non_author_cannot_edit_comment(self):
        self.client.login(username='user2', password='password123')
        comment = TaskComment.objects.create(task=self.task, author=self.user1, text='Коммент пользователя 1')

        url = reverse('edit_task_comment', kwargs={'comment_id': comment.id})
        response = self.client.post(url, {'text': 'Попытка изменения пользователем 2'})
        
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json().get('success'))

    def test_author_can_delete_latest_comment(self):
        self.client.login(username='user1', password='password123')
        comment = TaskComment.objects.create(task=self.task, author=self.user1, text='Коммент для удаления')

        url = reverse('delete_task_comment', kwargs={'comment_id': comment.id})
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get('success'))
        self.assertFalse(TaskComment.objects.filter(id=comment.id).exists())

    def test_author_cannot_delete_comment_if_newer_exists(self):
        self.client.login(username='user1', password='password123')
        comment1 = TaskComment.objects.create(task=self.task, author=self.user1, text='Первый коммент')
        comment2 = TaskComment.objects.create(task=self.task, author=self.user2, text='Второй коммент')

        url = reverse('delete_task_comment', kwargs={'comment_id': comment1.id})
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json().get('success'))
        self.assertTrue(TaskComment.objects.filter(id=comment1.id).exists())

    def test_non_author_cannot_delete_comment(self):
        self.client.login(username='user2', password='password123')
        comment = TaskComment.objects.create(task=self.task, author=self.user1, text='Коммент пользователя 1')

        url = reverse('delete_task_comment', kwargs={'comment_id': comment.id})
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json().get('success'))
        self.assertTrue(TaskComment.objects.filter(id=comment.id).exists())

    def test_clear_notifications(self):
        self.task.is_read_by_assignee = False
        self.task.status_changed_for_head = True
        self.task.save()

        self.client.login(username='user2', password='password123')
        url = reverse('clear_head_notifications')
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get('success'))
        self.task.refresh_from_db()
        self.assertTrue(self.task.is_read_by_assignee)


class TaskDependencyTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='depuser', password='password123', is_administrator=True)
        self.priority = TaskPriority.objects.create(code=1, name='Высокий')
        self.task1 = Task.objects.create(
            title='Задача 1',
            created_by=self.user,
            assigned_to=self.user,
            priority=self.priority,
            due_date='2026-10-10'
        )
        self.task2 = Task.objects.create(
            title='Задача 2',
            created_by=self.user,
            assigned_to=self.user,
            priority=self.priority,
            due_date='2026-10-15'
        )
        self.task3 = Task.objects.create(
            title='Задача 3',
            created_by=self.user,
            assigned_to=self.user,
            priority=self.priority,
            due_date='2026-10-20'
        )
        self.client.login(username='depuser', password='password123')

    def test_search_tasks_for_dependencies(self):
        url = reverse('search_tasks_for_dependencies')
        resp = self.client.get(url, {'q': 'Задача 2', 'exclude_id': self.task1.id})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        task_ids = [t['id'] for t in data['tasks']]
        self.assertIn(self.task2.id, task_ids)
        self.assertNotIn(self.task1.id, task_ids)

    def test_create_and_edit_dependencies(self):
        edit_url = reverse('edit_task', kwargs={'task_id': self.task2.id})
        import json
        deps = [{'depends_on_id': self.task1.id, 'relation_type': 'FS', 'lag_lead_days': 2}]
        resp = self.client.post(edit_url, {
            'title': self.task2.title,
            'due_date': '2026-10-15',
            'dependencies': json.dumps(deps)
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get('success'))
        self.assertTrue(self.task2.dependencies.filter(depends_on=self.task1, relation_type='FS', lag_lead_days=2).exists())

    def test_prevent_cycle_deadlock(self):
        import json
        # Task 2 depends on Task 1
        from accounts.models import TaskDependency
        TaskDependency.objects.create(task=self.task2, depends_on=self.task1, relation_type='FS', lag_lead_days=0)
        # Task 3 depends on Task 2
        TaskDependency.objects.create(task=self.task3, depends_on=self.task2, relation_type='FS', lag_lead_days=0)

        # Now try to make Task 1 depend on Task 3 -> creates cycle 1 -> 3 -> 2 -> 1
        edit_url = reverse('edit_task', kwargs={'task_id': self.task1.id})
        deps = [{'depends_on_id': self.task3.id, 'relation_type': 'FS', 'lag_lead_days': 0}]
        resp = self.client.post(edit_url, {
            'title': self.task1.title,
            'due_date': '2026-10-10',
            'dependencies': json.dumps(deps)
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn('циклическая зависимость', resp.json().get('message', ''))

    def test_prevent_self_dependency(self):
        import json
        edit_url = reverse('edit_task', kwargs={'task_id': self.task1.id})
        deps = [{'depends_on_id': self.task1.id, 'relation_type': 'FS', 'lag_lead_days': 0}]
        resp = self.client.post(edit_url, {
            'title': self.task1.title,
            'due_date': '2026-10-10',
            'dependencies': json.dumps(deps)
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn('задача не может зависеть от самой себя', resp.json().get('message', ''))


class TaskUserNotificationTestCase(TestCase):
    def setUp(self):
        from accounts.models import Department
        self.dept = Department.objects.create(name='Тестовый отдел')
        self.head = User.objects.create_user(
            username='head_user',
            password='password123',
            department=self.dept,
            is_department_head=True
        )
        self.employee1 = User.objects.create_user(
            username='emp1',
            password='password123',
            department=self.dept
        )
        self.employee2 = User.objects.create_user(
            username='emp2',
            password='password123',
            department=self.dept
        )
        self.priority = TaskPriority.objects.create(code=1, name='Средний')

    def test_task_creation_notification(self):
        """Руководитель назначает задачу сотруднику: руководитель не получает уведомление, а исполнитель получает."""
        from accounts.models import TaskUserNotification
        self.client.login(username='head_user', password='password123')
        resp = self.client.post(reverse('time_manager'), {
            'action': 'add_task',
            'title': 'Новая задача от руководителя',
            'assigned_to': self.employee1.id,
            'priority': self.priority.id,
            'due_date': '2026-10-25',
        })
        self.assertEqual(resp.status_code, 302)
        task = Task.objects.get(title='Новая задача от руководителя')

        # Создатель head_user (actor): прочитано
        head_notif = TaskUserNotification.objects.get(task=task, user=self.head)
        self.assertTrue(head_notif.is_read)

        # Назначенный исполнитель emp1: не прочитано
        emp1_notif = TaskUserNotification.objects.get(task=task, user=self.employee1)
        self.assertFalse(emp1_notif.is_read)

    def test_comment_notifies_author_and_not_commenter(self):
        """Если исполнитель пишет комментарий в задачу, создатель получает уведомление, а исполнитель - нет."""
        from accounts.models import TaskUserNotification
        task = Task.objects.create(
            title='Задача автора emp1',
            created_by=self.employee1,
            assigned_to=self.employee2,
            department=self.dept,
            priority=self.priority,
            due_date='2026-10-25'
        )
        # Исполнитель emp2 пишет комментарий
        self.client.login(username='emp2', password='password123')
        resp = self.client.post(reverse('add_task_comment', kwargs={'task_id': task.id}), {
            'text': 'Сообщение от исполнителя emp2'
        })
        self.assertEqual(resp.status_code, 200)

        # Автор комментария emp2 (actor): прочитано (свои действия не спамят уведомлениями)
        emp2_notif = TaskUserNotification.objects.get(task=task, user=self.employee2)
        self.assertTrue(emp2_notif.is_read)

        # Создатель задачи emp1: НЕ прочитано (получил уведомление об активности в своей задаче!)
        emp1_notif = TaskUserNotification.objects.get(task=task, user=self.employee1)
        self.assertFalse(emp1_notif.is_read)

    def test_head_clear_notifications_does_not_affect_employee(self):
        """Если начальник нажимает 'Отметить всё прочитанным', уведомления сотрудника не сбрасываются."""
        from accounts.models import TaskUserNotification
        from accounts.task_notifications import notify_task_changed
        task = Task.objects.create(
            title='Задача в отделе',
            created_by=self.head,
            assigned_to=self.employee1,
            department=self.dept,
            priority=self.priority,
            due_date='2026-10-25'
        )
        # Генерируем изменение в задаче
        notify_task_changed(task, actor=None, change_detail='Обновление системы')

        self.assertFalse(TaskUserNotification.objects.get(task=task, user=self.head).is_read)
        self.assertFalse(TaskUserNotification.objects.get(task=task, user=self.employee1).is_read)

        # Начальник нажимает 'Отметить всё прочитанным'
        self.client.login(username='head_user', password='password123')
        resp = self.client.post(reverse('clear_head_notifications'))
        self.assertEqual(resp.status_code, 200)

        # У начальника сброшено
        self.assertTrue(TaskUserNotification.objects.get(task=task, user=self.head).is_read)

        # У обычного сотрудника emp1 уведомление ОСТАЛОСЬ активным!
        self.assertFalse(TaskUserNotification.objects.get(task=task, user=self.employee1).is_read)

    def test_status_change_notifies_creator(self):
        """Смена статуса исполнителем уведомляет создателя задачи."""
        from accounts.models import TaskUserNotification
        task = Task.objects.create(
            title='Задача на проверку',
            created_by=self.employee1,
            assigned_to=self.employee2,
            department=self.dept,
            priority=self.priority,
            due_date='2026-10-25',
            status='assigned'
        )
        self.client.login(username='emp2', password='password123')
        resp = self.client.post(reverse('update_task_status', kwargs={'task_id': task.id}), {
            'status': 'pending_review'
        })
        self.assertEqual(resp.status_code, 200)

        # Создатель emp1 получил уведомление
        emp1_notif = TaskUserNotification.objects.get(task=task, user=self.employee1)
        self.assertFalse(emp1_notif.is_read)

        # Исполнитель emp2 (actor) не получил уведомление для самого себя
        emp2_notif = TaskUserNotification.objects.get(task=task, user=self.employee2)
        self.assertTrue(emp2_notif.is_read)

    def test_employee_sees_notification_banner_and_can_clear(self):
        """Обычный сотрудник видит плашку уведомлений при наличии непрочитанных задач и может сбросить её."""
        from accounts.models import TaskUserNotification
        task = Task.objects.create(
            title='Задача для emp1',
            created_by=self.head,
            assigned_to=self.employee1,
            department=self.dept,
            priority=self.priority,
            due_date='2026-10-25',
            status='assigned'
        )
        TaskUserNotification.objects.create(task=task, user=self.employee1, is_read=False)

        self.client.login(username='emp1', password='password123')
        resp = self.client.get(reverse('time_manager'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['user_unread_tasks_count'], 1)
        self.assertContains(resp, 'id="head-notification-banner"')

        # Проверяем, что задача помечена как is_updated = 1
        tasks = list(resp.context['tasks'])
        self.assertTrue(any(t.id == task.id and t.is_updated == 1 for t in tasks))

        # Обычный сотрудник нажимает 'Отметить всё прочитанным'
        clear_resp = self.client.post(reverse('clear_head_notifications'))
        self.assertEqual(clear_resp.status_code, 200)

        # Теперь плашка исчезает
        resp_after = self.client.get(reverse('time_manager'))
        self.assertEqual(resp_after.status_code, 200)
        self.assertEqual(resp_after.context['user_unread_tasks_count'], 0)
        self.assertNotContains(resp_after, 'id="head-notification-banner"')


class UserChatColorTestCase(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username='color_user1', password='password123', chat_color='#db2777')
        self.user2 = User.objects.create_user(username='color_user2', password='password123', chat_color='')
        self.priority = TaskPriority.objects.create(code=1, name='Средний')
        self.task = Task.objects.create(
            title='Задача с цветами чата',
            created_by=self.user1,
            assigned_to=self.user2,
            priority=self.priority,
            due_date='2026-10-25'
        )

    def test_effective_chat_color(self):
        """Проверка выбора цвета из палитры и детерминированного фоллбэка."""
        self.assertEqual(self.user1.effective_chat_color, '#db2777')
        self.assertTrue(self.user2.effective_chat_color.startswith('#'))
        # Фоллбэк стабилен для одного и того же пользователя
        self.assertEqual(self.user2.effective_chat_color, self.user2.effective_chat_color)

    def test_add_comment_returns_author_color(self):
        """При добавлении комментария API возвращает author_color."""
        self.client.login(username='color_user1', password='password123')
        resp = self.client.post(reverse('add_task_comment', kwargs={'task_id': self.task.id}), {
            'text': 'Сообщение в красивом цвете'
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['author_color'], '#db2777')

    def test_get_task_details_includes_author_color(self):
        """Полноэкранные детали задачи возвращают author_color для каждого комментария."""
        TaskComment.objects.create(task=self.task, author=self.user1, text='Первое')
        TaskComment.objects.create(task=self.task, author=self.user2, text='Второе')

        self.client.login(username='color_user1', password='password123')
        resp = self.client.get(reverse('get_task_details', kwargs={'task_id': self.task.id}))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        comments = data['task']['comments']
        self.assertEqual(len(comments), 2)
        self.assertEqual(comments[0]['author_color'], '#db2777')
        self.assertEqual(comments[1]['author_color'], self.user2.effective_chat_color)

    def test_task_comments_updates_and_counts_include_color(self):
        """Эндпоинты фонового обновления возвращают author_color."""
        c1 = TaskComment.objects.create(task=self.task, author=self.user1, text='Первое фоновое')
        c2 = TaskComment.objects.create(task=self.task, author=self.user1, text='Второе фоновое')
        self.client.login(username='color_user1', password='password123')

        # get_task_comments_updates
        resp1 = self.client.get(f"{reverse('get_task_comments_updates', kwargs={'task_id': self.task.id})}?since_id=0")
        self.assertEqual(resp1.status_code, 200)
        data1 = resp1.json()
        self.assertEqual(data1['new_comments'][0]['author_color'], '#db2777')

        # get_tasks_comments_counts with since_id = c1.id
        resp2 = self.client.get(f"{reverse('get_tasks_comments_counts')}?since_id={c1.id}")
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()
        self.assertTrue(data2['success'])
        self.assertEqual(data2['new_comments'][0]['author_color'], '#db2777')

    def test_custom_chat_color_creation_and_display(self):
        """Создание нового цвета через ChatColor и корректное отображение названия."""
        ChatColor.objects.create(name='Космический фиолетовый', color_hex='#8b5cf6', order=500, is_active=True)
        custom_user = User.objects.create_user(username='custom_color_user', password='password123', chat_color='#8b5cf6')
        self.assertEqual(custom_user.effective_chat_color, '#8b5cf6')
        self.assertEqual(custom_user.get_chat_color_display(), 'Космический фиолетовый')

        # Пустой цвет возвращает 'Автоматический'
        self.assertEqual(self.user2.get_chat_color_display(), 'Автоматический')

    def test_color_palette_widget_render_and_dark_theme(self):
        """Проверка рендеринга виджета палитры с поддержкой темной темы."""
        from accounts.admin import ColorPaletteWidget
        widget = ColorPaletteWidget()
        html = widget.render('chat_color', '#db2777')
        self.assertIn('color-palette-grid', html)
        self.assertIn('is-selected', html)
        self.assertIn('data-theme="dark"', html)
        self.assertIn('#db2777', html)



