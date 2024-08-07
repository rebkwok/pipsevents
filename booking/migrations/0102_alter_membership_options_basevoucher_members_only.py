# Generated by Django 4.2.13 on 2024-07-31 13:30

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("booking", "0101_alter_stripesubscriptionvoucher_amount_off_and_more"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="membership",
            options={"ordering": ("id",)},
        ),
        migrations.AddField(
            model_name="basevoucher",
            name="members_only",
            field=models.BooleanField(
                default=False, help_text="Can only be redeemed by members"
            ),
        ),
    ]
