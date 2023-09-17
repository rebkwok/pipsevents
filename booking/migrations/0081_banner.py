# Generated by Django 4.1.1 on 2023-07-04 19:24

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0080_auto_20220119_0946'),
    ]

    operations = [
        migrations.CreateModel(
            name='Banner',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('banner_type', models.CharField(choices=[('banner_all', 'all users banner'), ('banner_new', 'new users banner')], default='banner_all', max_length=10)),
                ('content', models.TextField()),
                ('start_datetime', models.DateTimeField(default=django.utils.timezone.now)),
                ('end_datetime', models.DateTimeField(blank=True, null=True)),
            ],
        ),
    ]