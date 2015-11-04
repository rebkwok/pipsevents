import urllib.parse
import ast
import logging

from datetime import datetime, time
from functools import wraps


from django.db.utils import IntegrityError
from django import forms
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User, Permission

from django.contrib import messages
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.template.loader import get_template
from django.template import Context
from django.template.response import TemplateResponse
from django.shortcuts import HttpResponseRedirect, HttpResponse, redirect, \
    render, get_object_or_404
from django.views.generic import CreateView, ListView, UpdateView, DeleteView, \
    TemplateView
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.core.mail import send_mail

from braces.views import LoginRequiredMixin

from booking.models import Event, Booking, Block, BlockType, WaitingListUser, \
    BookingError, TicketBooking, Ticket, TicketedEvent
from booking import utils
from booking.email_helpers import send_support_email, send_waiting_list_email

from timetable.models import Session
from studioadmin.forms import BookingStatusFilter, ConfirmPaymentForm, \
    EventFormSet, \
    EventAdminForm, SimpleBookingRegisterFormSet, StatusFilter, \
    TimetableSessionFormSet, SessionAdminForm, DAY_CHOICES, \
    UploadTimetableForm, EmailUsersForm, ChooseUsersFormSet, UserFilterForm, \
    BlockStatusFilter, UserBookingFormSet, UserBlockFormSet, \
    ActivityLogSearchForm, RegisterDayForm, TicketedEventFormSet, \
    TicketedEventAdminForm, TicketBookingInlineFormSet, PrintTicketsForm

from activitylog.models import ActivityLog


logger = logging.getLogger(__name__)


def staff_required(func):
    def decorator(request, *args, **kwargs):
        if request.user.is_staff:
            return func(request, *args, **kwargs)
        else:
            return HttpResponseRedirect(reverse('booking:permission_denied'))
    return wraps(func)(decorator)


class StaffUserMixin(object):

    def dispatch(self, request, *args, **kwargs):
        if not self.request.user.is_staff:
            return HttpResponseRedirect(reverse('booking:permission_denied'))
        return super(StaffUserMixin, self).dispatch(request, *args, **kwargs)


class ConfirmPaymentView(LoginRequiredMixin, StaffUserMixin, UpdateView):

    model = Booking
    template_name = 'studioadmin/confirm_payment.html'
    success_message = 'Payment status changed to {}. An update email ' \
                      'has been sent to user {}.'
    form_class = ConfirmPaymentForm

    def get_initial(self):
        return {
            'payment_confirmed': self.object.payment_confirmed
        }

    def form_valid(self, form):
        if form.has_changed():
            booking = form.save(commit=False)

            if booking.payment_confirmed and 'payment_confirmed' \
                    in form.changed_data:
                # if user leaves paid unchecked but checks payment confirmed
                # as true, booking should be marked as paid
                booking.paid = True
                booking.date_payment_confirmed = timezone.now()

            if not booking.paid and 'paid' in form.changed_data:
                # if booking is changed to unpaid, reset payment_confirmed to
                # False too
                booking.payment_confirmed = False
            booking.save()

            if booking.paid and booking.payment_confirmed:
                payment_status = 'paid and confirmed'
            elif booking.paid:
                payment_status = "paid - payment not confirmed yet"
            else:
                payment_status = 'not paid'

            messages.success(
                self.request,
                self.success_message.format(payment_status, booking.user.username)
            )

            ctx = Context({
                'event': booking.event,
                'host': 'http://{}'.format(self.request.META.get('HTTP_HOST')),
                'payment_status': payment_status
            })
            try:
                send_mail(
                    '{} Payment status updated for {}'.format(
                        settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, booking.event),
                    get_template(
                        'studioadmin/email/confirm_payment.html').render(ctx),
                    settings.DEFAULT_FROM_EMAIL,
                    [self.request.user.email],
                    html_message=get_template(
                        'studioadmin/email/confirm_payment.html').render(ctx),
                    fail_silently=False)
            except Exception as e:
                logger.error(
                        'EXCEPTION "{}"" while sending email for booking '
                        'id {}'.format(e, booking.id)
                        )

            ActivityLog(log='Payment status for booking id {} for event {}, '
                'user {} has been updated by admin user {}'.format(
                booking.id, booking.event, booking.user.username,
                self.request.user.username
                )
            )
        else:
            messages.info(
                self.request, "No changes made to the payment "
                              "status for {}'s booking for {}.".format(
                    self.object.user.username, self.object.event)
            )

        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('studioadmin:users')


class ConfirmRefundView(LoginRequiredMixin, StaffUserMixin, UpdateView):

    model = Booking
    template_name = 'studioadmin/confirm_refunded.html'
    success_message = "Refund of payment for {}'s booking for {} has been " \
                      "confirmed.  An update email has been sent to {}."
    fields = ('id',)

    def form_valid(self, form):
        booking = form.save(commit=False)

        if 'confirmed' in self.request.POST:
            booking.paid = False
            booking.payment_confirmed = False
            booking.date_payment_confirmed = None
            booking.save()

            messages.success(
                self.request,
                self.success_message.format(booking.user.username,
                                            booking.event,
                                            booking.user.username)
            )

            ctx = Context({
                'event': booking.event,
                'host': 'http://{}'.format(self.request.META.get('HTTP_HOST'))

            })

            send_mail(
                '{} Payment refund confirmed for {}'.format(
                    settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, booking.event),
                get_template('studioadmin/email/confirm_refund.txt').render(ctx),
                settings.DEFAULT_FROM_EMAIL,
                [self.request.user.email],
                html_message=get_template(
                    'studioadmin/email/confirm_refund.html').render(ctx),
                fail_silently=False)

            ActivityLog(
                log='Payment refund for booking id {} for event {}, '
                    'user {} has been updated by admin user {}'.format(
                    booking.id, booking.event, booking.user.username,
                    self.request.user.username
                )
            )

        if 'cancelled' in self.request.POST:
            messages.info(
                self.request,
                "Cancelled; no changes to payment status for {}'s booking "
                "for {}".format(booking.user.username, booking.event)
            )
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('studioadmin:users')


