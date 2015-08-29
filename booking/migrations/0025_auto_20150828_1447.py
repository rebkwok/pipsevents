# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0024_waitinglistuser'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='booking',
            options={'permissions': (('can_book_free_pole_practice', 'Can book free pole practice'), ('is_regular_student', 'Is regular student'))},
        ),
    ]
