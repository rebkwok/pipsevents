from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.core import management
from booking.utils import create_classes
from timetable.models import Session


class Command(BaseCommand):

    def handle(self, *args, **options):

        today = date.today()
        this_week_mon = today - timedelta(days=today.weekday())
        next_week_mon = this_week_mon + timedelta(7)

        if not Session.objects.all():
            self.stdout.write('No timetable sessions in system yet.  Creating sessions.')
            management.call_command('create_timetable')

        self.stdout.write("Creating this week's classes (week beginning {})"
                          .format(this_week_mon.strftime('%a %d %b %Y')))
        create_classes()
        self.stdout.write("Creating next week's classes (week beginning {})"
                          .format(next_week_mon.strftime('%a %d %b %Y')))
        create_classes(week='next')
