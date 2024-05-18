# -*- coding: utf-8 -*-

import logging
import pytz
import shortuuid

from decimal import Decimal

from django.db import models
from django.conf import settings
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from django_extensions.db.fields import AutoSlugField

from datetime import timedelta


logger = logging.getLogger(__name__)


class TicketBookingError(Exception):
    pass


class TicketedEvent(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    date = models.DateTimeField()
    location = models.CharField(max_length=255, default="Watermelon Studio")
    max_tickets = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Leave blank if no max number"
    )
    contact_person = models.CharField(max_length=255, default="Gwen Holbrey")
    contact_email = models.EmailField(default=settings.DEFAULT_STUDIO_EMAIL)
    ticket_cost = models.DecimalField(default=0, max_digits=8, decimal_places=2)
    advance_payment_required = models.BooleanField(default=True)
    show_on_site = models.BooleanField(
        default=True, help_text="Tick to show on the site and allow ticket bookings")
    payment_open = models.BooleanField(default=True)
    payment_info = models.TextField(blank=True)
    payment_due_date = models.DateTimeField(
        null=True, blank=True,
        help_text='Tickets that are not paid by the payment due date '
                  'will be automatically cancelled (a warning email will be '
                  'sent to users first).')
    payment_time_allowed = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Number of hours allowed for payment after booking (after "
                  "this ticket purchases will be cancelled.  Note that the "
                  "automatic cancel job allows 6 hours after booking, so "
                  "6 hours is the minimum time that will be applied."
    )
    email_studio_when_purchased = models.BooleanField(default=False)
    max_ticket_purchase = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Limit the number of tickets that can be "
                             "purchased at one time"
    )
    extra_ticket_info_label = models.CharField(
        max_length=255, blank=True, default=''
    )
    extra_ticket_info_help = models.CharField(
        max_length=255, blank=True, default='',
        help_text="Description/details/help text to display under the extra "
                  "info field"
    )
    extra_ticket_info_required = models.BooleanField(
        default=False,
        help_text="Tick if this information is mandatory when booking tickets"
    )
    extra_ticket_info1_label = models.CharField(
        max_length=255, blank=True, default=''
    )
    extra_ticket_info1_help = models.CharField(
        max_length=255, blank=True, default='',
        help_text="Description/details/help text to display under the extra "
                  "info field"
    )
    extra_ticket_info1_required = models.BooleanField(
        default=False,
        help_text="Tick if this information is mandatory when booking tickets"
    )
    cancelled = models.BooleanField(default=False)
    slug = AutoSlugField(populate_from='name', max_length=40, unique=True)
    paypal_email = models.EmailField(
        default="thewatermelonstudio@hotmail.com",
        help_text='Email for the paypal account to be used for payment.  '
                  'Check this carefully!'
    )

    class Meta:
        ordering = ['-date']

    def tickets_left(self):
        if self.max_tickets:
            ticket_bookings = TicketBooking.objects.filter(
                ticketed_event__id=self.id, cancelled=False,
                purchase_confirmed=True
            )
            booked_number = Ticket.objects.filter(
                ticket_booking__in=ticket_bookings
            ).count()
            return self.max_tickets - booked_number
        else:
            # if there is no max_tickets, return an unfeasibly high number
            return 10000

    def bookable(self):
        return self.tickets_left() > 0

    def __str__(self):
        return '{} - {}'.format(
            str(self.name),
            self.date.astimezone(
                pytz.timezone('Europe/London')
            ).strftime('%d %b %Y, %H:%M')
        )

    def save(self, *args, **kwargs):
        if not self.ticket_cost:
            self.advance_payment_required = False
            self.payment_open = False
            self.payment_due_date = None
            self.payment_time_allowed = None
        if self.payment_due_date:
            # replace time with very end of day
            # move forwards 1 day and set hrs/min/sec/microsec to 0, then move
            # back 1 sec
            next_day = (self.payment_due_date + timedelta(
                days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            self.payment_due_date = next_day - timedelta(seconds=1)
            # if a payment due date is set, make sure advance_payment_required is
            # set to True
            self.advance_payment_required = True
        if self.payment_time_allowed:
            self.advance_payment_required = True
        super(TicketedEvent, self).save(*args, **kwargs)


class TicketedEventWaitingListUser(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="ticketed_event_waiting_lists")
    ticketed_event = models.ForeignKey(
        TicketedEvent, related_name="waiting_list_users", on_delete=models.CASCADE
    )
    date_joined = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.user.username} - {self.ticketed_event}"


class TicketBooking(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="ticket_bookings")
    ticketed_event = models.ForeignKey(
        TicketedEvent, related_name="ticket_bookings", on_delete=models.CASCADE
    )
    date_booked = models.DateTimeField(default=timezone.now)
    paid = models.BooleanField(default=False)

    # cancelled flag so we can cancel unpaid ticket purchases
    # do not allow reopening of cancelled ticket bookings
    cancelled = models.BooleanField(default=False)

    # Flags for email reminders and warnings
    reminder_sent = models.BooleanField(default=False)
    warning_sent = models.BooleanField(default=False)
    date_warning_sent = models.DateTimeField(null=True, blank=True)

    booking_reference = models.CharField(max_length=255)
    purchase_confirmed = models.BooleanField(default=False)

    # stripe payments
    invoice = models.ForeignKey("stripe_payments.Invoice", on_delete=models.SET_NULL, null=True, blank=True, related_name="ticket_bookings")
    checkout_time = models.DateTimeField(null=True, blank=True)

    def set_booking_reference(self):
        self.booking_reference = shortuuid.ShortUUID().random(length=22)

    def mark_checked(self):
        self.checkout_time = timezone.now()
        self.save()

    @property
    def cost(self):
        return Decimal(
            self.ticketed_event.ticket_cost * self.tickets.count()
        ).quantize(Decimal(".01"))

    def __str__(self):
        return 'Booking ref {} - {} - {}'.format(
            self.booking_reference, self.ticketed_event.name, self.user.username
        )

    def save(self, *args, **kwargs):
        if self.pk is None:
            if self.ticketed_event.tickets_left() <= 0:
                raise TicketBookingError(
                    'No tickets left for {}'.format(self.ticketed_event)
                )
            self.set_booking_reference()
        if self.warning_sent and not self.date_warning_sent:
            self.date_warning_sent = timezone.now()
        super(TicketBooking, self).save(*args, **kwargs)


class Ticket(models.Model):
    extra_ticket_info = models.TextField(blank=True, default='')
    extra_ticket_info1 = models.TextField(blank=True, default='')
    ticket_booking = models.ForeignKey(
        TicketBooking, related_name="tickets", on_delete=models.CASCADE
    )

    def save(self, *args, **kwargs):
        # raise error for each ticket creation also if we try to book for a
        #  full event
        if self.pk is None:
            if self.ticket_booking.ticketed_event.tickets_left() <= 0:
                raise TicketBookingError(
                    'No tickets left for {}'.format(
                        self.ticket_booking.ticketed_event
                    )
                )
        super(Ticket, self).save(*args, **kwargs)
