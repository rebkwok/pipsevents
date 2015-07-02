from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from datetime import timedelta
from booking.models import Event, EventType


class Command(BaseCommand):

    def handle(self, *args, **options):

        ws, _ = EventType.objects.get_or_create(event_type='EV', subtype='Workshop')
        ev, _ = EventType.objects.get_or_create(event_type='EV', subtype='Other event')

        self.stdout.write("Creating events")
        now = timezone.now()
        # create 2 with defaults, 1 with max participants
        Event.objects.get_or_create(
            name="Workshop",
            event_type=ws,
            description="Workshop with awesome unnamed instructor!\n"
                        "Booking and payment not open yet",
            date=now + timedelta(30),
            max_participants=20,
            cost=10,
            booking_open=False,
            payment_open=False,
            advance_payment_required=True,
            payment_due_date=now + timedelta(27),
        )

        Event.objects.get_or_create(
            name="Pips outing",
            event_type=ev,
            description="Outing for pips to play!\n"
                        "Cost, no max participants, payment open.",
            location="The pub",
            date=now + timedelta(20),
            cost=5,
            payment_open=True,
            payment_due_date=now + timedelta(15),
        )

        # no costs
        Event.objects.get_or_create(
            name="Party",
            event_type=ev,
            description="Watermelon party",
            date=now + timedelta(10),
        )

        # non-default contact
        Event.objects.get_or_create(
            name="Workshop 1",
            event_type=ws,
            description="Workshop with another awesome unnamed instructor!\n",
            date=now + timedelta(30),
            max_participants=20,
            cost=10,
            payment_open=True,
            contact_person="Someone else",
            contact_email="someone@else.com",
            payment_due_date=now + timedelta(30),
        )

        # Past event
        Event.objects.get_or_create(
            name="An old event",
            event_type=ev,
            description="Event that happened in the past!\n",
            date=now - timedelta(30),
            advance_payment_required=True,
            max_participants=20,
            cost=10,
            payment_open=True,
            payment_due_date=now - timedelta(40),
        )
