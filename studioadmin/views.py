import urllib.parse
import ast
from functools import wraps

from django.db.utils import IntegrityError
from django import forms
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.template.loader import get_template
from django.template import Context

from django.shortcuts import HttpResponseRedirect, redirect, \
    render, get_object_or_404
from django.views.generic import CreateView, ListView, UpdateView, DeleteView
from django.utils import timezone
from django.core.mail import send_mail

from braces.views import LoginRequiredMixin

from booking.models import Event, Booking, Block, BlockType
from booking import utils

from timetable.models import Session
from studioadmin.forms import ConfirmPaymentForm, EventFormSet, \
    EventAdminForm, SimpleBookingRegisterFormSet, StatusFilter, \
    TimetableSessionFormSet, SessionAdminForm, DAY_CHOICES, \
    UploadTimetableForm, EmailUsersForm, ChooseUsersFormSet, UserFilterForm, \
    BlockStatusFilter, UserBookingFormSet, UserBlockFormSet


class ImproperlyConfigured(Exception):
    pass


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
    success_message = 'Change to payment status confirmed.  An update email ' \
                      'has been sent to user {}.'
    form_class = ConfirmPaymentForm


    def get_initial(self):
        return {
            'payment_confirmed': self.object.payment_confirmed
        }

    def form_valid(self, form):

        if form.has_changed():
            booking = form.save(commit=False)
            booking.paid = form.data.get( 'paid', False)
            booking.payment_confirmed = form.data.get(
                'payment_confirmed', False
            )
            booking.date_payment_confirmed = timezone.now()
            booking.save()

            messages.success(
                self.request,
                self.success_message.format(booking.user.username)
            )

            if booking.paid and booking.payment_confirmed:
                payment_status = 'paid and confirmed'
            elif booking.paid:
                payment_status = "paid - payment not confirmed yet"
            else:
                payment_status = 'not paid'
            send_mail(
                '{} Payment status updated for {}'.format(
                    settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, booking.event),
                "Your payment status has been updated to {}.".format(
                    payment_status
                ),
                settings.DEFAULT_FROM_EMAIL,
                [self.request.user.email],
                fail_silently=False)
            # TODO implenent templates

        else:
            messages.info(
                self.request, "Saved without making changes to the payment "
                              "status for {}'s booking for {}.".format(
                    self.object.user.username, self.object.event)
            )

        return HttpResponseRedirect(self.get_success_url())


class ConfirmRefundView(LoginRequiredMixin, StaffUserMixin, UpdateView):

    model = Booking
    template_name = 'studioadmin/confirm_refunded.html'
    success_message = "Refund of payment for {}'s booking for {} has been " \
                      "confirmed.  An update email has been sent to {}."
    fields = '__all__'


    def form_valid(self, form):

        if 'confirmed' in self.request.POST:
            booking = form.save(commit=False)
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

            send_mail(
                '{} Payment refund confirmed for {}'.format(
                    settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, booking.event),
                "Your payment has been confirmed as refunded for {}".format(
                    booking.event),
                settings.DEFAULT_FROM_EMAIL,
                [self.request.user.email],
                fail_silently=False)
            # TODO implenent templates

        if 'cancelled' in self.request.POST:
            messages.info(
                self.request,
                "Cancelled; no changes to payment status for {}'s booking "
                "for {}".format(booking.user.username, booking.event)
            )
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('studioadmin:lessons')


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
                    if form.has_changed():
                        messages.info(
                            request,
                            "Register updated for user {}".format(
                                form.instance.user.username
                            )
                        )
                        form.save(commit=False)

                    for error in form.errors:
                        messages.error(request, "{}".format(error),
                                       extra_tags='safe')
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
                request, "There were errors in the following fields:"
            )
            for error in formset.errors:
                messages.error(request, "{}".format(error), extra_tags='safe')
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

    if event.max_participants:
        extra_lines = event.spaces_left()
    elif event.max_participants < 25:
        extra_lines = 25 - event.spaces_left()
    else:
        extra_lines = 2

    template = 'studioadmin/register.html'
    if print_view:
        template = 'studioadmin/register_print.html'

    sidenav_selection = 'events_register'
    if event.event_type.event_type == 'CL':
        sidenav_selection = 'lessons_register'

    return render(
        request, template, {
            'formset': formset, 'event': event, 'status_filter': status_filter,
            'extra_lines': extra_lines, 'print': print_view,
            'status_choice': status_choice,
            'sidenav_selection': sidenav_selection
        }
    )


