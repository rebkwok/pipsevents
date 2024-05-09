"""
Update prices for blocktypes, events and timetable session from a json file. Expected format:
{
    "blocktype": [
        {
            "identifier": "standard",
            "size": 3,
            "price": 36.00
        },
        ...
    ],
    "event": [
        {
            "event_type": "CL",
            "subtype": "Pole level class",
            "price": 13.00
        },
        ...
    ],
    "session": [
        {
            "event_type": "CL",
            "subtype": "Pole level class",
            "price": 13.00
        },
        ...
    ]
}

"""
import json
from pathlib import Path

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.utils import timezone

from booking.models import BlockType, Event
from timetable.models import Session as TimetableSession

from activitylog.models import ActivityLog


class Command(BaseCommand):
    help = 'activate/deactivate blocktypes with by identifier'

    def add_arguments(self, parser):
        parser.add_argument('prices', type=Path, help="path to prices json file")
        parser.add_argument('-l', "--live-run", action="store_true", help="path to prices json file")

    def handle(self, prices, **options):
        dry_run = not options.get("live_run")
        new_prices = json.loads(prices.read_text())
        blocktype_prices = new_prices["blocktype"]
        event_prices = new_prices["event"]
        session_prices = new_prices["session"]

        for new_price in blocktype_prices:
            block_types = BlockType.objects.filter(
                identifier=new_price["identifier"],
                size=new_price["size"]
            )
            if dry_run:
                self.stdout.write(f"{block_types.count()} {new_price['identifier']} block types (size {new_price['size']}) would be updated to new price £{new_price['price']}")
            else:
                block_types.update(cost=new_price["price"])
                ActivityLog.objects.create(
                    log=f"Prices for {block_types.count()} {new_price['identifier']} block types (size {new_price['size']}) updated to new price £{new_price['price']}"
                )
        
        for new_price in event_prices:
            events = Event.objects.filter(
                date__gt=timezone.now(),
                event_type__event_type=new_price["event_type"],
                event_type__subtype=new_price["subtype"],
            )
            if dry_run:
                self.stdout.write(f"{events.count()} events ({new_price['event_type']} - {new_price['subtype']}) would be updated to new price £{new_price['price']}")
            else:
                events.update(cost=new_price["price"])
                ActivityLog.objects.create(
                    log=f"Prices for {events.count()} events ({new_price['event_type']} - {new_price['subtype']}) updated to new price £{new_price['price']}"
                )

        for new_price in session_prices:
            ts = TimetableSession.objects.filter(
                event_type__event_type=new_price["event_type"],
                event_type__subtype=new_price["subtype"],
            )
            if dry_run:
                self.stdout.write(f"{ts.count()} timetable sessions ({new_price['event_type']} - {new_price['subtype']}) would be updated to new price £{new_price['price']}")
            else:
                ts.update(cost=new_price["price"])
                ActivityLog.objects.create(
                    log=f"Prices for {ts.count()} timetable sessions ({new_price['event_type']} - {new_price['subtype']}) updated to new price £{new_price['price']}"
                )
