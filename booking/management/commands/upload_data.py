import argparse
import csv
from datetime import datetime
from django.utils import timezone
from django.core import management
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User

from booking.models import Block, BlockType, Booking, Event
from activitylog.models import ActivityLog


class Command(BaseCommand):

    def add_arguments(self, parser):
        # Positional arguments
        # parser.add_argument('infile', nargs='+')
        parser.add_argument('infile', nargs='+', type=argparse.FileType('r'))
        parser.parse_args(['-'])

    def handle(self, *args, **options):

        file = options['infile'][0]
        csvreader = csv.reader(file)
        lines = [row for row in csvreader]

        for line in lines[1:]:
            assert len(line) == 23

            first_name = line[0].strip()
            last_name = line[1]
            email = line[2]
            initials = [name[0] for name in last_name.lower().split(' ')]
            username = first_name.lower() + ''.join(initials)
            password = username
            # create user
            user, created = User.objects.get_or_create(
                first_name=first_name,
                last_name=last_name,
                email=email,
                username=username)
            if created:
                user.set_password(password)
                user.save()

            self.stdout.write(
                "User {} with email {} {}".format(
                    user.username, user.email, 'created' if created else 'already exists'
                )
            )
            if created:
                ActivityLog.objects.create(
                    log="User {} with email {} created".format(
                        user.username, user.email
                    )
                )

            class_block = line[3] # this is either 5 or 10
            if class_block:
                class_block_type = BlockType.objects.get(
                    event_type__subtype='Pole level class', size=int(class_block)
                )
                block_start_date = datetime.strptime(
                    line[4], '%d-%b-%Y'
                ).replace(tzinfo=timezone.utc)
                block, block_created = Block.objects.get_or_create(
                    block_type=class_block_type,
                    user=user,
                    start_date=block_start_date,
                    paid=True)

                self.stdout.write(
                    "Block {} {}".format(
                        block, 'created' if block_created else 'already exists'
                    )
                )
                class_blocks_used = int(line[5]) # the number of dummy classes to make

                if block_created:
                    ActivityLog.objects.create(
                        log="Block {} set up ({} total, {} already used)".format(
                            block,
                            class_block,
                            class_blocks_used
                        )
                    )

                class_block_event_ids_str = [booking.split('#')[-1] for booking in line[6:8]]
                class_block_event_ids = [int(booking_id) for booking_id in class_block_event_ids_str if booking_id]
                class_block_events = Event.objects.filter(id__in=class_block_event_ids)
                # create dummy bookings and upcoming bookings
                dummy_classes = [
                    event for event in Event.objects.filter(
                        name__contains="Dummy class"
                    )
                ]
                self.stdout.write(
                    "{} class blocks used by user {}".format(
                        class_blocks_used, user.username
                    )
                )

                for i in range(class_blocks_used):
                    booking, created = Booking.objects.get_or_create(
                        event=dummy_classes[i], user=user, block=block
                    )
                    self.stdout.write(
                        "Dummy class {} for user {} {}".format(
                            i + 1,
                            user.username,
                            'created' if created else 'already exists'
                        )
                    )
                for event in class_block_events:
                    booking, created = Booking.objects.get_or_create(
                        event=event, user=user, block=block
                    )
                    self.stdout.write(
                        "Booking for user {}, class {} {}".format(
                            user.username,
                            event,
                            'created' if created else 'already exists'
                        )
                    )
                    if created:
                        ActivityLog.objects.create(
                            log="Booking for user {}, class {} created".format(
                                user.username,
                                event
                            )
                        )


            practice_block = line[9] # this is either 5 or 10
            if practice_block:
                practice_block_type = BlockType.objects.get(
                    event_type__subtype='Pole practice', size=int(practice_block)
                )
                block_start_date = datetime.strptime(
                    line[10], '%d-%b-%Y'
                ).replace(tzinfo=timezone.utc)
                block, block_created = Block.objects.get_or_create(
                    block_type=practice_block_type,
                    user=user,
                    start_date=block_start_date)

                self.stdout.write(
                    "Block {} {}".format(
                        block, 'created' if block_created else 'already exists'
                    )
                )
                practice_blocks_used = int(line[11]) # the number of dummy classes to make

                if block_created:
                    ActivityLog.objects.create(
                        log="Block {} set up ({} total, {} already used)".format(
                            block,
                            practice_block,
                            practice_blocks_used
                        )
                    )

                prac_block_event_ids_str = [booking.split('#')[-1] for booking in line[12:14]]
                practice_block_event_ids = [int(booking_id) for booking_id in prac_block_event_ids_str if booking_id]

                practice_block_events = Event.objects.filter(
                    id__in=practice_block_event_ids
                )

                # create dummy bookings and upcoming bookings
                dummy_practice_events = [
                    event for event in Event.objects.filter(
                        name__contains="Dummy practice"
                    )
                ]

                self.stdout.write(
                    "{} practice blocks used by user {}".format(
                        practice_blocks_used, user.username
                    )
                )
                for i in range(practice_blocks_used):
                    booking, created = Booking.objects.get_or_create(
                        event=dummy_practice_events[i], user=user, block=block
                    )
                    self.stdout.write(
                        "Dummy pole practice {} for user {} {}".format(
                            i + 1,
                            user.username,
                            'created' if created else 'already exists'
                        )
                    )
                for event in practice_block_events:
                    booking, created = Booking.objects.get_or_create(
                        event=event, user=user, block=block
                    )
                    self.stdout.write(
                        "Booking for user {}, {} {}".format(
                            user.username,
                            event,
                            'created' if created else 'already exists'
                        )
                    )
                    if created:
                        ActivityLog.objects.create(
                            log="Booking for user {}, {} created".format(
                                user.username,
                                event)
                        )
            # create non block bookings with paid status
            non_block_booking1 = line[15:17]
            non_block_booking2 = line[17:19]
            non_block_booking3 = line[19:21]
            non_block_booking4 = line[21:]
            non_block_bookings = [non_block_booking1, non_block_booking2, non_block_booking3, non_block_booking4]

            for booking_data in non_block_bookings:
                if booking_data[0]:
                    event_id = int(booking_data[0].split('#')[-1])
                    paid_str = booking_data[1].lower()[0]
                    paid = True if paid_str == "y" else False
                    payment_confirmed = True if paid_str == "y" else False
                    event = Event.objects.get(id=event_id)
                    booking, created = Booking.objects.get_or_create(
                        event=event, user=user
                    )
                    if created:
                        booking.paid = paid
                        booking.payment_confirmed = payment_confirmed
                        booking.block = None
                        booking.save()
    
                    self.stdout.write(
                        "Booking for user {}, class {} {}".format(
                            user.username,
                            event,
                            'created' if created else 'already exists'
                        )
                    )
                    if created:
                        ActivityLog.objects.create(
                            log="Booking for user {}, class {} created".format(
                                user.username,
                                event
                            )
                        )
