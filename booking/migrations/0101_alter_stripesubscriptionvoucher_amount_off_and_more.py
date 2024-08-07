# Generated by Django 4.2.13 on 2024-07-27 08:43

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("booking", "0100_stripesubscriptionvoucher_new_memberships_only"),
    ]

    operations = [
        migrations.AlterField(
            model_name="stripesubscriptionvoucher",
            name="amount_off",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=8, null=True
            ),
        ),
        migrations.AlterField(
            model_name="stripesubscriptionvoucher",
            name="duration",
            field=models.CharField(
                choices=[
                    ("once", "once"),
                    ("forever", "forever"),
                    ("repeating", "repeating"),
                ],
                default="once",
                max_length=255,
            ),
        ),
        migrations.AlterField(
            model_name="stripesubscriptionvoucher",
            name="memberships",
            field=models.ManyToManyField(to="booking.membership"),
        ),
    ]
