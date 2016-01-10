# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.utils.timezone
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='OnlineDisclaimer',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, primary_key=True, serialize=False)),
                ('date', models.DateTimeField(default=django.utils.timezone.now)),
                ('name', models.CharField(verbose_name='full name', max_length=255)),
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
                ('medical_conditions_details', models.CharField(blank=True, max_length=2048, null=True)),
                ('joint_problems', models.BooleanField(verbose_name='Do you suffer from problems regarding knee/back/shoulder/ankle/hip/neck?', choices=[(True, 'Yes'), (False, 'No')], default=True)),
                ('joint_problems_details', models.CharField(blank=True, max_length=2048, null=True)),
                ('allergies', models.BooleanField(verbose_name='Do you have any allergies?', choices=[(True, 'Yes'), (False, 'No')], default=True)),
                ('allergies_details', models.CharField(blank=True, max_length=2048, null=True)),
                ('medical_treatment_terms', models.CharField(max_length=2048, default='I confirm that I am over the age of 18')),
                ('medical_treatment_permission', models.BooleanField()),
                ('disclaimer_terms', models.CharField(max_length=2048, default='\n    I recognise that I may be asked to participate in some strenuous exercise\n    during the course and that such participation may present a heightened\n    risk of injury or ill health. All risks will be fully explained and I do\n    not hold The Watermelon Studio and any of their staff responsible for any\n    harm that may come to me should I decide to participate in such tasks. I\n    will not participate if pregnant and will update my teacher on any new\n    medical condition/injury throughout my time at The Watermelon Studio.\n    Other teachers/instructors may use the information submitted in this form\n    to help keep the chances of any injury to a minimum. I also hereby agree\n    to follow all rules set out by The Watermelon Studio.  I have\n    read and agree to the terms and conditions on the website.\n')),
                ('terms_accepted', models.BooleanField()),
                ('over_18_statement', models.CharField(max_length=2048, default='I confirm that I am over the age of 18')),
                ('age_over_18_confirmed', models.BooleanField()),
                ('user', models.OneToOneField(to=settings.AUTH_USER_MODEL, related_name='online_disclaimer')),
            ],
        ),
        migrations.CreateModel(
            name='PrintDisclaimer',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, primary_key=True, serialize=False)),
                ('date', models.DateTimeField(default=django.utils.timezone.now)),
                ('user', models.OneToOneField(to=settings.AUTH_USER_MODEL, related_name='print_disclaimer')),
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