@login_required
@staff_required
def register_view(request, event_slug, status_choice='OPEN', print_view=False):
    event = get_object_or_404(Event, slug=event_slug)

    if request.method == 'POST':

        if request.POST.get("print"):
            print_view = True

        status_choice = request.POST.getlist('status_choice')[0]

        formset = SimpleBookingRegisterFormSet(
            request.POST,
            instance=event,
        )
        if formset.is_valid():
            if not formset.has_changed() and \
                    request.POST.get('formset_submitted'):
                messages.info(request, "No changes were made")
            else:
                for form in formset:
                    booking = form.save(commit=False)
                    if form.has_changed():
                        if booking.block:
                            booking.paid = True
                        booking.save()
                        messages.success(
                            request,
                            "Register updated for user {}".format(
                                booking.user.username
                            )
                        )
                        ActivityLog(
                            log='Booking id {} for event {}, user {} has been '
                                'updated by admin user {}'.format(
                                booking.id, booking.event,
                                booking.user.username,
                                request.user.username
                            )
                        )
                    for error in form.errors:
                        messages.error(request,mark_safe("{}".format(error)))
                formset.save()

            register_url = 'studioadmin:event_register'
            if event.event_type.event_type == 'CL':
                register_url = 'studioadmin:class_register'
            if print_view:
                register_url = register_url + '_print'

            return HttpResponseRedirect(
                reverse(register_url,
                        kwargs={'event_slug': event.slug,
                                'status_choice': status_choice}
                        )
            )
        else:
            messages.error(
                request,
                mark_safe(
                    "There were errors in the following fields:\n{}".format(
                        '\n'.join(
                            ["{}".format(error) for error in formset.errors]
                        )
                    )
                )
            )


    else:
        if status_choice == 'ALL':
            queryset = Booking.objects.all()
        else:
            queryset = Booking.objects.filter(status=status_choice)

        formset = SimpleBookingRegisterFormSet(
            instance=event,
            queryset=queryset
        )

    status_filter = StatusFilter(initial={'status_choice': status_choice})

    if status_choice == 'CANCELLED':
        extra_lines = 0
    elif event.max_participants:
        extra_lines = event.spaces_left()
    elif event.bookings.count() < 15:
        open_bookings = [
            event for event in event.bookings.all() if event.status == 'OPEN'
        ]
        extra_lines = 15 - len(open_bookings)
    else:
        extra_lines = 2

    template = 'studioadmin/register.html'
    if print_view:
        template = 'studioadmin/register_print.html'

    sidenav_selection = 'lessons_register'
    if event.event_type.event_type == 'EV':
        sidenav_selection = 'events_register'

    available_block_type = [
        block_type for block_type in
        BlockType.objects.filter(event_type=event.event_type)
    ]

    return TemplateResponse(
        request, template, {
            'formset': formset, 'event': event, 'status_filter': status_filter,
            'extra_lines': extra_lines, 'print': print_view,
            'status_choice': status_choice,
            'available_block_type': True if available_block_type else False,
            'sidenav_selection': sidenav_selection
        }
    )


@login_required
@staff_required
def register_print_day(request):
    '''
    link to print all registers for a specific day GET --> form with date selector
    POST sends selected date in querystring
    get date from querystring
    find all events for that date
    for each event, create formset as above; only for open bookings
    in template, iterate over events and create print version of register for each
    '''

    if request.method == 'POST':
        form = RegisterDayForm(request.POST)

        if form.is_valid():
            register_date = form.cleaned_data['register_date']
            register_format = form.cleaned_data['register_format']
            exclude_ext_instructors = form.cleaned_data['exclude_ext_instructor']

            events = Event.objects.filter(
                date__gt=datetime.combine(
                    register_date, time(hour=0, minute=0)
                ).replace(tzinfo=timezone.utc),
                date__lt=datetime.combine(
                    register_date, time(hour=23, minute=59)
                ).replace(tzinfo=timezone.utc),
            )

            new_form = RegisterDayForm(
                initial={'register_date': register_date,
                         'exclude_ext_instructor': exclude_ext_instructors,
                         'register_format': register_format},
                events=events
            )
            ctx = {'form': new_form, 'sidenav_selection': 'register_day'}

            if not events:
                messages.info(request, 'There are no classes/workshops/events on the date selected')
                return TemplateResponse(
                    request, "studioadmin/register_day_form.html", ctx
                )

            if 'print' in request.POST:

                if 'select_events' in request.POST:
                    event_ids = form.cleaned_data['select_events']
                    events = Event.objects.filter(
                        id__in=event_ids
                    )
                else:
                    messages.info(request, 'Please select at least one register to print')
                    form = RegisterDayForm(
                        initial={'register_date': register_date,
                                 'exclude_ext_instructor': exclude_ext_instructors,
                                 'register_format': register_format,
                                 'select_events': []},
                        events=events
                    )
                    return TemplateResponse(
                        request, "studioadmin/register_day_form.html",
                        {'form': form, 'sidenav_selection': 'register_day'}
                    )

                eventlist = []
                for event in events:
                    bookings = [
                        booking for booking in Booking.objects.filter(event=event, status='OPEN')
                        ]

                    bookinglist = []
                    for i, booking in enumerate(bookings):
                        available_block = [
                            block for block in
                            Block.objects.filter(user=booking.user) if
                            block.active_block() and
                            block.block_type.event_type == event.event_type
                        ]
                        available_block = booking.block or (
                            available_block[0] if available_block else None
                        )
                        booking_ctx = {'booking': booking, 'index': i+1, 'available_block': available_block}
                        bookinglist.append(booking_ctx)

                    if event.max_participants:
                        extra_lines = event.spaces_left()
                    elif event.bookings.count() < 15:
                        open_bookings = [
                            event for event in event.bookings.all() if event.status == 'OPEN'
                        ]
                        extra_lines = 15 - len(open_bookings)
                    else:
                        extra_lines = 2

                    available_block_type = [
                        block_type for block_type in
                        BlockType.objects.filter(event_type=event.event_type)
                    ]

                    event_ctx = {
                        'event': event,
                        'bookings': bookinglist,
                        'available_block_type': available_block_type,
                        'extra_lines': extra_lines,
                    }
                    eventlist.append(event_ctx)

                context = {
                    'date': register_date, 'events': eventlist,
                    'sidenav_selection': 'register_day',
                    'register_format': register_format
                }
                template = 'studioadmin/print_multiple_registers.html'
                return TemplateResponse(request, template, context)

            else:
                return TemplateResponse(
                    request, "studioadmin/register_day_form.html", ctx
                )

        else:

            messages.error(
                request,
                mark_safe('Please correct the following errors: {}'.format(
                    form.errors
                ))
            )
            return TemplateResponse(
                    request, "studioadmin/register_day_form.html",
                    {'form': form, 'sidenav_selection': 'register_day'}
                    )

    events = Event.objects.filter(
                date__gt=datetime.now().replace(hour=0, minute=0, tzinfo=timezone.utc),
                date__lt=datetime.now().replace(hour=23, minute=59, tzinfo=timezone.utc),
            )
    form = RegisterDayForm(events=events, initial={'exclude_ext_instructor': True})

    return TemplateResponse(
        request, "studioadmin/register_day_form.html",
        {'form': form, 'sidenav_selection': 'register_day'}
    )


