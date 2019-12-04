# Generated by Django 2.2.6 on 2019-12-04 15:10
from datetime import timedelta
import pytz
from dateutil.relativedelta import relativedelta
from django.db import migrations


def _get_end_of_day(input_datetime):
    next_day = (input_datetime + timedelta(
        days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    end_of_day_utc = next_day - timedelta(seconds=1)
    uktz = pytz.timezone('Europe/London')
    end_of_day_uk = end_of_day_utc.astimezone(uktz)
    utc_offset = end_of_day_uk.utcoffset()
    return end_of_day_utc - utc_offset


def get_expiry_date(block):
    # replace block expiry date with very end of day in local time
    # move forwards 1 day and set hrs/min/sec/microsec to 0, then move
    # back 1 sec
    # For a with a parent block with a parent (free class block),
    # override blocktype duration to be same as parent's blocktype
    duration = block.block_type.duration
    if block.parent:
        duration = block.parent.block_type.duration

    expiry_datetime = block.start_date + relativedelta(
        months=duration)

    # if a manual extended expiry date has been set, use that instead
    # (unless it's been set to be earlier than the calculated expiry date)
    # extended_expiry_date is set to end of day on save, so just return it
    if block.extended_expiry_date and \
            block.extended_expiry_date > expiry_datetime:
        return block.extended_expiry_date

    return _get_end_of_day(expiry_datetime)


def set_expiry_date(apps, schema_editor):
    # Add a date_warning_sent for any bookings for future events that have already had warning sent before the timestamp field existed
    Block = apps.get_model('booking', 'Block')
    for block in Block.objects.all():
        block.expiry_date = get_expiry_date(block)
        block.save()


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0066_block_expiry_date'),
    ]

    operations = [
        migrations.RunPython(
            set_expiry_date, reverse_code=migrations.RunPython.noop
        )
    ]