@login_required
@staff_required
def event_admin_list(request, ev_type):

    ev_type_abbreviation = 'EV' if ev_type == 'events' else 'CL'

    queryset = Event.objects.filter(
        event_type__event_type=ev_type_abbreviation,
        date__gte=timezone.now()
    ).order_by('date')
    events = True if queryset.count() > 0 else False

    if request.method == 'POST':
        eventformset = EventFormSet(request.POST)

        if eventformset.is_valid():
            if not eventformset.has_changed():
                messages.info(request, "No changes were made")
            else:
                for form in eventformset:
                    if form.has_changed():
                        if 'DELETE' in form.changed_data:
                            messages.info(
                                request,
                                'Session <strong>{}</strong> has been deleted!'.format(
                                    form.instance,
                                ),
                                extra_tags='safe'
                            )
                        else:
                            for field in form.changed_data:
                                messages.info(
                                    request,
                                    "<strong>{}</strong> updated for "
                                    "<strong>{}</strong>".format(
                                        field.title().replace("_", " "),
                                        form.instance
                                        ),
                                    extra_tags='safe'
                                )
                        form.save()

                    for error in form.errors:
                        messages.error(request, "{}".format(error),
                                       extra_tags='safe')
                eventformset.save()
            return HttpResponseRedirect(
                reverse('studioadmin:{}'.format(ev_type),)
            )
        else:
            messages.error(
                request, "There were errors in the following fields:"
            )
            for error in eventformset.errors:
                messages.error(request, "{}".format(error), extra_tags='safe')

    else:
        eventformset = EventFormSet(queryset=queryset)

    return render(
        request, 'studioadmin/admin_events.html', {
            'eventformset': eventformset,
            'type': ev_type,
            'events': events,
            'sidenav_selection': ev_type
            }
    )


class EventRegisterListView(LoginRequiredMixin, StaffUserMixin, ListView):

    model = Event
    template_name = 'studioadmin/events_register_list.html'
    context_object_name = 'events'

    def get_queryset(self):
        ev_type_abbreviation = 'EV' if self.kwargs["ev_type"] == 'events' \
            else 'CL'

        return Event.objects.filter(
            event_type__event_type=ev_type_abbreviation,
            date__gte=timezone.now()
        ).order_by('date')

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
        else:
            msg = 'No changes made'
        messages.info(self.request, msg, extra_tags='safe')
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
        messages.info(self.request, '<strong>{} {}</strong> has been '
                                    'created!'.format(msg_ev_type, event.name),
                      extra_tags='safe')
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('studioadmin:{}'.format(self.kwargs["ev_type"] + 's'))