@login_required
@staff_required
def event_admin_list(request, ev_type):


    if ev_type == 'events':
        ev_type_text = 'event'
        queryset = Event.objects.filter(
            event_type__event_type='EV',
            date__gte=timezone.now()
        ).order_by('date')
    else:
        ev_type_text = 'class'
        queryset = Event.objects.filter(
            date__gte=timezone.now()
        ).exclude(event_type__event_type='EV').order_by('date')

    events = True if queryset.count() > 0 else False
    show_past = False

    if request.method == 'POST':
        if "past" in request.POST:

            if ev_type == 'events':
                queryset = Event.objects.filter(
                    event_type__event_type='EV',
                    date__lte=timezone.now()
                ).order_by('date')
            else:
                queryset = Event.objects.filter(
                    date__lte=timezone.now()
                ).exclude(event_type__event_type='EV').order_by('date')
            events = True if queryset.count() > 0 else False
            show_past = True
            eventformset = EventFormSet(queryset=queryset)
        elif "upcoming" in request.POST:
            queryset = queryset
            show_past = False
            eventformset = EventFormSet(queryset=queryset)
        else:
            eventformset = EventFormSet(request.POST)

            if eventformset.is_valid():
                if not eventformset.has_changed():
                    messages.info(request, "No changes were made")
                else:
                    for form in eventformset:
                        if form.has_changed():
                            if 'DELETE' in form.changed_data:
                                messages.success(
                                    request, mark_safe(
                                        '{} <strong>{}</strong> has been deleted!'.format(
                                            ev_type_text.title(), form.instance,
                                        )
                                    )
                                )
                                ActivityLog.objects.create(
                                    log='{} {} (id {}) deleted by admin user {}'.format(
                                        ev_type_text.title(), form.instance,
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
                                        log='{} {} (id {}) updated by admin user {}: field_changed: {}'.format(
                                            ev_type_text.title(),
                                            form.instance, form.instance.id,
                                            request.user.username, field.title().replace("_", " ")
                                        )
                                    )

                            form.save()

                        for error in form.errors:
                            messages.error(request, mark_safe("{}".format(error)))
                    eventformset.save()
                return HttpResponseRedirect(
                    reverse('studioadmin:{}'.format(ev_type),)
                )
            else:
                messages.error(
                    request,
                    mark_safe(
                        "There were errors in the following fields:\n{}".format(
                            '\n'.join(
                                ["{}".format(error) for error in eventformset.errors]
                            )
                        )
                    )
                )

    else:
        eventformset = EventFormSet(queryset=queryset)

    return TemplateResponse(
        request, 'studioadmin/admin_events.html', {
            'eventformset': eventformset,
            'type': ev_type,
            'events': events,
            'sidenav_selection': ev_type,
            'show_past': show_past,
            }
    )


class EventRegisterListView(LoginRequiredMixin, StaffUserMixin, ListView):

    model = Event
    template_name = 'studioadmin/events_register_list.html'
    context_object_name = 'events'

    def get_queryset(self):
        if self.kwargs["ev_type"] == 'events':
            queryset = Event.objects.filter(
                event_type__event_type='EV',
                date__gte=timezone.now()
            ).order_by('date')
        else:
            queryset = Event.objects.filter(
                date__gte=timezone.now()
            ).exclude(event_type__event_type='EV').order_by('date')
        return queryset

    def get_context_data(self, **kwargs):
        context = super(EventRegisterListView, self).get_context_data(**kwargs)
        context['type'] = self.kwargs['ev_type']
        context['sidenav_selection'] = '{}_register'.format(
            self.kwargs['ev_type'])
        return context


class EventAdminUpdateView(LoginRequiredMixin, StaffUserMixin, UpdateView):

    form_class = EventAdminForm
    model = Event
    template_name = 'studioadmin/event_create_update.html'
    context_object_name = 'event'

    def get_form_kwargs(self, **kwargs):
        form_kwargs = super(EventAdminUpdateView, self).get_form_kwargs(**kwargs)
        form_kwargs['ev_type'] = 'EV' if self.kwargs["ev_type"] == 'event' \
            else 'CL'
        return form_kwargs

    def get_object(self):
        queryset = Event.objects.all()
        return get_object_or_404(queryset, slug=self.kwargs['slug'])

    def get_context_data(self, **kwargs):
        context = super(EventAdminUpdateView, self).get_context_data(**kwargs)
        context['type'] = self.kwargs["ev_type"]
        if self.kwargs["ev_type"] == "lesson":
            context['type'] = "class"
        context['sidenav_selection'] = self.kwargs['ev_type'] + 's'

        return context

    def form_valid(self, form):
        if form.has_changed():
            event = form.save()
            msg_ev_type = 'Event' if self.kwargs["ev_type"] == 'event' else 'Class'
            msg = '<strong>{} {}</strong> has been updated!'.format(
                msg_ev_type, event.name
            )
            ActivityLog.objects.create(
                log='{} {} (id {}) updated by admin user {}'.format(
                    msg_ev_type, event, event.id,
                    self.request.user.username
                )
            )
        else:
            msg = 'No changes made'
        messages.success(self.request, mark_safe(msg))
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('studioadmin:{}'.format(self.kwargs["ev_type"] + 's'))


class EventAdminCreateView(LoginRequiredMixin, StaffUserMixin, CreateView):

    form_class = EventAdminForm
    model = Event
    template_name = 'studioadmin/event_create_update.html'
    context_object_name = 'event'

    def get_form_kwargs(self, **kwargs):
        form_kwargs = super(EventAdminCreateView, self).get_form_kwargs(**kwargs)
        form_kwargs['ev_type'] = 'EV' if self.kwargs["ev_type"] == 'event' \
            else 'CL'
        return form_kwargs

    def get_context_data(self, **kwargs):
        context = super(EventAdminCreateView, self).get_context_data(**kwargs)
        context['type'] = self.kwargs["ev_type"]
        if self.kwargs["ev_type"] == "lesson":
            context['type'] = "class"
        context['sidenav_selection'] = 'add_{}'.format(self.kwargs['ev_type'])
        return context

    def form_valid(self, form):
        event = form.save()
        msg_ev_type = 'Event' if self.kwargs["ev_type"] == 'event' else 'Class'
        messages.success(self.request, mark_safe('<strong>{} {}</strong> has been '
                                    'created!'.format(msg_ev_type, event.name)))
        ActivityLog.objects.create(
            log='{} {} (id {}) created by admin user {}'.format(
                msg_ev_type, event, event.id, self.request.user.username
            )
        )
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('studioadmin:{}'.format(self.kwargs["ev_type"] + 's'))


@login_required
@staff_required
def timetable_admin_list(request):

    if request.method == 'POST':
        sessionformset = TimetableSessionFormSet(request.POST)

        if sessionformset.is_valid():
            if not sessionformset.has_changed():
                messages.info(request, "No changes were made")
            else:
                for form in sessionformset:
                    if form.has_changed():
                        if 'DELETE' in form.changed_data:
                            messages.success(
                                request, mark_safe(
                                    'Session <strong>{} {} {}</strong> has been deleted!'.format(
                                    form.instance.name,
                                    DAY_CHOICES[form.instance.day],
                                    form.instance.time.strftime('%H:%M')
                                ))
                            )
                            ActivityLog.objects.create(
                                log='Session {} (id {}) deleted by admin '
                                    'user {}'.format(
                                    form.instance, form.instance.id,
                                    request.user.username
                                )
                            )
                        else:
                            for field in form.changed_data:
                                messages.success(
                                    request, mark_safe(
                                        "<strong>{}</strong> updated for "
                                        "<strong>{}</strong>".format(
                                            field.title().replace("_", " "),
                                            form.instance
                                            )
                                    )
                                )
                                ActivityLog.objects.create(
                                    log='Session {} (id {}) updated by admin '
                                        'user {}'.format(
                                        form.instance, form.instance.id,
                                        request.user.username
                                    )
                                )
                        form.save()

                    for error in form.errors:
                        messages.error(request, mark_safe("{}".format(error)))
                sessionformset.save()
            return HttpResponseRedirect(
                reverse('studioadmin:timetable')
            )
        else:
            messages.error(
                request,
                mark_safe(
                    "There were errors in the following fields:\n{}".format(
                        '\n'.join(
                            ["{}".format(error) for error in sessionformset.errors]
                        )
                    )
                )
            )

    else:
        sessionformset = TimetableSessionFormSet(
            queryset=Session.objects.all().order_by('day', 'time')
        )

    return render(
        request, 'studioadmin/timetable_list.html', {
            'sessionformset': sessionformset,
            'sidenav_selection': 'timetable'
            }
    )


class TimetableSessionUpdateView(
    LoginRequiredMixin, StaffUserMixin, UpdateView
):

    form_class = SessionAdminForm
    model = Session
    template_name = 'studioadmin/session_create_update.html'
    context_object_name = 'session'

    def get_object(self):
        queryset = Session.objects.all()
        return get_object_or_404(queryset, pk=self.kwargs['pk'])

    def get_context_data(self, **kwargs):
        context = super(
            TimetableSessionUpdateView, self
        ).get_context_data(**kwargs)
        context['sidenav_selection'] = 'timetable'
        context['session_day'] = DAY_CHOICES[self.object.day]

        return context

    def form_valid(self, form):
        if form.has_changed():
            session = form.save()
            msg = 'Session <strong>{} {} {}</strong> has been updated!'.format(
                session.name, DAY_CHOICES[session.day],
                session.time.strftime('%H:%M')
            )
            ActivityLog.objects.create(
                log='Session {} (id {}) updated by admin user {}'.format(
                    session, session.id, self.request.user.username
                )
            )
        else:
            msg = 'No changes made'
        messages.success(self.request, mark_safe(msg))
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('studioadmin:timetable')


class TimetableSessionCreateView(
    LoginRequiredMixin, StaffUserMixin, CreateView
):

    form_class = SessionAdminForm
    model = Session
    template_name = 'studioadmin/session_create_update.html'
    context_object_name = 'session'

    def get_context_data(self, **kwargs):
        context = super(
            TimetableSessionCreateView, self
        ).get_context_data(**kwargs)
        context['sidenav_selection'] = 'add_session'
        return context

    def form_valid(self, form):
        session = form.save()
        msg = 'Session <strong>{} {} {}</strong> has been created!'.format(
            session.name, DAY_CHOICES[session.day],
            session.time.strftime('%H:%M')
        )
        ActivityLog.objects.create(
            log='Session {} (id {}) created by admin user {}'.format(
                session, session.id, self.request.user.username
            )
        )
        messages.success(self.request, mark_safe(msg))
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('studioadmin:timetable')


@login_required
@staff_required
def upload_timetable_view(request,
                          template_name="studioadmin/upload_timetable_form.html"):

    if request.method == 'POST':
        form = UploadTimetableForm(request.POST)
        if form.is_valid():
            start_date = form.cleaned_data['start_date']
            end_date = form.cleaned_data['end_date']
            session_ids = form.cleaned_data['sessions']

            created_classes, existing_classes = \
                utils.upload_timetable(
                    start_date, end_date, session_ids, request.user
                )
            context = {'start_date': start_date,
                       'end_date': end_date,
                       'created_classes': created_classes,
                       'existing_classes': existing_classes,
                       'sidenav_selection': 'upload_timetable'}
            return render(
                request, 'studioadmin/upload_timetable_confirmation.html',
                context
            )
    else:
        form = UploadTimetableForm()
    return render(request, template_name,
                  {'form': form, 'sidenav_selection': 'upload_timetable'})


class UserListView(LoginRequiredMixin, StaffUserMixin, ListView):

    model = User
    template_name = 'studioadmin/user_list.html'
    context_object_name = 'users'
    queryset = User.objects.all().order_by('first_name')

    def get(self, request, *args, **kwargs):
        if 'change_user' in self.request.GET:
            change_user_id = self.request.GET.getlist('change_user')[0]
            user_to_change = User.objects.get(id=change_user_id)
            is_regular_student = user_to_change.has_perm('booking.is_regular_student')
            perm = Permission.objects.get(codename='is_regular_student')
            if is_regular_student:
                user_to_change.user_permissions.remove(perm)
                if user_to_change.is_superuser:
                    messages.error(
                        request,
                        "{} {} ({}) is a superuser; you cannot remove "
                        "permissions".format(
                            user_to_change.first_name,
                            user_to_change.last_name,
                            user_to_change.username
                        )
                    )
                else:
                    messages.success(
                        request,
                        "'Regular student' status has been removed for "
                        "{} {} ({})".format(
                            user_to_change.first_name,
                            user_to_change.last_name,
                            user_to_change.username
                        )
                    )
                    ActivityLog.objects.create(
                        log="'Regular student' status has been removed for "
                        "{} {} ({}) by admin user {}".format(
                            user_to_change.first_name,
                            user_to_change.last_name,
                            user_to_change.username,
                            request.user.username
                        )
                    )

            else:
                user_to_change.user_permissions.add(perm)
                messages.success(
                    request,
                    "{} {} ({}) has been given 'regular student' "
                    "status".format(
                        user_to_change.first_name,
                        user_to_change.last_name,
                        user_to_change.username
                    )
                )
                ActivityLog.objects.create(
                    log="{} {} ({}) has been given 'regular student' "
                    "status by admin user {}".format(
                        user_to_change.first_name,
                            user_to_change.last_name,
                            user_to_change.username,
                            request.user.username
                        )
                )
            user_to_change.save()
        return super(UserListView, self).get(request, *args, **kwargs)

    def get_context_data(self):
        context = super(UserListView, self).get_context_data()
        context['sidenav_selection'] = 'users'
        return context


class BlockListView(LoginRequiredMixin, StaffUserMixin, ListView):

    model = Block
    template_name = 'studioadmin/block_list.html'
    context_object_name = 'blocks'
    default_sort_params = ('block_type', 'asc')

    def get_queryset(self):
        block_status = self.request.GET.get('block_status', 'current')
        all_blocks = Block.objects.all()
        if block_status == 'all':
            return all_blocks
        elif block_status == 'current':
            current = (block.id for block in all_blocks
                      if not block.expired and not block.full)
            return Block.objects.filter(id__in=current)
        elif block_status == 'active':
            active = (block.id for block in all_blocks if block.active_block())
            return Block.objects.filter(id__in=active)
        elif block_status == 'unpaid':
            unpaid = (block.id for block in all_blocks
                      if not block.expired and not block.paid
                      and not block.full)
            return Block.objects.filter(id__in=unpaid)
        elif block_status == 'expired':
            expired = (block.id for block in all_blocks if block.expired or block.full)
            return Block.objects.filter(id__in=expired)

    def get_context_data(self):
        context = super(BlockListView, self).get_context_data()
        context['sidenav_selection'] = 'blocks'

        block_status = self.request.GET.get('block_status', 'current')
        form = BlockStatusFilter(initial={'block_status': block_status})
        context['form'] = form
        context['block_status'] = block_status

        return context


@login_required
@staff_required
def choose_users_to_email(request,
                          template_name='studioadmin/choose_users_form.html'):

    initial_userfilterdata={'events': [''], 'lessons': ['']}

    if 'filter' in request.POST:
        event_ids = request.POST.getlist('filter-events')
        lesson_ids = request.POST.getlist('filter-lessons')

        if event_ids == ['']:
            if request.session.get('events'):
                del request.session['events']
            event_ids = []
        else:
            request.session['events'] = event_ids
            initial_userfilterdata['events'] = event_ids

        if lesson_ids == ['']:
            if request.session.get('lessons'):
                del request.session['lessons']
            lesson_ids = []
        else:
            request.session['lessons'] = lesson_ids
            initial_userfilterdata['lessons'] = lesson_ids

        if not event_ids and not lesson_ids:
            usersformset = ChooseUsersFormSet(
                queryset=User.objects.all().order_by('username'))
        else:
            event_and_lesson_ids = event_ids + lesson_ids
            bookings = Booking.objects.filter(event__id__in=event_and_lesson_ids)
            user_ids = set([booking.user.id for booking in bookings
                            if booking.status == 'OPEN'])
            usersformset = ChooseUsersFormSet(
                queryset=User.objects.filter(id__in=user_ids).order_by('username')
            )

    elif request.method == 'POST':
        usersformset = ChooseUsersFormSet(request.POST)

        if usersformset.is_valid():

            event_ids = request.session.get('events', [])
            lesson_ids = request.session.get('lessons', [])
            users_to_email = []

            for form in usersformset:
                # check checkbox value to determine if that user is to be
                # emailed; add user_id to list
                if form.is_valid():
                    if form.cleaned_data.get('email_user'):
                        users_to_email.append(form.instance.id)
                else:
                    for error in form.errors:
                        messages.error(request, mark_safe("{}".format(error)))

            request.session['users_to_email'] = users_to_email

            return HttpResponseRedirect(url_with_querystring(
                reverse('studioadmin:email_users_view'), events=event_ids, lessons=lesson_ids)
            )

        else:
            messages.error(
                request,
                mark_safe(
                    "There were errors in the following fields:\n{}".format(
                        '\n'.join(
                            ["{}".format(error) for error in usersformset.errors]
                        )
                    )
                )
            )

    else:
        usersformset = ChooseUsersFormSet(
            queryset=User.objects.all().order_by('username'),
        )

    userfilterform = UserFilterForm(prefix='filter', initial=initial_userfilterdata)

    return TemplateResponse(
        request, template_name, {
            'usersformset': usersformset,
            'userfilterform': userfilterform,
            'sidenav_selection': 'email_users',
            }
    )


def url_with_querystring(path, **kwargs):
    return path + '?' + urllib.parse.urlencode(kwargs)


@login_required
@staff_required
def email_users_view(request,
                     template_name='studioadmin/email_users_form.html'):

        users_to_email = User.objects.filter(id__in=request.session['users_to_email'])

        if request.method == 'POST':

            form = EmailUsersForm(request.POST)

            if form.is_valid():
                subject = '{} {}'.format(
                    settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,
                    form.cleaned_data['subject'])
                from_address = form.cleaned_data['from_address']
                message = form.cleaned_data['message']
                cc = form.cleaned_data['cc']

                # do this per email address so recipients are not visible to
                # each
                email_addresses = [user.email for user in users_to_email]
                if cc:
                    email_addresses.append(from_address)
                for email_address in email_addresses:
                    try:
                        send_mail(subject, message, from_address,
                              [email_address],
                              html_message=get_template(
                                  'studioadmin/email/email_users.html').render(
                                  Context({
                                      'subject': subject,
                                      'message': message})
                              ),
                              fail_silently=False)
                    except Exception as e:
                        # send mail to tech support with Exception
                        send_support_email(e, __name__, "Bulk Email to students")
                        ActivityLog.objects.create(log="Possible error with "
                            "sending bulk email; notification sent to tech support")
                ActivityLog.objects.create(
                    log='Bulk email with subject "{}" sent to users {} by '
                        'admin user {}'.format(
                        subject, email_addresses, request.user.username
                    )
                )

                return render(request,
                    'studioadmin/email_users_confirmation.html')

            else:
                event_ids = request.session.get('events')
                lesson_ids = request.session.get('lessons')
                events = Event.objects.filter(id__in=event_ids)
                lessons = Event.objects.filter(id__in=lesson_ids)
                totaleventids = event_ids + lesson_ids
                totalevents = Event.objects.filter(id__in=totaleventids)
                messages.error(request, mark_safe("Please correct errors in form: {}".format(form.errors)))
                form = EmailUsersForm(initial={'subject': "; ".join((str(event) for event in totalevents))})

        else:
            event_ids = ast.literal_eval(request.GET.get('events'))
            events = Event.objects.filter(id__in=event_ids)
            lesson_ids = ast.literal_eval(request.GET.get('lessons'))
            lessons = Event.objects.filter(id__in=lesson_ids)
            totaleventids = event_ids + lesson_ids
            totalevents = Event.objects.filter(id__in=totaleventids)
            form = EmailUsersForm(initial={'subject': "; ".join((str(event) for event in totalevents))})

        return TemplateResponse(
            request, template_name, {
                'form': form,
                'users_to_email': users_to_email,
                'sidenav_selection': 'email_users',
                'events': events,
                'lessons': lessons
            }
        )


@login_required
@staff_required
def user_bookings_view(request, user_id, booking_status='future'):
    user = get_object_or_404(User, id=user_id)

    if request.method == 'POST':
        booking_status = request.POST.getlist('booking_status')[0]
        userbookingformset = UserBookingFormSet(
            request.POST.copy(), instance=user, user=user,
        )
        if userbookingformset.is_valid():
            if not userbookingformset.has_changed() and \
                    request.POST.get('formset_submitted'):
                messages.info(request, "No changes were made")
            else:
                for form in userbookingformset:
                    if form.is_valid():
                        if form.has_changed():
                            if form.changed_data == ['send_confirmation']:
                                messages.info(
                                    request, "'Send confirmation' checked for '{}' "
                                    "but no changes were made; email has not been "
                                    "sent to user.".format(form.instance.event))
                            else:
                                extra_msgs = [] # these will be displayed as a list in the email to the user

                                booking = form.save(commit=False)
                                event_was_full = booking.event.spaces_left() == 0
                                action = 'updated' if form.instance.id else 'created'
                                if 'status' in form.changed_data and action == 'updated':
                                    if booking.status == 'CANCELLED':
                                        booking.paid = False
                                        booking.payment_confirmed = False
                                        booking.block = None
                                        action = 'cancelled'
                                    elif booking.status == 'OPEN':
                                        action = 'reopened'

                                    extra_msgs.append("Booking status changed "
                                                      "to {}".format(action)
                                                      )

                                if booking.block:
                                    booking.paid = True
                                    booking.payment_confirmed = True
                                elif 'block' in form.changed_data:
                                    booking.block = None
                                    booking.paid = False
                                    booking.payment_confirmed = False

                                if 'deposit_paid' in form.changed_data:
                                    if booking.deposit_paid:
                                        extra_msgs.append(
                                            "Booking payment status changed to "
                                            "'deposit paid'"
                                        )

                                if 'paid' in form.changed_data:
                                    if booking.paid:
                                        # assume that if booking is being done via
                                        # studioadmin, marking paid also means payment
                                        # is confirmed
                                        booking.payment_confirmed = True
                                        extra_msgs.append(
                                            "Booking payment status changed to "
                                            "'fully paid and confirmed'"
                                        )
                                    else:
                                        booking.payment_confirmed = False

                                try:
                                    booking.save()
                                except BookingError:
                                    messages.error(request,
                                        mark_safe('<span class="cancel-warning">'
                                        'ERROR:</span> Booking cannot'
                                        ' be made for fully booked event '
                                        '{}'.format(booking.event))
                                    )
                                else:
                                    set_as_free = 'free_class' in \
                                                  form.changed_data and \
                                                  booking.free_class
                                    if 'send_confirmation' in form.changed_data:
                                        try:
                                            # send confirmation email
                                            host = 'http://{}'.format(request.META.get('HTTP_HOST'))
                                            # send email to studio
                                            ctx = Context({
                                                  'host': host,
                                                  'event': booking.event,
                                                  'user': booking.user,
                                                  'action': action,
                                                  'set_as_free': set_as_free,
                                                  'extra_msgs': extra_msgs
                                            })
                                            send_mail('{} Your booking for {} has been {}'.format(
                                                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, booking.event, action
                                                ),
                                                get_template(
                                                    'studioadmin/email/booking_change_confirmation.txt'
                                                ).render(ctx),
                                                settings.DEFAULT_FROM_EMAIL,
                                                [booking.user.email],
                                                html_message=get_template(
                                                    'studioadmin/email/booking_change_confirmation.html'
                                                    ).render(ctx),
                                                fail_silently=False)
                                            send_confirmation_msg = "and confirmation " \
                                            "email sent to user"
                                        except Exception as e:
                                            # send mail to tech support with Exception
                                            send_support_email(
                                                e, __name__, "user_booking_list - "
                                                "send confirmation email"
                                            )
                                            send_confirmation_msg = ". There was a " \
                                            "problem sending the confirmation email to the " \
                                            "user.  Tech support has been notified."
                                    else:
                                        send_confirmation_msg = ""

                                    messages.success(
                                        request,
                                        'Booking for {} has been {} {}'.format(
                                            booking.event, action, send_confirmation_msg
                                        )
                                    )
                                    ActivityLog.objects.create(
                                        log='Booking id {} (user {}) for "{}" {} '
                                                'by admin user {} {}'.format(
                                            booking.id, booking.user.username, booking.event,
                                            action, request.user.username,
                                            "and marked as free class" if set_as_free else ""
                                        )
                                    )

                                    if action == 'reopened':
                                        messages.info(
                                            request, mark_safe(
                                                'Note: this booking was previously '
                                                'cancelled and has now been reopened. '
                                                '<span class="cancel-warning">Payment '
                                                'status has not been automatically '
                                                'updated. Please review the booking '
                                                'and update if paid '
                                                'and/or block used.</span>'
                                            )
                                        )
                                    elif action == 'cancelled':
                                        messages.info(
                                            request, 'Note: this booking has been '
                                            'cancelled.  The booking has automatically '
                                            'been marked as unpaid (refunded) and, if '
                                            'applicable, the block used has been updated.')

                                        if event_was_full:
                                            waiting_list_users = WaitingListUser.objects.filter(
                                                event=booking.event
                                            )
                                            if waiting_list_users:
                                                try:
                                                    send_waiting_list_email(
                                                        booking.event,
                                                        [wluser.user for \
                                                            wluser in waiting_list_users],
                                                        host='http://{}'.format(
                                                            request.META.get('HTTP_HOST')
                                                        )
                                                    )
                                                    ActivityLog.objects.create(
                                                        log='Waiting list email sent to '
                                                        'user(s) {} for event {}'.format(
                                                            ', '.join(
                                                                [wluser.user.username \
                                                                    for wluser in \
                                                                    waiting_list_users]
                                                            ),
                                                            booking.event
                                                        )
                                                    )
                                                except Exception as e:
                                                    # send mail to tech support with Exception
                                                    send_support_email(
                                                        e, __name__, "Automatic cancel job - waiting list email"
                                                    )

                                    if action == 'created' or action == 'reopened':
                                        try:
                                            waiting_list_user = WaitingListUser.objects.get(
                                                user=booking.user, event=booking.event
                                            )
                                            waiting_list_user.delete()
                                            ActivityLog.objects.create(
                                                log='User {} has been removed from the '
                                                'waiting list for {}'.format(
                                                    booking.user.username,
                                                    booking.event
                                                )
                                            )
                                        except WaitingListUser.DoesNotExist:
                                            pass
                    else:
                        for error in form.errors:
                            messages.error(request, mark_safe("{}".format(error)))

                    userbookingformset.save(commit=False)

            return HttpResponseRedirect(
                reverse(
                    'studioadmin:user_bookings_list',
                    kwargs={
                        'user_id': user.id,
                        'booking_status': booking_status
                    }
                )
            )
        else:
            messages.error(
                request,
                mark_safe(
                    "There were errors in the following fields:\n{}".format(
                        '\n'.join(
                            ["{}".format(error) for error in userbookingformset.errors]
                        )
                    )
                )
            )
    else:
        all_bookings = Booking.objects.filter(user=user)

        if booking_status == 'past':
            queryset = all_bookings.filter(
                event__date__lt=timezone.now()
            ).order_by('event__date')
            userbookingformset = UserBookingFormSet(
                queryset=queryset, instance=user, user=user,
            )
        else:
            # 'future' by default
            queryset = all_bookings.filter(
                event__date__gte=timezone.now()
            ).order_by('event__date')
            userbookingformset = UserBookingFormSet(
                queryset=queryset, instance=user, user=user,
            )

        userbookingformset = UserBookingFormSet(
            instance=user,
            queryset=queryset,
            user=user
        )

    booking_status_filter = BookingStatusFilter(
        initial={'booking_status': booking_status}
    )

    template = 'studioadmin/user_booking_list.html'
    return TemplateResponse(
        request, template, {
            'userbookingformset': userbookingformset, 'user': user,
            'sidenav_selection': 'users',
            'booking_status_filter': booking_status_filter,
            'booking_status': booking_status
        }
    )


@login_required
@staff_required
def user_blocks_view(request, user_id):

    user = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        userblockformset = UserBlockFormSet(
            request.POST,
            instance=user,
            user=user
        )
        if userblockformset.is_valid():
            if not userblockformset.has_changed():
                messages.info(request, "No changes were made")
            else:
                for form in userblockformset:
                    if form.has_changed():

                        block = form.save(commit=False)

                        if 'DELETE' in form.changed_data:
                            messages.success(
                                request, mark_safe(
                                    'Block <strong>{}</strong> has been '
                                    'deleted!  Any bookings made with this '
                                    'block have been changed to unpaid.  '
                                    'Please inform user {} ({})'.format(
                                        block, block.user.username,
                                        block.user.email
                                    )
                                )
                            )
                            ActivityLog.objects.create(
                                log='Block {} (id {}) deleted by admin user {}'.format(
                                form.instance, form.instance.id, request.user.username)
                            )
                            block.delete()
                        else:
                            new = False if form.instance.id else True
                            msg = 'created' if new else 'updated'

                            messages.success(
                                request,
                                'Block for {} has been {}'.format(
                                    block.block_type.event_type, msg
                                )
                            )
                            block.save()
                            ActivityLog.objects.create(
                                log='Block id {} ({}), user {}, has been {}'
                                        ' by admin user {}'.format(
                                    block.id, block.block_type,
                                    block.user.username, msg,
                                    request.user.username
                                )
                            )
                    for error in form.errors:
                        messages.error(request, mark_safe("{}".format(error)))
                userblockformset.save(commit=False)

            return HttpResponseRedirect(
                reverse('studioadmin:user_blocks_list',
                        kwargs={'user_id': user.id}
                        )
            )
        else:
            messages.error(
                request,
                mark_safe(
                    "There were errors in the following fields:\n{}".format(
                        '\n'.join(
                            ["{}".format(error) for error in userblockformset.errors]
                        )
                    )
                )
            )
    else:
        queryset = Block.objects.filter(
            user=user).order_by('start_date')
        userblockformset = UserBlockFormSet(
            instance=user,
            queryset=queryset,
            user=user
        )

    template = 'studioadmin/user_block_list.html'
    return TemplateResponse(
        request, template, {
            'userblockformset': userblockformset, 'user': user,
            'sidenav_selection': 'users'
        }
    )


class ActivityLogListView(LoginRequiredMixin, StaffUserMixin, ListView):

    model = ActivityLog
    template_name = 'studioadmin/activitylog.html'
    context_object_name = 'logs'
    paginate_by = 20

    def get_queryset(self):

        empty_text = [
            'email_warnings job run; no unpaid booking warnings to send',
            'cancel_unpaid_bookings job run; no bookings to cancel',
            'deleted_unconfirmed_bookings job run; no bookings to cancel',
            'email_ticket_booking_warnings job run; no unpaid booking warnings to send',
            'cancel_unpaid_ticket_bookings job run; no bookings to cancel'
        ]
        queryset = ActivityLog.objects.exclude(
            log__in=empty_text
        ).order_by('-timestamp')

        reset = self.request.GET.get('reset')
        search_submitted =  self.request.GET.get('search_submitted')
        search_text = self.request.GET.get('search')
        search_date = self.request.GET.get('search_date')
        hide_empty_cronjobs = self.request.GET.get('hide_empty_cronjobs')

        if reset or (not (search_text or search_date) and hide_empty_cronjobs) or (not reset and not search_submitted):
            return queryset

        if not hide_empty_cronjobs:
            queryset = ActivityLog.objects.all().order_by('-timestamp')

        if search_date:
            try:
                search_date = datetime.strptime(search_date, '%d-%b-%Y')
                start_datetime = search_date
                end_datetime = search_date.replace(hour=23, minute=59, second=59, microsecond=999999)
                queryset = queryset.filter(
                    Q(timestamp__gte=start_datetime) & Q(timestamp__lte=end_datetime)
                ).order_by('-timestamp')
            except ValueError:
                messages.error(
                    self.request, 'Invalid search date format.  Please select '
                    'from datepicker or enter using the format dd-Mmm-YYYY'
                )
                return queryset

        if search_text:
            queryset = queryset.filter(
                log__contains=search_text).order_by('-timestamp')

        return queryset

    def get_context_data(self):
        context = super(ActivityLogListView, self).get_context_data()
        context['sidenav_selection'] = 'activitylog'

        search_submitted =  self.request.GET.get('search_submitted')
        hide_empty_cronjobs = self.request.GET.get('hide_empty_cronjobs') \
        if search_submitted else 'on'

        search_text = self.request.GET.get('search', '')
        search_date = self.request.GET.get('search_date', None)
        reset = self.request.GET.get('reset')
        if reset:
            hide_empty_cronjobs = 'on'
            search_text = ''
            search_date = None
        form = ActivityLogSearchForm(
            initial={
                'search': search_text, 'search_date': search_date,
                'hide_empty_cronjobs': hide_empty_cronjobs
            })
        context['form'] = form

        return context


@login_required
@staff_required
def event_waiting_list_view(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    waiting_list_users = WaitingListUser.objects.filter(
        event__id=event_id).order_by('user__username')
    ev_type = 'lessons' if event.event_type.event_type == 'CL' else 'events'

    template = 'studioadmin/event_waiting_list.html'
    return TemplateResponse(
        request, template, {
            'waiting_list_users': waiting_list_users, 'event': event,
            'sidenav_selection': '{}_register'.format(ev_type)
        }
    )

@login_required
@staff_required
def cancel_event_view(request, slug):
    event = get_object_or_404(Event, slug=slug)
    ev_type = 'class' if event.event_type.event_type == 'CL' else 'event'

    open_bookings = [
        booking for booking in event.bookings.all() if booking.status == 'OPEN'
        ]

    open_direct_paid_bookings = [
        booking for booking in open_bookings if
        (booking.paid or booking.deposit_paid) and
        not booking.block and not booking.free_class
    ]

    if request.method == 'POST':
        if 'confirm' in request.POST:
            for booking in open_bookings:

                block_paid = bool(booking.block)
                direct_paid = booking in open_direct_paid_bookings

                if booking.block:
                    booking.block = None
                    booking.paid = False
                    booking.payment_confirmed = False
                elif booking.free_class:
                    booking.free_class = False
                    booking.paid = False
                    booking.payment_confirmed = False

                booking.status = "CANCELLED"
                booking.save()

                try:
                    # send notification email to user
                    host = 'http://{}'.format(request.META.get('HTTP_HOST'))
                    # send email to studio
                    ctx = Context({
                          'host': host,
                          'event_type': ev_type,
                          'block': block_paid,
                          'direct_paid': direct_paid,
                          'event': event,
                          'user': booking.user,
                    })
                    send_mail('{} {} has been cancelled'.format(
                        settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, ev_type.title(),
                        ),
                        get_template(
                            'studioadmin/email/event_cancelled.txt'
                        ).render(ctx),
                        settings.DEFAULT_FROM_EMAIL,
                        [booking.user.email],
                        html_message=get_template(
                            'studioadmin/email/event_cancelled.html'
                            ).render(ctx),
                        fail_silently=False)
                except Exception as e:
                    # send mail to tech support with Exception
                    send_support_email(
                        e, __name__, "cancel event - "
                        "send notification email to user"
                    )

            event.cancelled = True
            event.booking_open = False
            event.payment_open = False
            event.save()

            if open_direct_paid_bookings:
                # email studio with links for confirming refunds

                try:
                    # send notification email to user
                    host = 'http://{}'.format(request.META.get('HTTP_HOST'))
                    # send email to studio
                    ctx = Context({
                          'host': host,
                          'event_type': ev_type,
                          'open_direct_paid_bookings': open_direct_paid_bookings,
                          'event': event,
                    })
                    send_mail('{} Refunds due for cancelled {}'.format(
                        settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, ev_type.title(),
                        ),
                        get_template(
                            'studioadmin/email/to_studio_event_cancelled.txt'
                        ).render(ctx),
                        settings.DEFAULT_FROM_EMAIL,
                        [settings.DEFAULT_STUDIO_EMAIL],
                        html_message=get_template(
                            'studioadmin/email/to_studio_event_cancelled.html'
                            ).render(ctx),
                        fail_silently=False)
                except Exception as e:
                    # send mail to tech support with Exception
                    send_support_email(
                        e, __name__, "cancel event - "
                        "send refund notification email to tudio"
                    )

            if open_bookings:
                booking_cancelled_msg = 'open ' \
                                        'booking(s) for {} have been cancelled ' \
                                        'and notification emails have been ' \
                                        'sent.'.format(
                    ev_type.title(),
                    ', '.join(
                        ['{} {}'.format(booking.user.first_name,
                                        booking.user.last_name)
                         for booking in open_bookings]
                        )
                    )
            else:
                booking_cancelled_msg = 'there were ' \
                                        'no open bookings for this {}'.format(
                    ev_type.title(), ev_type
                )
            messages.info(
                request, '{} has been cancelled; ' + booking_cancelled_msg
            )

            ActivityLog.objects.create(
                log="{} {} has been cancelled by admin user {}; {}".format(
                    ev_type.title(), event, request.user.username,
                    booking_cancelled_msg
                )
            )

            return HttpResponseRedirect(
                reverse('studioadmin:{}'.format(
                    'events' if ev_type == 'event' else 'lessons'
                ))
            )
        elif 'cancel' in request.POST:
            return HttpResponseRedirect(
                reverse('studioadmin:{}'.format(
                    'events' if ev_type == 'event' else 'lessons'
                ))
            )

    context = {
        'event': event,
        'event_type': ev_type,
        'open_bookings': open_bookings,
        'open_direct_paid_bookings': open_direct_paid_bookings
    }

    return TemplateResponse(
        request, 'studioadmin/cancel_event.html', context
    )


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
            ctx = Context({
                  'host': host,
                  'ticketed_event': self.ticketed_event,
                  'action': action,
            })
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
                    ctx = Context({
                          'host': host,
                          'ticketed_event': ticketed_event,
                          'ticket_booking': booking,
                    })
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
                    ctx = Context({
                          'host': host,
                          'open_paid_ticket_bookings': open_paid_ticket_bookings,
                          'ticketed_event': ticketed_event,
                    })
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
                log="{} has been cancelled by admin user {}. {}".format(
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

            ctx = Context({
                'ticketed_event': ticket_booking.ticketed_event,
                'ticket_booking': ticket_booking,
                'host': 'http://{}'.format(self.request.META.get('HTTP_HOST'))

            })

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

            ActivityLog(
                log='Payment refund for ticket booking ref {} for event {}, '
                    '(user {}) has been updated by admin user {}'.format(
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
