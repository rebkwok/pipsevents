import logging

from django.conf import settings
from django.contrib import messages
from django.template.loader import get_template
from django.template import Context
from django.shortcuts import HttpResponse, HttpResponseRedirect, render, \
    get_object_or_404
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView, FormView, TemplateView
)
from django.template.response import TemplateResponse
from django.core.mail import send_mail
from django.core.urlresolvers import reverse
from django.utils import timezone
from django.utils.safestring import mark_safe
from braces.views import LoginRequiredMixin

from booking.models import TicketedEvent, TicketBooking, Ticket
from booking.forms import TicketFormSet, TicketPurchaseForm
import booking.context_helpers as context_helpers
from booking.email_helpers import send_support_email, send_waiting_list_email

from payments.forms import PayPalPaymentsUpdateForm, PayPalPaymentsListForm
from payments.helpers import create_ticket_booking_paypal_transaction

from activitylog.models import ActivityLog

logger = logging.getLogger(__name__)


class TicketedEventListView(ListView):
    model = TicketedEvent
    context_object_name = 'ticketed_events'
    template_name = 'booking/ticketed_events.html'

    def get_queryset(self):
        return TicketedEvent.objects.filter(
            date__gte=timezone.now(), show_on_site=True, cancelled=False
        )

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(TicketedEventListView, self).get_context_data(**kwargs)
        if not self.request.user.is_anonymous():
            # Add in the booked events

            tickets_booked_events = [
                tbk.ticketed_event for tbk in TicketBooking.objects.filter(
                    user=self.request.user, cancelled=False,
                    purchase_confirmed=True
                ) if tbk.tickets.exists()
            ]
            context['tickets_booked_events'] = tickets_booked_events

        if self.request.user.is_staff:
            context['not_visible_events'] = TicketedEvent.objects.filter(
                date__gte=timezone.now(), show_on_site=False
            )

        return context


