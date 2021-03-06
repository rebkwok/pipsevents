# Generated by Django 2.0.3 on 2018-05-08 15:24

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('accounts', '0005_update_disclaimer_terms'),
    ]

    operations = [
        migrations.CreateModel(
            name='CookiePolicy',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('content', models.TextField()),
                ('version', models.DecimalField(decimal_places=1, max_digits=100, unique=True)),
                ('issue_date', models.DateTimeField(default=django.utils.timezone.now)),
            ],
            options={
                'verbose_name_plural': 'Cookie Policies',
            },
        ),
        migrations.CreateModel(
            name='DataPrivacyPolicy',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('content', models.TextField()),
                ('version', models.DecimalField(decimal_places=1, max_digits=100, unique=True)),
                ('issue_date', models.DateTimeField(default=django.utils.timezone.now)),
            ],
            options={
                'verbose_name_plural': 'Data Privacy Policies',
            },
        ),
        migrations.CreateModel(
            name='SignedDataPrivacy',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_signed', models.DateTimeField(default=django.utils.timezone.now)),
                ('version', models.DecimalField(decimal_places=1, max_digits=100)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='data_privacy_agreement', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Signed Data Privacy Agreement',
            },
        ),
        migrations.AlterUniqueTogether(
            name='signeddataprivacy',
            unique_together={('user', 'version')},
        ),
    ]
