# Generated by Django 4.2.13 on 2024-07-20 08:44

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("stripe_payments", "0003_stripesubscriptioninvoice"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="stripesubscriptioninvoice",
            options={"ordering": ("-invoice_date",)},
        ),
    ]