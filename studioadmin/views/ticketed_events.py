import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.template.loader import get_template
from django.template.response import TemplateResponse
from django.shortcuts import HttpResponseRedirect, get_object_or_404
from django.views.generic import CreateView, UpdateView, TemplateView
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.core.mail import send_mail

from braces.views import LoginRequiredMixin

from booking.models import TicketBooking, Ticket, TicketedEvent
from booking.email_helpers import send_support_email

from studioadmin.forms import TicketedEventFormSet, TicketedEventAdminForm, \
    TicketBookingInlineFormSet, PrintTicketsForm

from studioadmin.views.helpers import staff_required, StaffUserMixin
from activitylog.models import ActivityLog


logger = logging.getLogger(__name__)


class TicketedEventAdminListView(
    LoginRequiredMixin, StaffUserMixin, TemplateView
):

    template_name = 'studioadmin/ticketed_events_admin_list.html'

    def get_context_data(self, **kwargs):
        context = super(
            TicketedEventAdminListView, self
        ).get_context_data(**kwargs)

        queryset = TicketedEvent.objects.filter(
                date__gte=timezone.now()
            ).order_by('date')

        if self.request.method == 'POST':
            if "past" in self.request.POST:
                queryset = TicketedEvent.objects.filter(
                    date__lte=timezone.now()
                ).order_by('date')
                context['show_past'] = True
            elif "upcoming" in self.request.POST:
                queryset = queryset
                context['show_past'] = False

        if queryset.count() > 0:
            context['ticketed_events'] = True

        ticketed_event_formset = TicketedEventFormSet(
            data=self.request.POST if 'formset_submitted' in self.request.POST
            else None,
            queryset=queryset if 'formset_submitted' not in self.request.POST
            else None,
        )
        context['ticketed_event_formset'] = ticketed_event_formset
        context['sidenav_selection'] = 'ticketed_events'
        return context

    def get(self, request, *args, **kwargs):
        context = self.get_context_data()
        return TemplateResponse(request, self.template_name, context)

    def post(self, request, *args, **kwargs):

        context = self.get_context_data(**kwargs)

        if "past" in self.request.POST or "upcoming" in self.request.POST:
            return TemplateResponse(request, self.template_name, context)

        if "formset_submitted" in request.POST:
            ticketed_event_formset = context['ticketed_event_formset']

            if ticketed_event_formset.is_valid():
                if not ticketed_event_formset.has_changed():
                    messages.info(request, "No changes were made")
                else:
                    for form in ticketed_event_formset:
                        if form.has_changed():
                            if 'DELETE' in form.changed_data:
                                messages.success(
                                    request, mark_safe(
                                        'Event <strong>{}</strong> has been '
                                        'deleted!'.format(
                                            form.instance,
                                        )
                                    )
                                )
                                ActivityLog.objects.create(
                                    log='Ticketed Event {} (id {}) deleted by '
                                        'admin user {}'.format(
                                        form.instance,
                                        form.instance.id, request.user.username
                                    )
                                )
                            else:
                                for field in form.changed_data:
                                    messages.success(
                                        request, mark_safe(
                                            "<strong>{}</strong> updated for "
                                            "<strong>{}</strong>".format(
                                                field.title().replace("_", " "),
                                                form.instance))
                                    )

                                    ActivityLog.objects.create(
                                        log='Ticketed Event {} (id {}) updated '
                                            'by admin user {}: field_'
                                            'changed: {}'.format(
                                            form.instance, form.instance.id,
                                            request.user.username,
                                            field.title().replace("_", " ")
                                        )
                                    )
                            form.save()

                        for error in form.errors:
                            messages.error(
                                request, mark_safe("{}".format(error))
                            )
                    ticketed_event_formset.save()
                return HttpResponseRedirect(
                    reverse('studioadmin:ticketed_events')
                )

            else:
                messages.error(
                    request,
                    mark_safe(
                        "There were errors in the following fields:\n{}".format(
                            '\n'.join(
                                ["{}".format(error)
                                 for error in ticketed_event_formset.errors]
                            )
                        )
                    )
                )
                return TemplateResponse(request, self.template_name, context)


