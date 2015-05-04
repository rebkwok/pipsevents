from django import forms
from django.conf import settings
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.db.models import Q


from django.shortcuts import HttpResponseRedirect, render, get_object_or_404
from django.views.generic import CreateView, ListView, UpdateView, DeleteView
from django.utils import timezone
from django.core.mail import send_mail

from braces.views import LoginRequiredMixin

from booking.models import Event, Booking, Block, BlockType

from studioadmin.forms import ConfirmPaymentForm, EventFormSet, \
    EventAdminForm, SimpleBookingRegisterFormSet, StatusFilter


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


def register_view(request, event_slug, status_choice='OPEN', print=False):

    event = get_object_or_404(Event, slug=event_slug)

    if not request.user.is_authenticated():
        return HttpResponseRedirect(reverse('account_login'))
    if not request.user.is_staff:
        return HttpResponseRedirect(reverse('booking:permission_denied'))

    if request.method == 'POST':

        if request.POST.get("print"):
            print = True

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
            if print:
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
    if print:
        template = 'studioadmin/register_print.html'

    sidenav_selection = 'events_register'
    if event.event_type.event_type == 'CL':
        sidenav_selection = 'lessons_register'

    return render(
        request, template, {
            'formset': formset, 'event': event, 'status_filter': status_filter,
            'extra_lines': extra_lines, 'print': print,
            'status_choice': status_choice,
            'sidenav_selection': sidenav_selection
        }
    )


def event_admin_list(request, ev_type):
    if not request.user.is_authenticated():
        return HttpResponseRedirect(reverse('account_login'))
    if not request.user.is_staff:
        return HttpResponseRedirect(reverse('booking:permission_denied'))

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
                        for field in form.changed_data:
                            messages.info(
                            request,
                            "{} updated for {}".format(
                                field, form.instance
                            )
                        )
                        form.save(commit=False)

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

    def get_object(self):
        queryset = Event.objects.all()
        return get_object_or_404(queryset, slug=self.kwargs['slug'])

    def get_context_data(self, **kwargs):
        context = super(EventAdminUpdateView, self).get_context_data(**kwargs)
        context['type'] = self.kwargs["ev_type"][0:-1]
        if self.kwargs["ev_type"] == "lessons":
            context['type'] = "class"
        context['sidenav_selection'] = self.kwargs['ev_type']

        return context

    def form_valid(self, form):
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('studioadmin:{}'.format(self.kwargs["ev_type"]))


class EventAdminCreateView(LoginRequiredMixin, StaffUserMixin, CreateView):

    form_class = EventAdminForm
    model = Event
    template_name = 'studioadmin/event_create_update.html'
    context_object_name = 'event'

    def get_context_data(self, **kwargs):
        context = super(EventAdminCreateView, self).get_context_data(**kwargs)
        context['type'] = self.kwargs["ev_type"]
        if self.kwargs["ev_type"] == "lesson":
            context['type'] = "class"
        context['sidenav_selection'] = 'add_{}'.format(self.kwargs['ev_type'])
        return context

    def form_valid(self, form):
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('studioadmin:{}'.format(self.kwargs["ev_type"]))


class EventAdminDeleteView(LoginRequiredMixin, StaffUserMixin, DeleteView):
    # Allow deleting; if bookings made, show warning, cancel bookings, email
    # users and studio with refund info and cancel event rather than deleting.
    # Need to add event status open/cancelled to model

    pass


class TimetableListView(LoginRequiredMixin, StaffUserMixin, ListView):

    pass


class TimetableSessionUpdateView(
    LoginRequiredMixin, StaffUserMixin, UpdateView
):

    pass


class TimetableSessionCreateView(
    LoginRequiredMixin, StaffUserMixin, CreateView
):

    pass


class TimetableSessionDeleteView(
    LoginRequiredMixin, StaffUserMixin, DeleteView
):
    # sessions can be deleted safely as there are no bookings made against them

    pass


def upload_timetable_view(request):

    pass


def email_event_users_view(request):

    pass
