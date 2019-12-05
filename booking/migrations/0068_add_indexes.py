# Generated by Django 2.2.6 on 2019-12-05 10:27

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0067_data_migration_set_block_expiry_date'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='block',
            index=models.Index(fields=['user', 'paid'], name='booking_blo_user_id_c5ac39_idx'),
        ),
        migrations.AddIndex(
            model_name='block',
            index=models.Index(fields=['user', 'expiry_date'], name='booking_blo_user_id_298431_idx'),
        ),
        migrations.AddIndex(
            model_name='block',
            index=models.Index(fields=['user', '-start_date'], name='booking_blo_user_id_7ff31b_idx'),
        ),
        migrations.AddIndex(
            model_name='booking',
            index=models.Index(fields=['event', 'user', 'status'], name='booking_boo_event_i_15add5_idx'),
        ),
        migrations.AddIndex(
            model_name='booking',
            index=models.Index(fields=['block'], name='booking_boo_block_i_e787ec_idx'),
        ),
        migrations.AddIndex(
            model_name='event',
            index=models.Index(fields=['event_type', 'date', 'cancelled'], name='booking_eve_event_t_ca5e55_idx'),
        ),
        migrations.AddIndex(
            model_name='event',
            index=models.Index(fields=['event_type', 'name', 'date', 'cancelled'], name='booking_eve_event_t_267fc0_idx'),
        ),
        migrations.AddIndex(
            model_name='waitinglistuser',
            index=models.Index(fields=['user', 'event'], name='booking_wai_user_id_b026f7_idx'),
        ),
    ]