class TicketedEventAdminUpdateView(
    LoginRequiredMixin, StaffUserMixin, UpdateView
):

    form_class = TicketedEventAdminForm
    model = TicketedEvent
    template_name = 'studioadmin/ticketed_event_create_update.html'
    context_object_name = 'ticketed_event'

    def get_object(self):
        queryset = TicketedEvent.objects.all()
        return get_object_or_404(queryset, slug=self.kwargs['slug'])

    def get_context_data(self, **kwargs):
        context = super(
            TicketedEventAdminUpdateView, self
        ).get_context_data(**kwargs)
        context['sidenav_selection'] = 'ticketed_events'
        return context

    def form_valid(self, form):
        if form.has_changed():
            ticketed_event = form.save()
            msg = 'Event <strong> {}</strong> has been updated!'.format(
                ticketed_event.name
            )
            ActivityLog.objects.create(
                log='Ticketed event {} (id {}) updated by admin user {}'.format(
                    ticketed_event, ticketed_event.id,
                    self.request.user.username
                )
            )
        else:
            msg = 'No changes made'
        messages.success(self.request, mark_safe(msg))
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('studioadmin:ticketed_events')


class TicketedEventAdminCreateView(
    LoginRequiredMixin, StaffUserMixin, CreateView
):

    form_class = TicketedEventAdminForm
    model = TicketedEvent
    template_name = 'studioadmin/ticketed_event_create_update.html'
    context_object_name = 'ticketed_event'

    def get_context_data(self, **kwargs):
        context = super(
            TicketedEventAdminCreateView, self
        ).get_context_data(**kwargs)
        context['sidenav_selection'] = 'add_ticketed_event'
        return context

    def form_valid(self, form):
        ticketed_event = form.save()
        messages.success(
            self.request, mark_safe('Event <strong> {}</strong> has been '
                                    'created!'.format(ticketed_event.name))
        )
        ActivityLog.objects.create(
            log='Ticketed Event {} (id {}) created by admin user {}'.format(
                ticketed_event, ticketed_event.id, self.request.user.username
            )
        )
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('studioadmin:ticketed_events')