class TicketCreateView(LoginRequiredMixin, TemplateView):

    template_name = 'booking/create_ticket_booking.html'

    def dispatch(self, request, *args, **kwargs):
        # allow staff users to see this page for not show_on_site events too
        if request.user.is_staff:
            self.ticketed_event = get_object_or_404(
                TicketedEvent, slug=kwargs['event_slug'],
                cancelled=False
            )
        else:
            self.ticketed_event = get_object_or_404(
                TicketedEvent, slug=kwargs['event_slug'], show_on_site=True,
                cancelled=False
            )

        if not request.user.is_anonymous():
            if request.method.lower() == 'get':
                # get non-cancelled and unconfirmed ticket bookings
                user_unconfirmed_ticket_bookings = TicketBooking.objects.filter(
                        user=self.request.user,
                    ticketed_event=self.ticketed_event,
                        cancelled=False,
                        purchase_confirmed=False
                    )

                if user_unconfirmed_ticket_bookings:
                    self.ticket_booking = user_unconfirmed_ticket_bookings[0]
                else:
                    self.ticket_booking = TicketBooking.objects.create(
                        user=self.request.user,
                        ticketed_event=self.ticketed_event
                    )
            elif request.method.lower() == 'post':
                ticket_bk_id = request.POST['ticket_booking_id']
                # first check this ticket booking exists, in case the user never
                # confirmed and is returning to this page after an hour or more
                # and it's been automatically deleted
                try:
                    self.ticket_booking = TicketBooking.objects.get(
                        pk=ticket_bk_id
                    )
                except TicketBooking.DoesNotExist:
                    return HttpResponseRedirect(
                        reverse(
                            'booking:ticket_purchase_expired',
                            kwargs={'slug': self.ticketed_event.slug}
                        )
                    )

        return super(TicketCreateView, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(TicketCreateView, self).get_context_data(**kwargs)
        context['ticketed_event'] = self.ticketed_event
        context['ticket_booking'] = self.ticket_booking

        ticket_purchase_form = TicketPurchaseForm(
            prefix='ticket_purchase_form',
            ticketed_event=self.ticketed_event,
            ticket_booking=self.ticket_booking,
            data=self.request.POST if 'ticket_purchase_form-quantity'
                                        in self.request.POST else None,
        )
        context['ticket_purchase_form'] = ticket_purchase_form
        context['ticket_formset'] = TicketFormSet(
            prefix='ticket_formset',
            data=self.request.POST if 'ticket_formset-submit'
                                        in self.request.POST else None,
            instance=self.ticket_booking,
            ticketed_event=self.ticketed_event,
        )
        return context

    def post(self, request, *args, **kwargs):
        if 'cancel' in request.POST:
            self.ticket_booking.delete()
            messages.info(
                request,
                'Ticket booking for {} has been cancelled.'.format(
                    self.ticketed_event
                )
            )
            return HttpResponseRedirect(reverse('booking:ticketed_events'))

        context = self.get_context_data()
        ticket_purchase_form = context['ticket_purchase_form']
        ticket_formset = context['ticket_formset']

        if ticket_purchase_form.has_changed():
            # tickets on current booking are only included in the tickets_left
            # calculation if purchase has been confirmed
            old_tickets = self.ticket_booking.tickets.all()
            old_ticket_count = old_tickets.count()

            if self.ticket_booking.purchase_confirmed:
                tickets_left_excl_this = self.ticketed_event.tickets_left() \
                                            + old_ticket_count
            else:
                tickets_left_excl_this = self.ticketed_event.tickets_left()

            new_quantity = int(request.POST.get('ticket_purchase_form-quantity'))

            if new_quantity > tickets_left_excl_this:
                messages.error(
                    request, 'Cannot purchase the number of tickets requested.  '
                             'Only {} tickets left.'.format(
                        self.ticketed_event.tickets_left()
                    )
                )
            else:
                # create the correct number of tickets on this booking
                if old_ticket_count < new_quantity:
                    for i in range(new_quantity-old_ticket_count):
                        Ticket.objects.create(ticket_booking=self.ticket_booking)
                if old_ticket_count > new_quantity:
                    for ticket in old_tickets[new_quantity:]:
                        ticket.delete()

                if old_ticket_count > 0:
                    ActivityLog.objects.create(
                        log="Ticket number updated on booking ref {}".format(
                            self.ticket_booking.booking_reference
                            )
                    )

            tickets = self.ticket_booking.tickets.all()
            context['tickets'] = tickets

            return TemplateResponse(request, self.template_name, context)

        if 'ticket_formset-submit' in request.POST:
            if ticket_formset.is_valid():
                ticket_formset.save()

                # we only create the paypal form if there is a ticket cost and
                # online payments are open
                if self.ticketed_event.ticket_cost and \
                        self.ticketed_event.payment_open:
                    invoice_id = create_ticket_booking_paypal_transaction(
                        self.request.user, self.ticket_booking
                    ).invoice_id
                    host = 'http://{}'.format(self.request.META.get('HTTP_HOST')
                                                      )
                    paypal_form = PayPalPaymentsUpdateForm(
                        initial=context_helpers.get_paypal_dict(
                            host,
                            self.ticketed_event.ticket_cost,
                            self.ticketed_event,
                            invoice_id,
                            '{} {}'.format('ticket_booking', self.ticket_booking.id),
                            quantity=self.ticket_booking.tickets.count()
                        )
                    )
                    context["paypalform"] = paypal_form
                self.ticket_booking.purchase_confirmed = True
                # reset the ticket_booking booked date to the date user confirms
                context['purchase_confirmed'] = True
                self.ticket_booking.date_booked = timezone.now()
                self.ticket_booking.save()
                ActivityLog.objects.create(
                    log="Ticket Purchase confirmed: event {}, user {}, "
                        "booking ref {}".format(
                            self.ticketed_event.name, request.user.username,
                            self.ticket_booking.booking_reference
                        )
                )

                host = 'http://{}'.format(request.META.get('HTTP_HOST'))
                ctx = Context({
                      'host': host,
                      'ticketed_event': self.ticketed_event,
                      'ticket_booking': self.ticket_booking,
                      'ticket_count': self.ticket_booking.tickets.count(),
                      'user': request.user,
                })

                try:
                    # send notification email to user
                    send_mail('{} Ticket booking confirmed for {}: ref {}'.format(
                            settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,
                            self.ticketed_event,
                            self.ticket_booking.booking_reference,

                        ),
                        get_template(
                            'booking/email/ticket_booking_made.txt'
                        ).render(ctx),
                        settings.DEFAULT_FROM_EMAIL,
                        [request.user.email],
                        html_message=get_template(
                            'booking/email/ticket_booking_made.html'
                            ).render(ctx),
                        fail_silently=False)
                except Exception as e:
                    # send mail to tech support with Exception
                    send_support_email(
                        e, __name__, "ticket booking created - "
                        "send email to user"
                    )

                if self.ticketed_event.email_studio_when_purchased:
                    try:
                        send_mail('{} Ticket booking confirmed for {}: ref {}'.format(
                                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,
                                self.ticketed_event,
                                self.ticket_booking.booking_reference,
                            ),
                            get_template(
                                'booking/email/to_studio_ticket_booking_made.txt'
                            ).render(ctx),
                            settings.DEFAULT_FROM_EMAIL,
                            [settings.DEFAULT_STUDIO_EMAIL],
                            html_message=get_template(
                                'booking/email/to_studio_ticket_booking_made.html'
                                ).render(ctx),
                            fail_silently=False)
                    except Exception as e:
                        # send mail to tech support with Exception
                        send_support_email(
                            e, __name__, "ticket booking created - "
                            "send email to studio"
                        )
            else:
                messages.error(
                    request, "Please correct errors in the form below"
                )

            tickets = self.ticket_booking.tickets.all()
            context['tickets'] = tickets
            ticket_purchase_form = TicketPurchaseForm(
                prefix='ticket_purchase_form',
                ticketed_event=self.ticketed_event,
                ticket_booking=self.ticket_booking,
                initial={'quantity': self.ticket_booking.tickets.count()}
            )
            context["ticket_purchase_form"] = ticket_purchase_form
            return TemplateResponse(request, self.template_name, context)


class TicketBookingListView(LoginRequiredMixin, ListView):

    model = TicketBooking
    context_object_name = 'ticket_bookings'
    template_name = 'booking/ticket_bookings.html'

    def get_queryset(self):
        return TicketBooking.objects.filter(
            ticketed_event__date__gte=timezone.now(), user=self.request.user,
            purchase_confirmed=True
        ).order_by('ticketed_event__date')

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(TicketBookingListView, self).get_context_data(**kwargs)

        ticketbookinglist = []
        for ticket_booking in self.object_list:
            if not ticket_booking.cancelled and not ticket_booking.paid \
                    and ticket_booking.ticketed_event.payment_open:
                # ONLY DO THIS IF PAYPAL BUTTON NEEDED
                invoice_id = create_ticket_booking_paypal_transaction(
                    self.request.user, ticket_booking).invoice_id
                host = 'http://{}'.format(self.request.META.get('HTTP_HOST'))
                paypal_form = PayPalPaymentsListForm(
                    initial=context_helpers.get_paypal_dict(
                        host,
                        ticket_booking.ticketed_event.ticket_cost,
                        ticket_booking.ticketed_event,
                        invoice_id,
                        '{} {}'.format('ticket_booking', ticket_booking.id),
                        quantity=ticket_booking.tickets.count()
                    )
                )
            else:
                paypal_form = None

            ticketbookingform = {
                'ticket_booking': ticket_booking,
                'paypalform': paypal_form
                }
            ticketbookinglist.append(ticketbookingform)
        context['ticketbookinglist'] = ticketbookinglist
        return context


class TicketBookingHistoryListView(LoginRequiredMixin, ListView):

    model = TicketBooking
    context_object_name = 'ticket_bookings'
    template_name = 'booking/ticket_bookings.html'

    def get_queryset(self):
        return TicketBooking.objects.filter(
            ticketed_event__date__lt=timezone.now(), user=self.request.user,
            purchase_confirmed=True
        ).order_by('ticketed_event__date')

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(
            TicketBookingHistoryListView, self
        ).get_context_data(**kwargs)
        # Add in the history flag
        context['history'] = True

        ticketbookinglist = []
        for ticket_booking in self.object_list:
            ticketbookingform = {'ticket_booking': ticket_booking}
            ticketbookinglist.append(ticketbookingform)
        context['ticketbookinglist'] = ticketbookinglist
        return context


class TicketBookingView(LoginRequiredMixin, TemplateView):

    template_name = 'booking/ticket_booking.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_anonymous():
            self.ticket_booking = get_object_or_404(
                TicketBooking, booking_reference=kwargs['ref'],
                purchase_confirmed=True,
                user=request.user
            )
        return super(TicketBookingView, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(TicketBookingView, self).get_context_data(**kwargs)
        context['ticketed_event'] = self.ticket_booking.ticketed_event
        context['ticket_booking'] = self.ticket_booking

        context['ticket_formset'] = TicketFormSet(
            prefix='ticket_formset',
            data=self.request.POST if 'ticket_formset-submit'
                                        in self.request.POST else None,
            instance=self.ticket_booking,
            ticketed_event=self.ticket_booking.ticketed_event,
        )
        tickets = self.ticket_booking.tickets.all()
        context['tickets'] = tickets

        return context

    def post(self, request, *args, **kwargs):
        context = self.get_context_data()
        ticket_formset = context['ticket_formset']

        if 'ticket_formset-submit' in request.POST:
            if ticket_formset.is_valid():
                if not ticket_formset.has_changed():
                    messages.info(request, "No changes made")
                else:
                    ticket_formset.save()

                    ActivityLog.objects.create(
                        log="Ticket info updated by {} for booking ref {}".format(
                            request.user.username,
                            self.ticket_booking.booking_reference
                        )
                    )

                    messages.success(
                        request, "Ticket information for booking reference {} "
                                 "updated".format(
                            self.ticket_booking.booking_reference
                        )
                    )
                return HttpResponseRedirect(
                    reverse('booking:ticket_bookings')
                )
            else:
                messages.error(
                    request, "Please correct errors in the form below"
                )

        return TemplateResponse(request, self.template_name, context)


class TicketBookingCancelView(LoginRequiredMixin, UpdateView):

    model = TicketBooking
    template_name = 'booking/cancel_ticket_booking.html'
    context_object_name = 'ticket_booking'
    fields = ('id',)
    success_message = "Ticket booking reference {} has been cancelled"

    def check_and_redirect(self, request, ticket_booking):

        if ticket_booking.paid:
            return "Ticket booking ref {} has been paid and cannot be " \
                "cancelled".format(ticket_booking.booking_reference)
        elif ticket_booking.ticketed_event.cancelled:
            return "Ticket booking ref {} is for a cancelled event and " \
                   "cannot be cancelled here.  Please contact the studio " \
                   "for information.".format(ticket_booking.booking_reference)
        # redirect if booking cancelled
        elif ticket_booking.cancelled:
            return "Ticket booking (ref {}) has already been cancelled".format(
                    ticket_booking.booking_reference
                )
        else:
            return None

    def get(self, request, *args, **kwargs):
        # redirect if event cancelled
        ticket_booking = get_object_or_404(TicketBooking, pk=self.kwargs['pk'])

        self.check_and_redirect(request, ticket_booking)
        return super(TicketBookingCancelView, self).get(request, *args, **kwargs)

    def form_valid(self, form):

        if "confirm_cancel" in form.data:
            ticket_booking = form.save(commit=False)
            err_msg = self.check_and_redirect(self.request, ticket_booking)
            if err_msg:
                messages.info(self.request, err_msg)
                return HttpResponseRedirect(reverse('booking:ticket_bookings'))

            ticket_booking.cancelled = True
            ticket_booking.save()
            ActivityLog.objects.create(
                log='Ticket booking ref {} (for {}) has been cancelled by '
                    'user {}'.format(
                        ticket_booking.booking_reference,
                        ticket_booking.ticketed_event,
                        ticket_booking.user.username,
                    )
            )

            try:
                # send email and set messages
                host = 'http://{}'.format(self.request.META.get('HTTP_HOST'))
                # send email to user; no need to send to studio as cancelled
                # before payment
                ctx = Context({
                      'host': host,
                      'ticket_booking': ticket_booking,
                })
                send_mail('{} Ticket booking ref {} cancelled'.format(
                        settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,
                        ticket_booking.booking_reference,
                    ),
                    get_template(
                        'booking/email/ticket_booking_cancelled.txt'
                    ).render(ctx),
                    settings.DEFAULT_FROM_EMAIL,
                    [self.request.user.email],
                    html_message=get_template(
                        'booking/email/ticket_booking_cancelled.html'
                        ).render(ctx),
                    fail_silently=False)

            except Exception as e:
                # send mail to tech support with Exception
                send_support_email(
                    e, __name__, "TicketBookingCancelView - user email"
                )
                messages.error(
                    self.request,
                    "An error occured, please contact the studio for "
                    "information"
                )

            messages.success(
                self.request, self.success_message.format(
                   ticket_booking.booking_reference
               )
            )
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('booking:ticket_bookings')


def ticket_purchase_expired(request, slug):
    ticketed_event = get_object_or_404(
        TicketedEvent, slug=slug
    )
    return render(
        request, 'booking/ticket_purchase_expired.html',
        {'ticketed_event': ticketed_event}
    )
