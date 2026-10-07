from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0030_taskusernotification'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='chat_color',
            field=models.CharField(
                blank=True,
                choices=[
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
                ],
                default='',
                max_length=20,
                verbose_name='Цвет сообщений в чате',
            ),
        ),
    ]