class TicketedEventBookingsListView(
    LoginRequiredMixin, StaffUserMixin, TemplateView
):

    template_name = 'studioadmin/ticketed_event_bookings_admin_list.html'

    def dispatch(self, request, *args, **kwargs):

        self.ticketed_event = get_object_or_404(
            TicketedEvent, slug=kwargs['slug']
        )
        return super(
            TicketedEventBookingsListView, self
        ).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(
            TicketedEventBookingsListView, self
        ).get_context_data(**kwargs)

        context['ticketed_event'] = self.ticketed_event
        bookingids = [
            tbk.id for tbk in
            TicketBooking.objects.filter(
                ticketed_event=self.ticketed_event, purchase_confirmed=True,
            )
            if tbk.tickets.exists()
            ]

        if 'show_cancelled' in self.request.POST:
            queryset = TicketBooking.objects.filter(id__in=bookingids)
            context['show_cancelled_ctx'] = True
        else:
            queryset = TicketBooking.objects.filter(
                id__in=bookingids, cancelled=False
            )

        context['ticket_bookings'] = bool(queryset)
        context['ticket_booking_formset'] = TicketBookingInlineFormSet(
            data=self.request.POST if 'formset_submitted'
                                      in self.request.POST else None,
            queryset=queryset,
            instance=self.ticketed_event,
        )
        context['sidenav_selection'] = 'ticketed_events'
        return context

    def get(self, request, *args, **kwargs):
        context = self.get_context_data()
        return TemplateResponse(request, self.template_name, context)

    def post(self, request, *args, **kwargs):

        context = self.get_context_data(**kwargs)

        if "formset_submitted" in request.POST:
            ticket_booking_formset = context['ticket_booking_formset']

            if ticket_booking_formset.is_valid():
                if not ticket_booking_formset.has_changed():
                    messages.info(request, "No changes were made")
                else:
                    for form in ticket_booking_formset:
                        if form.has_changed():
                            if form.changed_data == ['send_confirmation']:
                                messages.info(
                                    request, "'Send confirmation' checked for '{}' "
                                    "but no changes were made; email has not been "
                                    "sent to user.".format(
                                        form.instance.booking_reference)
                                )
                            else:
                                ticket_booking = form.save(commit=False)
                                if 'cancel' in form.changed_data:
                                    action = 'cancelled'
                                    success_msg = 'Ticket Booking ref <strong>{}' \
                                          '</strong> has been cancelled! ' \
                                          'This booking is marked as paid; ' \
                                          'click <a href={}>here</a> to ' \
                                          'confirm payment ' \
                                          'has been refunded'.format(
                                        ticket_booking.booking_reference,
                                        reverse(
                                            'studioadmin:confirm_ticket_booking_refund',
                                            args=[ticket_booking.id]
                                        )
                                    )
                                    ticket_booking.cancelled = True

                                elif 'reopen' in form.changed_data:
                                    num_tickets = ticket_booking.tickets.count()
                                    if num_tickets > self.ticketed_event.tickets_left():
                                        success_msg = ''
                                        messages.error(
                                            request,
                                            "Cannot reopen ticket booking {}; "
                                            "not enough tickets left for "
                                            "event ({} requested, {} left)".format(
                                                ticket_booking.booking_reference,
                                                num_tickets,
                                                self.ticketed_event.tickets_left()
                                            )
                                        )
                                    else:
                                        success_msg = 'Ticket Booking ref <strong>{}' \
                                                   '</strong> has been ' \
                                                   'reopened!'.format(
                                                ticket_booking.booking_reference
                                            )
                                        action = "reopened"
                                        ticket_booking.cancelled = False
                                        ticket_booking.date_booked = timezone.now()
                                        ticket_booking.warning_sent = False

                                        ActivityLog.objects.create(
                                            log='Ticketed Booking ref {} {} by '
                                                'admin user {}'.format(
                                                ticket_booking.booking_reference,
                                                action,
                                                request.user.username
                                            )
                                        )
                                else:
                                    action = "updated"
                                    for field in form.changed_data:
                                        if field != 'send_confirmation':
                                            success_msg = mark_safe(
                                                    "<strong>{}</strong> updated to {} for "
                                                    "<strong>{}</strong>".format(
                                                        field.title().replace("_", " "),
                                                        form.cleaned_data[field],
                                                        ticket_booking))

                                            ActivityLog.objects.create(
                                                log='Ticketed Booking ref {} (user {}, '
                                                    'event {}) updated by admin user '
                                                    '{}: field_changed: {}'.format(
                                                    ticket_booking.booking_reference,
                                                    ticket_booking.user,
                                                    ticket_booking.ticketed_event,
                                                    ticket_booking.user.username,
                                                    field.title().replace("_", " ")
                                                )
                                            )
                                ticket_booking.save()

                                send_conf_msg = ""
                                if 'send_confirmation' in form.changed_data:
                                    send_conf_msg = self._send_confirmation_email(
                                        request, ticket_booking, action
                                    )

                                if success_msg or send_conf_msg:
                                    messages.success(
                                        request,
                                        mark_safe("{}</br>{}".format(
                                            success_msg, send_conf_msg
                                        ))
                                    )

                        for error in form.errors:
                            messages.error(
                                request, mark_safe("{}".format(error))
                            )
                return HttpResponseRedirect(
                    reverse(
                        'studioadmin:ticketed_event_bookings',
                        kwargs={'slug': self.ticketed_event.slug}
                    )
                )

            else:
                messages.error(
                    request,
                    mark_safe(
                        "There were errors in the following fields:\n{}".format(
                            '\n'.join(
                                ["{}".format(error)
                                 for error in ticket_booking_formset.errors]
                            )
                        )
                    )
                )
        return TemplateResponse(request, self.template_name, context)

    def _send_confirmation_email(self, request, ticket_booking, action):
        try:
            # send confirmation email
            host = 'http://{}'.format(request.META.get('HTTP_HOST'))
            # send email to studio
            ctx = {
                  'host': host,
                  'ticketed_event': self.ticketed_event,
                  'action': action,
            }
            send_mail('{} Your ticket booking ref {} for {} has been {}'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,
                ticket_booking.booking_reference,
                self.ticketed_event,
                action
                ),
                get_template(
                    'studioadmin/email/ticket_booking_change_confirmation.txt'
                ).render(ctx),
                settings.DEFAULT_FROM_EMAIL,
                [ticket_booking.user.email],
                html_message=get_template(
                    'studioadmin/email/ticket_booking_change_confirmation.html'
                    ).render(ctx),
                fail_silently=False)
            send_confirmation_msg = "Confirmation email was sent to " \
                                    "user {}.".format(
                ticket_booking.user.username
            )
        except Exception as e:
            # send mail to tech support with Exception
            send_support_email(
                e, __name__, "ticketed_event_booking_list - "
                "send confirmation email"
            )
            send_confirmation_msg = "There was a " \
            "problem sending the confirmation email to " \
            "user {}.  Tech support has been notified.".format(
                ticket_booking.user.username
            )

        return send_confirmation_msg