class EventAdminDeleteView(LoginRequiredMixin, StaffUserMixin, DeleteView):
    # Allow deleting; if bookings made, show warning, cancel bookings, email
    # users and studio with refund info and cancel event rather than deleting.
    # Need to add event status open/cancelled to model

    pass


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
                            messages.info(
                                request,
                                'Session <strong>{} {} {}</strong> has been deleted!'.format(
                                form.instance.name,
                                DAY_CHOICES[form.instance.day],
                                form.instance.time.strftime('%H:%M'),
                                ),
                                extra_tags='safe'
                            )
                        else:
                            for field in form.changed_data:
                                messages.info(
                                    request,
                                    "<strong>{}</strong> updated for "
                                    "<strong>{}</strong>".format(
                                        field.title().replace("_", " "),
                                        form.instance
                                        ),
                                    extra_tags='safe'
                                )
                        form.save()

                    for error in form.errors:
                        messages.error(request, "{}".format(error),
                                       extra_tags='safe')
                sessionformset.save()
            return HttpResponseRedirect(
                reverse('studioadmin:timetable')
            )
        else:
            messages.error(
                request, "There were errors in the following fields:"
            )
            for error in sessionformset.errors:
                messages.error(request, "{}".format(error), extra_tags='safe')

    else:
        sessionformset = TimetableSessionFormSet(
            queryset=Session.objects.all().order_by('day')
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
        else:
            msg = 'No changes made'
        messages.info(self.request, msg, extra_tags='safe')
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
        messages.info(self.request, msg, extra_tags='safe')
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
            created_classes, existing_classes = \
                utils.upload_timetable(start_date, end_date)
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
        block_status = self.request.GET.get('block_status', 'active')
        all_blocks = Block.objects.all()
        if block_status == 'all':
            return all_blocks
        elif block_status == 'active':
            active = (block.id for block in all_blocks if block.active_block())
            return Block.objects.filter(id__in=active)
        elif block_status == 'unpaid':
            unpaid = (block.id for block in all_blocks
                      if not block.expired and not block.paid
                      and not block.full)
            return Block.objects.filter(id__in=unpaid)
        elif block_status == 'expired':
            expired = (block.id for block in all_blocks if block.expired)
            return Block.objects.filter(id__in=expired)
        elif block_status == 'full':
            full = (block.id for block in all_blocks if block.full)
            return Block.objects.filter(id__in=full)

    def get_context_data(self):
        context = super(BlockListView, self).get_context_data()
        context['sidenav_selection'] = 'blocks'

        block_status = self.request.GET.get('block_status', 'active')
        form = BlockStatusFilter(initial={'block_status': block_status})
        context['form'] = form

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
                        messages.error(request, "{}".format(error),
                                           extra_tags='safe')

            request.session['users_to_email'] = users_to_email

            return HttpResponseRedirect(url_with_querystring(
                reverse('studioadmin:email_users_view'), events=event_ids, lessons=lesson_ids)
            )

        else:
            messages.error(
                request, "There were errors in the following fields:"
            )
            for error in usersformset.errors:
                messages.error(request, "{}".format(error), extra_tags='safe')

    else:
        usersformset = ChooseUsersFormSet(
            queryset=User.objects.all().order_by('username'),
        )

    userfilterform = UserFilterForm(prefix='filter', initial=initial_userfilterdata)

    return render(
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
                    send_mail(subject, message, from_address,
                              [email_address],
                              html_message=get_template(
                                  'studioadmin/email/email_users.html').render(
                                  Context({
                                      'subject': subject,
                                      'message': message})
                              ),
                              fail_silently=False)

                return render(request,
                    'studioadmin/email_users_confirmation.html')

            else:
                event_ids = request.session.get('events')
                lesson_ids = request.session.get('lessons')
                events = Event.objects.filter(id__in=event_ids)
                lessons = Event.objects.filter(id__in=lesson_ids)
                totaleventids = event_ids + lesson_ids
                totalevents = Event.objects.filter(id__in=totaleventids)
                messages.error(request, "Please correct errors in form: {}".format(form.errors), extra_tags='safe')
                form = EmailUsersForm(initial={'subject': "; ".join((str(event) for event in totalevents))})

        else:
            event_ids = ast.literal_eval(request.GET['events'])
            events = Event.objects.filter(id__in=event_ids)
            lesson_ids = ast.literal_eval(request.GET['lessons'])
            lessons = Event.objects.filter(id__in=lesson_ids)
            totaleventids = event_ids + lesson_ids
            totalevents = Event.objects.filter(id__in=totaleventids)
            form = EmailUsersForm(initial={'subject': "; ".join((str(event) for event in totalevents))})

        return render(
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
def user_bookings_view(request, user_id):

    user = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        userbookingformset = UserBookingFormSet(
            request.POST,
            instance=user,
            user=user
        )

        if userbookingformset.is_valid():
            if not userbookingformset.has_changed():
                messages.info(request, "No changes were made")
            else:
                for form in userbookingformset:
                    if form.has_changed():
                        new = False if form.instance.id else True
                        reopened = False
                        try:
                            booking = Booking.objects.get(
                                user__id=form.instance.user.id,
                                event__id=form.instance.event.id,
                                status='CANCELLED'
                            )
                            reopened = True
                            booking.status = 'OPEN'
                            booking.paid = form.instance.paid
                            booking.block = form.instance.block
                        except Booking.DoesNotExist:
                            booking = form.save(commit=False)

                        if booking.block:
                            booking.paid = True
                            booking.payment_confirmed = True

                        elif booking.paid:
                            # assume that if booking is being done via
                            # studioadmin, marking paid also means payment
                            # is confirmed
                            booking. payment_confirmed = True

                        msg = 'created' if new else 'updated'
                        messages.info(
                            request,
                            'Booking for {} has been {}'.format(booking.event, msg)
                        )
                        if reopened:
                            messages.info(
                                request, 'Note: this booking was previously '
                                'cancelled and has now been reopened')
                        booking.save()

                    for error in form.errors:
                        messages.error(request, "{}".format(error),
                                       extra_tags='safe')

                try:
                    userbookingformset.save(commit=False)
                except IntegrityError:
                    # we filter the options for event in the select, so we
                    # only have integrity error for saving a previously
                    # cancelled booking, which is dealt with above
                    pass

            return HttpResponseRedirect(
                reverse('studioadmin:user_bookings_list',
                        kwargs={'user_id': user.id}
                        )
            )
        else:
            messages.error(
                request, "There were errors in the following fields:"
            )
            for error in userbookingformset.errors:
                messages.error(request, "{}".format(error), extra_tags='safe')
    else:
        queryset = Booking.objects.filter(
            user=user, event__date__gte=timezone.now(), status='OPEN'
        ).order_by('event__date')
        userbookingformset = UserBookingFormSet(
            instance=user,
            queryset=queryset,
            user=user
        )

    template = 'studioadmin/user_booking_list.html'
    return render(
        request, template, {
            'userbookingformset': userbookingformset, 'user': user,
            'sidenav_selection': 'users'
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
                        new = False if form.instance.id else True
                        block = form.save(commit=False)
                        if block.paid:
                            block.payment_confirmed = True
                        msg = 'created' if new else 'updated'
                        messages.info(
                            request,
                            'Block for {} has been {}'.format(block.block_type.event_type, msg)
                        )
                        block.save()

                    for error in form.errors:
                        messages.error(request, "{}".format(error),
                                       extra_tags='safe')
                userblockformset.save(commit=False)

            return HttpResponseRedirect(
                reverse('studioadmin:user_blocks_list',
                        kwargs={'user_id': user.id}
                        )
            )
        else:
            messages.error(
                request, "There were errors in the following fields:"
            )
            for error in userblockformset.errors:
                messages.error(request, "{}".format(error), extra_tags='safe')
    else:
        queryset = Block.objects.filter(
            user=user).order_by('start_date')
        userblockformset = UserBlockFormSet(
            instance=user,
            queryset=queryset,
            user=user
        )

    template = 'studioadmin/user_block_list.html'
    return render(
        request, template, {
            'userblockformset': userblockformset, 'user': user,
            'sidenav_selection': 'users'
        }
    )