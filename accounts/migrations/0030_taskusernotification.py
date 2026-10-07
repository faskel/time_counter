import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0029_taskdependency'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='TaskUserNotification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_read', models.BooleanField(default=False, verbose_name='Прочитано')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Дата обновления')),
                ('task', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='user_notifications', to='accounts.task', verbose_name='Задача')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='task_notifications', to=settings.AUTH_USER_MODEL, verbose_name='Пользователь')),
            ],
            options={
                'verbose_name': 'Уведомление пользователя по задаче',
                'verbose_name_plural': 'Уведомления пользователей по задачам',
                'unique_together': {('task', 'user')},
            },
        ),
        migrations.AddIndex(
            model_name='taskusernotification',
            index=models.Index(fields=['user', 'is_read'], name='accounts_ta_user_id_44f1cf_idx'),
        ),
    ]