@login_required
@staff_required
def cancel_ticketed_event_view(request, slug):
    ticketed_event = get_object_or_404(TicketedEvent, slug=slug)

    open_paid_ticket_bookings = [
        booking for booking in ticketed_event.ticket_bookings.all()
        if not booking.cancelled and booking.purchase_confirmed and
        booking.tickets.exists() and booking.paid
        ]

    open_unpaid_ticket_bookings = [
        booking for booking in ticketed_event.ticket_bookings.all()
        if not booking.cancelled and booking.purchase_confirmed and
        booking.tickets.exists()
        and not booking.paid
        ]

    unconfirmed_ticket_bookings = TicketBooking.objects.filter(
        ticketed_event=ticketed_event, purchase_confirmed=False
    )

    if request.method == 'POST':
        if 'confirm' in request.POST:

            host = 'http://{}'.format(request.META.get('HTTP_HOST'))

            for booking in open_paid_ticket_bookings + \
                    open_unpaid_ticket_bookings:
                booking.cancelled = True
                booking.save()

                try:
                    # send notification email to user to all ticket booking,
                    # paid or unpaid
                    ctx = {
                          'host': host,
                          'ticketed_event': ticketed_event,
                          'ticket_booking': booking,
                    }
                    send_mail('{} {} has been cancelled'.format(
                        settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,
                        ticketed_event.name,
                        ),
                        get_template(
                            'studioadmin/email/ticketed_event_cancelled.txt'
                        ).render(ctx),
                        settings.DEFAULT_FROM_EMAIL,
                        [booking.user.email],
                        html_message=get_template(
                            'studioadmin/email/ticketed_event_cancelled.html'
                            ).render(ctx),
                        fail_silently=False)
                except Exception as e:
                    # send mail to tech support with Exception
                    send_support_email(
                        e, __name__, "cancel ticketed event - "
                        "send notification email to user"
                    )
            for booking in unconfirmed_ticket_bookings:
                booking.delete()

            ticketed_event.cancelled = True
            ticketed_event.show_on_site = False
            ticketed_event.payment_open = False
            ticketed_event.save()

            if open_paid_ticket_bookings:
                # email studio with links for confirming refunds for paid only

                try:
                    # send email to studio
                    ctx = {
                          'host': host,
                          'open_paid_ticket_bookings': open_paid_ticket_bookings,
                          'ticketed_event': ticketed_event,
                    }
                    send_mail('{} Refunds due for ticket bookings for '
                              'cancelled event {}'.format(
                        settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,
                        ticketed_event.name,
                        ),
                        get_template(
                            'studioadmin/email/to_studio_ticketed_event_cancelled.txt'
                        ).render(ctx),
                        settings.DEFAULT_FROM_EMAIL,
                        [settings.DEFAULT_STUDIO_EMAIL],
                        html_message=get_template(
                            'studioadmin/email/to_studio_ticketed_event_cancelled.html'
                            ).render(ctx),
                        fail_silently=False)
                except Exception as e:
                    # send mail to tech support with Exception
                    send_support_email(
                        e, __name__, "cancel ticketed event - "
                        "send refund notification email to studio"
                    )

            if open_paid_ticket_bookings and open_unpaid_ticket_bookings:
                booking_cancelled_msg = '{} has been cancelled; open ticket ' \
                                        'booking refs {} have been ' \
                                        'cancelled'.format(
                    ticketed_event,
                    ', '.join(['{}'.format(booking.booking_reference) for
                               booking in open_paid_ticket_bookings]
                    )
                )
                messages.info(
                    request,
                    booking_cancelled_msg + 'and notification emails have '
                                            'been sent.'
                )
            else:
                booking_cancelled_msg = '{} has been cancelled; there were ' \
                                        'no open ticket bookings for this ' \
                                        'event'.format(ticketed_event)
                messages.info(request, booking_cancelled_msg)

            ActivityLog.objects.create(
                log="{} cancelled by admin user {}. {}".format(
                    ticketed_event, request.user.username,
                    booking_cancelled_msg
                )
            )

            return HttpResponseRedirect(reverse('studioadmin:ticketed_events'))

        elif 'cancel' in request.POST:
            return HttpResponseRedirect(reverse('studioadmin:ticketed_events'))

    context = {
        'ticketed_event': ticketed_event,
        'open_paid_ticket_bookings': open_paid_ticket_bookings,
        'open_unpaid_ticket_bookings': open_unpaid_ticket_bookings,
        'already_cancelled': ticketed_event.cancelled
    }

    return TemplateResponse(
        request, 'studioadmin/cancel_ticketed_event.html', context
    )


