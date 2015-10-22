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


class TicketCreateView(LoginRequiredMixin, TemplateView):

    template_name = 'booking/create_ticket_booking.html'

    def dispatch(self, request, *args, **kwargs):
        self.ticketed_event = get_object_or_404(
            TicketedEvent, slug=kwargs['event_slug'], show_on_site=True
        )
        if request.method.lower() == 'get':
            # get non-cancelled ticket bookings withough attached tickets yet
            user_empty_ticket_bookings = [
                tbk for tbk in TicketBooking.objects.filter(
                    user=self.request.user, ticketed_event=self.ticketed_event,
                    cancelled=False
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

            if self.ticketed_event.tickets_left() < quantity and \
                            quantity > q_existing_tickets:
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

                if q_existing_tickets > 0:
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
                    send_mail('{} Ticket booking ref {} for {}'.format(
                            settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,
                            self.ticket_booking.booking_reference,
                            self.ticketed_event
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
                        send_mail('{} Ticket booking ref {} for {}'.format(
                                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,
                                self.ticket_booking.booking_reference,
                                self.ticketed_event
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
            if not ticket_booking.cancelled and not ticket_booking.paid:
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
        self.ticket_booking = get_object_or_404(
            TicketBooking, booking_reference=kwargs['ref'], user=request.user
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
    fields = ('__all__')
    success_message = "Ticket booking reference {} has been cancelled"

    def check_and_redirect(self, request, ticket_booking):

        if ticket_booking.paid:
            messages.info(
                request,
                "Ticket booking ref {} has been paid and cannot be "
                "cancelled".format(ticket_booking.booking_reference)
            )
            return HttpResponseRedirect(reverse('booking:ticket_bookings'))
        if ticket_booking.ticketed_event.cancelled:
            messages.info(
                request,
                "Ticket booking ref {} is for a cancelled event and cannot be "
                "cancelled here.  Please contact the studio for "
                "information.".format(ticket_booking.booking_reference)
            )
            return HttpResponseRedirect(reverse('booking:ticket_bookings'))

        # redirect if booking cancelled
        if ticket_booking.cancelled:
            messages.info(
                request,
                "Ticket booking (ref {}) has already been cancelled".format(
                    ticket_booking.booking_reference
                )
            )
            return HttpResponseRedirect(reverse('booking:ticket_bookings'))

    def get(self, request, *args, **kwargs):
        # redirect if event cancelled
        ticket_booking = get_object_or_404(TicketBooking, id=self.kwargs['pk'])

        self.check_and_redirect(request, ticket_booking)
        return super(TicketBookingCancelView, self).get(request, *args, **kwargs)

    def form_valid(self, form):

        if "confirm_cancel" in form.data:
            ticket_booking = form.save(commit=False)
            self.check_and_redirect(self.request, ticket_booking)

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
                # send email to user; no need to send to studio
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


    # TODO
    # 1) deal with form errors - DONE
    # 2) activity log entries - DONE
    # 3) payment_not_open case ("confirm purchase" button doesn't return
    # paypalform, instead just shows message with payment info - for
    # cases where payment isn't being taken by paypal) - DONE
    # 4) only show ticketed_events if "show on site" is checked - DONE
    # 5) Add "my purchased tickets" view - DONE
    # 6) Emails when tickets purchased - DONE
    # ************* 7) Check paypal processes properly and emails are sent ************************
    # ************* 8) Allow people to cancel their ticket purchase before payment
    # but not after (cancel for unpaid ticket bookings on the "my
    # purchased tickets" page).  Cancelling sets the cancel flag on the ticket
    # booking but doesn't delete it or delete the tickets *****************************************
    # ************* 9) reminder, warnings and Cancel manage commands for Cron jobs ****************
    # - cancel ticket bookings with purchase_confirmed that are
    # not paid by payment due date or within the allowed hours of booked date.
    # - delete ticket bookings without purchase_confirmed that are > 1 hour after
    # booking date (ie. ticket booking started but not completed and user
    # navigated away from page instead of pressing cancel button)
    # 10) StudioAdmin -
    # ******************- cancelling events with tickets purchased ******************
    # cancelling event cancels all ticket bookings; email all users for ticket
    # bookings and studio
    # - ticket booking list - allow updating paid - DONE
    # ****************** - ticket lists - printable - select event, tick info to display, choose ordering ******************
    # 11) TicketBooking formset view for users to edit their ticket info - DONE
    # ************ 12) tests **********************************************************************