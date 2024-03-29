# Generated by Django 4.1.1 on 2023-11-08 16:19

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('booking', '0088_alter_block_options'),
    ]

    operations = [
        migrations.CreateModel(
            name='TicketedEventWaitingListUser',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_joined', models.DateTimeField(default=django.utils.timezone.now)),
                ('ticketed_event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='waiting_list_users', to='booking.ticketedevent')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ticketed_event_waiting_lists', to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
