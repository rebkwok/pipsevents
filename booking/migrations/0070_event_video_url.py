# Generated by Django 3.0.3 on 2020-05-22 16:55

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0069_auto_20200228_1558'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='video_link',
            field=models.URLField(blank=True, help_text='Zoom/Video URL (for online classes only)', null=True),
        ),
    ]