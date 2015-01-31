from django.core.management.base import BaseCommand, CommandError
from booking.utils import create_classes


class Command(BaseCommand):

    def handle(self, *args, **options):

        self.stdout.write("Creating this week's classes")
        create_classes()
        self.stdout.write("Creating next week's classes")
        create_classes(week='next')

