import logging

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import HttpResponse, HttpResponseRedirect, render, \
    get_object_or_404
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView, FormView, TemplateView
)
from django.template.response import TemplateResponse
from django.core.urlresolvers import reverse
from django.utils import timezone
from braces.views import LoginRequiredMixin

from booking.models import TicketedEvent, TicketBooking, Ticket
from booking.forms import TicketFormSet, TicketPurchaseForm
import booking.context_helpers as context_helpers

from payments.forms import PayPalPaymentsUpdateForm
from payments.helpers import create_ticket_booking_paypal_transaction

logger = logging.getLogger(__name__)


class TicketedEventListView(ListView):
    model = TicketedEvent
    context_object_name = 'ticketed_events'
    template_name = 'booking/ticketed_events.html'

    def get_queryset(self):
        return TicketedEvent.objects.filter(
            date__gte=timezone.now(), show_on_site=True
        )

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(TicketedEventListView, self).get_context_data(**kwargs)
        if not self.request.user.is_anonymous():
            # Add in the booked events

            tickets_booked_events = [
                tbk.ticketed_event for tbk in TicketBooking.objects.filter(
                    user=self.request.user, cancelled=False
                ) if tbk.tickets.exists()
            ]
            context['tickets_booked_events'] = tickets_booked_events

        return context


class TicketedEventDetailView(LoginRequiredMixin, DetailView):

    model = TicketedEvent
    context_object_name = 'ticketed_event'
    template_name = 'booking/ticketed_event.html'

    def get_object(self):
        queryset = TicketedEvent.objects.all()
        return get_object_or_404(queryset, slug=self.kwargs['slug'])

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(TicketedEventDetailView, self).get_context_data()
        ticketed_event = self.object
        return context_helpers.get_ticketed_event_context(
            context, ticketed_event, self.request.user
        )


"""
use same template but 2 differnt views?

TicketCreateView: for submitting the ticket_purchase_form
Creates/gets the ticket_booking on get
Creates the tickets on post based on the quantity submitted (checks the number
already on the ticketbooking and adds/deletes as necessary)
renders TicketPurchaseView

TicketPurchaseView: for submitting the ticket details
renders the same template, includes the formset
Post saves the ticket details, returns view with payment buttons

"""
class TicketCreateView(LoginRequiredMixin, TemplateView):

    template_name = 'booking/create_ticket_booking.html'

    def dispatch(self, request, *args, **kwargs):
        self.ticketed_event = get_object_or_404(
            TicketedEvent, slug=kwargs['event_slug'], show_on_site=True
        )
        if request.method.lower() == 'get':
            user_empty_ticket_bookings = [
                tbk for tbk in TicketBooking.objects.filter(
                    user=self.request.user, ticketed_event=self.ticketed_event
                ) if not tbk.tickets.exists()
                ]

            if user_empty_ticket_bookings:
                self.ticket_booking = user_empty_ticket_bookings[0]
            else:
                self.ticket_booking = TicketBooking.objects.create(
                    user=self.request.user, ticketed_event=self.ticketed_event
                )
        elif request.method.lower() == 'post':
            ticket_bk_id = request.POST['ticket_booking_id']
            self.ticket_booking = TicketBooking.objects.get(pk=ticket_bk_id)

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
            existing_tickets = self.ticket_booking.tickets.all()
            q_existing_tickets = existing_tickets.count()
            quantity = int(request.POST.get('ticket_purchase_form-quantity'))

            if self.ticketed_event.tickets_left() < quantity and quantity > q_existing_tickets:
                messages.error(
                    request, 'Cannot purchase the number of tickets requested.  '
                             'Only {} tickets left.'.format(
                        self.ticketed_event.tickets_left()
                    )
                )
            else:
                # create the correct number of tickets on this booking
                if q_existing_tickets < quantity:
                    for i in range(quantity-q_existing_tickets):
                        Ticket.objects.create(ticket_booking=self.ticket_booking)
                if q_existing_tickets > quantity:
                    for ticket in existing_tickets[quantity:]:
                        ticket.delete()

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
                context['purchase_confirmed'] = True
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

            # TODO
            # 1) deal with form errors
            # 2) activity log entries
            # 3) payment_not_open case ("confirm purchase" button doesn't return
            # paypalform, instead just shows message with payment info - for
            # cases where payment isn't being taken by paypal) - DONE
            # 4) only show ticketed_events if "show on site" is checked - DONE
            # 5) Add "my purchased tickets" view
            # 6) Emails when tickets purchased
            # 7) Check paypal processes properly and emails are sent
            # 8) Allow people to cancel their ticket purchase before payment
            # but not after (cancel for unpaid ticket bookings on the "my
            # purchased tickets" page
            # 9) reminder, warnings and Cancel manage commands
            # 10) StudioAdmin
            # 11) Cron jobs