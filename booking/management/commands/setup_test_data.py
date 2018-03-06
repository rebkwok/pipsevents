from django.core.management.base import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):

    def handle(self, *args, **options):
        call_command('setup_fb')
        call_command('create_groups')
        call_command('load_users')
        call_command('create_event_and_blocktypes')
        call_command('create_events')
        call_command('create_classes')
        call_command('create_bookings')
        call_command('create_timetable')