class ConfirmTicketBookingRefundView(
    LoginRequiredMixin, StaffUserMixin, UpdateView
):

    model = TicketBooking
    context_object_name = "ticket_booking"
    template_name = 'studioadmin/confirm_ticket_booking_refunded.html'
    success_message = "Refund of payment for {}'s ticket booking (ref {}) for " \
                      "{} has been confirmed.  An update email has been sent " \
                      "to {}."
    fields = ('id',)

    def form_valid(self, form):
        ticket_booking = form.save(commit=False)

        if 'confirmed' in self.request.POST:
            ticket_booking.paid = False
            ticket_booking.save()

            messages.success(
                self.request,
                self.success_message.format(ticket_booking.user.username,
                                            ticket_booking.booking_reference,
                                            ticket_booking.ticketed_event,
                                            ticket_booking.user.username)
            )

            ctx = {
                'ticketed_event': ticket_booking.ticketed_event,
                'ticket_booking': ticket_booking,
                'host': 'http://{}'.format(self.request.META.get('HTTP_HOST'))
            }

            send_mail(
                '{} Payment refund confirmed for ticket booking ref {}'.format(
                    settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,
                    ticket_booking.booking_reference
                ),
                get_template(
                    'studioadmin/email/confirm_ticket_booking_refund.txt'
                ).render(ctx),
                settings.DEFAULT_FROM_EMAIL,
                [self.request.user.email],
                html_message=get_template(
                    'studioadmin/email/confirm_ticket_booking_refund.html').render(ctx),
                fail_silently=False)

            ActivityLog.objects.create(
                log='Payment refund for ticket booking ref {} for event {}, '
                    '(user {}) updated by admin user {}'.format(
                    ticket_booking.booking_reference,
                    ticket_booking.ticketed_event, ticket_booking.user.username,
                    self.request.user.username
                )
            )

        if 'cancelled' in self.request.POST:
            messages.info(
                self.request,
                "Cancelled; no changes to payment status for {}'s ticket "
                "booking ref {}".format(
                    ticket_booking.user.username,
                    ticket_booking.booking_reference,
                    )
            )
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('studioadmin:ticketed_events')


@login_required
@staff_required
def print_tickets_list(request):
    '''
    print list of tickets for a specific event
    GET --> form with selectors for event, sort by, show info
    POST sends selected event-slug in querystring
    get slug from querystring
    find all ticket bookings/tickets for that event
    '''

    if request.method == 'POST':

        form = PrintTicketsForm(request.POST)

        if form.is_valid():

            ticketed_event = form.cleaned_data['ticketed_event']

            show_fields = form.cleaned_data.get('show_fields')

            order_field = form.cleaned_data.get(
                'order_field', 'ticket_booking__date_booked'
            )

            ticket_bookings = TicketBooking.objects.filter(
                ticketed_event=ticketed_event,
                purchase_confirmed=True,
                cancelled=False
            )

            ctx = {'form': form, 'sidenav_selection': 'print_tickets_list'}

            if not ticket_bookings:
                messages.info(request, 'There are no open ticket bookings for '
                                       'the event selected')
                return TemplateResponse(
                    request, "studioadmin/print_tickets_form.html", ctx
                )

            if 'print' in request.POST:
                form = PrintTicketsForm(
                    request.POST, ticketed_event_instance=ticketed_event
                )
                form.is_valid()

                tickets = Ticket.objects.filter(
                    ticket_booking__in=ticket_bookings
                ).order_by(order_field)

                context = {
                    'ticketed_event': ticketed_event,
                    'tickets': tickets,
                    'show_fields': show_fields,
                }
                template = 'studioadmin/print_tickets_list.html'
                return TemplateResponse(request, template, context)

            elif 'ticketed_event' in form.changed_data:

                if ticketed_event.extra_ticket_info_label:
                    show_fields += ['show_extra_ticket_info']
                if ticketed_event.extra_ticket_info1_label:
                    show_fields += ['show_extra_ticket_info1']

                data = dict(request.POST)
                data['show_fields'] = show_fields
                data['ticketed_event'] = ticketed_event.id
                data['order_field'] = order_field
                new_form = PrintTicketsForm(
                    data,
                    ticketed_event_instance=ticketed_event
                )
                ctx = {
                    'form': new_form, 'sidenav_selection': 'print_tickets_list'
                }
                return TemplateResponse(
                        request, "studioadmin/print_tickets_form.html", ctx
                    )
        else:

            messages.error(
                request,
                mark_safe('Please correct the following errors: {}'.format(
                    form.errors
                ))
            )
            return TemplateResponse(
                    request, "studioadmin/print_tickets_form.html",
                    {'form': form, 'sidenav_selection': 'print_tickets_list'}
                    )

    form = PrintTicketsForm()

    return TemplateResponse(
        request, "studioadmin/print_tickets_form.html",
        {'form': form, 'sidenav_selection': 'print_tickets_list'}
    )
