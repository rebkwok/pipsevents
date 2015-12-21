'''
Activate/deactivate blocktypes by identifier (to be used in cronjob to turn
certain blocktypes on/off
'''

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand

from booking.models import BlockType
from booking.email_helpers import send_support_email

from activitylog.models import ActivityLog


class Command(BaseCommand):
    help = 'create new blocktypes for sale and standard prices'

    def handle(self, *args, **options):

        # make existing blocktypes standard and copy to make sale blocks
        for bt in BlockType.objects.all():
            bt.identifier = 'standard'
            bt.active = False
            bt.save()

            bt.pk = None
            bt.identifier = 'sale'
            bt.active = False
            bt.save()

        # set prices
        standard_pc_10 = BlockType.objects.get(
            identifier='standard',
            size=10,
            event_type__subtype='Pole level class'
        )
        standard_pc_10.cost = 68
        standard_pc_10.save()

        standard_pc_5 = BlockType.objects.get(
            identifier='standard',
            size=5,
            event_type__subtype='Pole level class'
        )
        standard_pc_5.cost = 35
        standard_pc_5.save()

        standard_pp_10 = BlockType.objects.get(
            identifier='standard',
            size=10,
            event_type__subtype='Pole practice'
        )
        standard_pp_10.cost = 36
        standard_pp_10.save()

        sale_pc_10 = BlockType.objects.get(
            identifier='sale',
            size=10,
            event_type__subtype='Pole level class'
        )
        sale_pc_10.cost = 60
        sale_pc_10.save()

        sale_pc_5 = BlockType.objects.get(
            identifier='sale',
            size=5,
            event_type__subtype='Pole level class'
        )
        sale_pc_5.cost = 30
        sale_pc_5.save()

        sale_pp_10 = BlockType.objects.get(
            identifier='sale',
            size=10,
            event_type__subtype='Pole practice'
        )
        sale_pp_10.cost = 32
        sale_pp_10.save()
