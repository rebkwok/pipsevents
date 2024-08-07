# Generated by Django 4.2.13 on 2024-06-08 08:46

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stripe_payments', '0002_invoice_is_stripe_test'),
    ]

    operations = [
        migrations.CreateModel(
            name='StripeSubscriptionInvoice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('subscription_id', models.CharField()),
                ('invoice_id', models.CharField()),
                ('status', models.CharField()),
                ('total', models.DecimalField(decimal_places=2, max_digits=8)),
                ('invoice_date', models.DateTimeField()),
            ],
        ),
    ]
