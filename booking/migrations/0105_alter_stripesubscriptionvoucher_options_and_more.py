# Generated by Django 5.1.1 on 2024-11-03 13:25

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("booking", "0104_event_members_only"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="stripesubscriptionvoucher",
            options={"ordering": ("-active", "-expiry_date", "-redeem_by")},
        ),
        migrations.AddField(
            model_name="stripesubscriptionvoucher",
            name="expiry_date",
            field=models.DateTimeField(
                blank=True,
                help_text="Date after which the code will be removed from any memberships that have currently applied it.",
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="stripesubscriptionvoucher",
            name="redeem_by",
            field=models.DateTimeField(
                blank=True,
                help_text="Date after which users can no longer apply the code; note that once applied, it will apply for the voucher duration, even if that duration extends beyond the redeem by date. i.e. if a voucher applies for 2 months, and is redeemed on the redeem by date, it will still apply for the next 2 months' membership. If you want to override this behaviour, set an expiry date as well.",
                null=True,
            ),
        ),
    ]
