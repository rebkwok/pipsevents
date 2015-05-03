from django import forms
from django.conf import settings
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.db.models import Q

from django.shortcuts import HttpResponseRedirect, render, get_object_or_404
from django.views.generic import CreateView, ListView, UpdateView
from django.utils import timezone
from django.core.mail import send_mail

from braces.views import LoginRequiredMixin, StaffuserRequiredMixin

from booking.models import Event, Booking, Block, BlockType
from booking.forms import SimpleBookingRegisterFormSet, ConfirmPaymentForm, \
    StatusFilter


class ConfirmPaymentView(LoginRequiredMixin, UpdateView):

    model = Booking
    template_name = 'studioadmin/confirm_payment.html'
    success_message = 'Change to payment status confirmed.  An update email ' \
                      'has been sent to user {}.'
    form_class = ConfirmPaymentForm

    def get(self, request, *args, **kwargs):
        if not self.request.user.is_staff:
            return HttpResponseRedirect(reverse('booking:permission_denied'))
        return super(ConfirmPaymentView, self).get(request, *args, **kwargs)

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


class ConfirmRefundView(LoginRequiredMixin, UpdateView):

    model = Booking
    template_name = 'studioadmin/confirm_refunded.html'
    success_message = "Refund of payment for {}'s booking for {} has been " \
                      "confirmed.  An update email has been sent to {}."
    fields = '__all__'

    def get(self, request, *args, **kwargs):
        if not self.request.user.is_staff:
            return HttpResponseRedirect(reverse('booking:permission_denied'))
        return super(ConfirmRefundView, self).get(request, *args, **kwargs)

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


def register_view(request, event_slug, status_choice='OPEN'):

    event = get_object_or_404(Event, slug=event_slug)

    if not request.user.is_authenticated():
        return HttpResponseRedirect(reverse('account_login'))
    if not request.user.is_staff:
        return HttpResponseRedirect(reverse('booking:permission_denied'))

    if request.method == 'POST':
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
            return HttpResponseRedirect(
                reverse('studioadmin:register',
                        kwargs={'event_slug': event.slug,
                                'status_choice': status_choice})
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

    return render(
        request, 'studioadmin/register.html', {
            'formset': formset, 'event': event, 'status_filter': status_filter,
            'extra_lines': extra_lines
        }
    )


class EventAdminListView(StaffuserRequiredMixin, ListView):

    model = Event
    context_object_name = 'events'
    template_name = 'studioadmin/admin_events.html'

    def get(self, request, *args, **kwargs):
        self.ev_type = kwargs['type']
        self.ev_type_abbreviation = 'EV' if self.ev_type == 'events' else 'CL'
        return super(EventAdminListView, self).get(request)

    def get_queryset(self):
        return Event.objects.filter(
            event_type__event_type=self.ev_type_abbreviation,
            date__gte=timezone.now()
        ).order_by('date')

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(EventAdminListView, self).get_context_data(**kwargs)
        context['type'] = self.ev_type

        return context


class EventAdminUpdateView(StaffuserRequiredMixin, UpdateView):

    pass


class EventAdminCreateView(StaffuserRequiredMixin, CreateView):

    pass


class TimetableListView(StaffuserRequiredMixin, ListView):

    pass


class TimetableSessionDetailView(StaffuserRequiredMixin, UpdateView):

    pass


class TimetableSessionDetailView(StaffuserRequiredMixin, CreateView):

    pass


def upload_timetable_view(request):

    pass


def email_event_users_view(request):

    pass
