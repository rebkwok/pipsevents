import logging

from django.db.models import Q
from django.shortcuts import HttpResponseRedirect, render, get_object_or_404
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView, FormView, TemplateView
)
from django.utils import timezone
from braces.views import LoginRequiredMixin

from booking.models import TicketedEvent, TicketBooking, Ticket
from booking.forms import TicketFormSet, TicketPurchaseForm
import booking.context_helpers as context_helpers


logger = logging.getLogger(__name__)


class TicketedEventListView(ListView):
    model = TicketedEvent
    context_object_name = 'ticketed_events'
    template_name = 'booking/ticketed_events.html'

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
            TicketedEvent, slug=kwargs['event_slug']
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

        return super(TicketCreateView, self).dispatch(*args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(TicketCreateView, self).get_context_data(**kwargs)
        context['ticketed_event'] = self.ticketed_event
        context['ticket_booking'] = self.ticket_booking

        ticket_purchase_form = TicketPurchaseForm(
            prefix='ticket_purchase_form',
            ticket_booking=self.ticket_booking,
            data = self.request.POST if 'ticket_purchase_form'
                                        in self.request.POST else None,
        )
        context['ticket_purchase_form'] = ticket_purchase_form
        context['ticket_formset'] = []

        return context

    def post(self, request, *args, **kwargs):

        if 'ticket_purchase_form-submit' in request.POST:
            pass


class TicketPurchaseView(LoginRequiredMixin, TemplateView):

    template_name = 'booking/create_ticket_booking.html'

    def dispatch(self, request, *args, **kwargs):
        self.ticketed_event = get_object_or_404(
            TicketedEvent, slug=kwargs['event_slug']
        )
        self.ticket_booking = get_object_or_404(
            TicketBooking, booking_reference=kwargs['booking_ref']
        )

        return super(TicketPurchaseView, self).dispatch(*args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(TicketCreateView, self).get_context_data(**kwargs)
        context['ticketed_event'] = self.ticketed_event
        context['ticket_booking'] = self.ticket_booking

        ticket_purchase_form = TicketPurchaseForm(
            prefix='ticket_purchase_form',
            ticket_booking=self.ticket_booking,
            data = self.request.POST if 'ticket_purchase_form'
                                        in self.request.POST else None,
        )
        ticket_formset = TicketFormSet(
            prefix='ticket_formset',
            user=self.request.user,
            data = self.request.POST if 'ticket_formset'
                                        in self.request.POST else None,
        )
        context['ticket_purchase_form'] = ticket_purchase_form
        context['ticket_formset'] = ticket_formset

        return context