# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='OnlineDisclaimer',
            fields=[
                ('id', models.AutoField(verbose_name='ID', primary_key=True, serialize=False, auto_created=True)),
                ('date', models.DateTimeField(default=django.utils.timezone.now)),
                ('name', models.CharField(max_length=255)),
                ('dob', models.DateField(verbose_name='date of birth')),
                ('address', models.CharField(max_length=512)),
                ('postcode', models.CharField(max_length=10)),
                ('home_phone', models.CharField(max_length=255)),
                ('mobile_phone', models.CharField(max_length=255)),
                ('emergency_contact1_name', models.CharField(verbose_name='name', max_length=255)),
                ('emergency_contact1_relationship', models.CharField(verbose_name='relationship', max_length=255)),
                ('emergency_contact1_phone', models.CharField(verbose_name='contact number', max_length=255)),
                ('emergency_contact2_name', models.CharField(verbose_name='name', max_length=255)),
                ('emergency_contact2_relationship', models.CharField(verbose_name='relationship', max_length=255)),
                ('emergency_contact2_phone', models.CharField(verbose_name='contact number', max_length=255)),
                ('medical_conditions', models.BooleanField(verbose_name='Do you have any medical conditions which may require treatment or medication?', choices=[(True, 'Yes'), (False, 'No')], default=True)),
                ('medical_conditions_details', models.CharField(max_length=2048, blank=True, null=True)),
                ('joint_problems', models.BooleanField(verbose_name='Do you suffer from problems regarding knee/back/shoulder/ankle/hip/neck?', choices=[(True, 'Yes'), (False, 'No')], default=True)),
                ('joint_problems_details', models.CharField(max_length=2048, blank=True, null=True)),
                ('allergies', models.BooleanField(verbose_name='Do you have any allergies?', choices=[(True, 'Yes'), (False, 'No')], default=True)),
                ('allergies_details', models.CharField(max_length=2048, blank=True, null=True)),
                ('medical_treatment_permission', models.BooleanField(verbose_name='I give permission for myself to receive medical treatment in the event of an accident')),
                ('disclaimer_terms', models.CharField(max_length=2048)),
                ('terms_accepted', models.BooleanField()),
                ('age_over_18_confirmed', models.BooleanField(verbose_name='I confirm that I am over the age of 18')),
                ('user', models.OneToOneField(related_name='online_disclaimer', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='PrintDisclaimer',
            fields=[
                ('id', models.AutoField(verbose_name='ID', primary_key=True, serialize=False, auto_created=True)),
                ('date', models.DateTimeField(default=django.utils.timezone.now)),
                ('user', models.OneToOneField(related_name='print_disclaimer', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.RemoveField(
            model_name='disclaimer',
            name='user',
        ),
        migrations.DeleteModel(
            name='Disclaimer',
        ),
    ]
