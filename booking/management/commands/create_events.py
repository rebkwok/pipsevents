from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from datetime import timedelta
from booking.models import Event


class Command(BaseCommand):

    def handle(self, *args, **options):

        self.stdout.write("Creating events")
        now = timezone.now()
        # create 2 with defaults, 1 with max participants
        Event.objects.get_or_create(
            name="Workshop",
            type=Event.WORKSHOP,
            description="Workshop with awesome unnamed instructor!\n"
                        "Advance payment required, payment not open yet",
            date=now + timedelta(30),
            max_participants=20,
            cost=10,
            payment_open=False,
            advance_payment_required=True,
            payment_info="Please pay by paypal to contact email.",
            payment_due_date=now + timedelta(40),
        )

        Event.objects.get_or_create(
            name="Pips outing",
            type=Event.OTHER_EVENT,
            description="Outing for pips to play!\n"
                        "Cost, no max participants, payment open.",
            location="The pub",
            date=now + timedelta(20),
            cost=5,
            payment_open=True,
            payment_info="Please pay by paypal to contact email.",
            payment_due_date=now + timedelta(30),
        )

        # no costs
        Event.objects.get_or_create(
            name="Party",
            type=Event.OTHER_EVENT,
            description="Watermelon party",
            date=now + timedelta(10),
            payment_link="",
        )

        # non-default contact
        Event.objects.get_or_create(
            name="Workshop 1",
            type=Event.WORKSHOP,
            description="Workshop with another awesome unnamed instructor!\n"
                        "Advance payment not required, payment open.",
            date=now + timedelta(30),
            max_participants=20,
            cost=10,
            payment_open=True,
            contact_person="Someone else",
            contact_email="someone@else.com",
            payment_info="Please pay by paypal to contact email.",
            payment_due_date=now + timedelta(40),
        )

        # Past event
        Event.objects.get_or_create(
            name="An old event",
            type=Event.OTHER_EVENT,
            description="Event that happened in the past!\n"
                        "Advance payment required, payment open left set to true.",
            date=now - timedelta(30),
            advance_payment_required=True,
            max_participants=20,
            cost=10,
            payment_open=True,
            payment_info="Please pay by paypal to contact email.",
            payment_due_date=now + timedelta(40),
        )