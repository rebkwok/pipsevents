from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from datetime import timedelta
from booking.models import Event


class Command(BaseCommand):

    def handle(self, *args, **options):

        self.stdout.write("Creating events")
        now = timezone.now()
        # create 2 with defaults, 1 with max participants
        Event.objects.create(
            name="Workshop",
            description="Workshop with awesome unnamed instructor!",
            date=now + timedelta(30),
            max_participants=20,
            cost=10,
            payment_info="Please pay by paypal to contact email.",
            payment_due_date=now + timedelta(40),
        )

        Event.objects.create(
            name="Pips outing",
            description="Outing for pips to play!",
            location="The pub",
            date=now + timedelta(20),
            cost=5,
            payment_info="Please pay by paypal to contact email.",
            payment_due_date=now + timedelta(30),
        )

        # create 2 with no costs
        Event.objects.create(
            name="Party",
            description="Watermelon party",
            date=now + timedelta(10),
        )

        Event.objects.create(
            name="Free event",
            description="Watermelon event",
            date=now + timedelta(25),
        )

        # non-default contact
        Event.objects.create(
            name="Workshop 1",
            description="Workshop with another awesome unnamed instructor!",
            date=now + timedelta(30),
            max_participants=20,
            cost=10,
            contact_person="Becky",
            contact_email="rebkwok@gmail.com",
            payment_info="Please pay by paypal to contact email.",
            payment_due_date=now + timedelta(40),
        )

        # with open payments
        Event.objects.create(
            name="Workshop 2",
            description="Workshop with yet another awesome unnamed instructor!",
            date=now + timedelta(45),
            max_participants=20,
            cost=10,
            payment_open=True,
            contact_person="Becky",
            contact_email="rebkwok@gmail.com",
            payment_info="Please pay by paypal to contact email.",
            payment_due_date=now + timedelta(50),
        )
