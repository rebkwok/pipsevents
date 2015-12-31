# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0039_auto_20151217_1653'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='booking',
            options={'permissions': (('can_book_free_pole_practice', 'Can book free pole practice'), ('is_regular_student', 'Is regular student'), ('can_view_registers', 'Can view registers'))},
        ),
    ]
