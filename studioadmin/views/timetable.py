import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.shortcuts import HttpResponseRedirect, render, get_object_or_404
from django.views.generic import CreateView, UpdateView
from django.utils.safestring import mark_safe

from braces.views import LoginRequiredMixin

from booking import utils
from booking.models import Event
from timetable.models import Session
from studioadmin.forms import TimetableSessionFormSet, SessionAdminForm, \
    DAY_CHOICES, UploadTimetableForm
from studioadmin.views.helpers import staff_required, StaffUserMixin
from activitylog.models import ActivityLog


logger = logging.getLogger(__name__)


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

                sessionformset.save()
            return HttpResponseRedirect(
                reverse('studioadmin:timetable')
            )
        else:  # pragma: no cover
            # all fields are booleans; no errors will be thrown, but keep this
            # code in case we change the fields in future
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

            if 'paypal_email' in form.changed_data and \
                session.paypal_email != settings.DEFAULT_PAYPAL_EMAIL:
                messages.warning(
                    self.request,
                    mark_safe(
                        "You have changed the paypal receiver email. If you "
                        "haven't used this email before, "
                        "it is strongly recommended that you test the email "
                        "address "
                        "<a href='/studioadmin/test-paypal-email?email={}'>"
                        "here</a>".format(session.paypal_email)
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

        if session.paypal_email != settings.DEFAULT_PAYPAL_EMAIL:
            messages.warning(
                self.request,
                mark_safe(
                    "You have changed the paypal receiver email from the "
                    "default value. If you haven't used this email before, "
                    "it is strongly recommended that you test the email "
                    "address "
                    "<a href='/studioadmin/test-paypal-email?email={}'>"
                    "here</a>".format(session.paypal_email)
                )
            )

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

            override_options = {
                "visible_on_site": form.cleaned_data['override_options_visible_on_site'],
                "booking_open": form.cleaned_data['override_options_booking_open'],
                "payment_open": form.cleaned_data['override_options_payment_open']
            }

            created_classes, existing_classes, duplicate_classes = \
                utils.upload_timetable(
                    start_date, end_date, session_ids, request.user, override_options=override_options
                )

            def _format_override_option(value):
                value = int(value)
                return "yes" if value == 1 else "no"

            context = {'start_date': start_date,
                       'end_date': end_date,
                       'created_classes': created_classes,
                       'existing_classes': existing_classes,
                       'duplicate_classes': duplicate_classes,
                       'sidenav_selection': 'upload_timetable',
                       'override_options': ', '.join([f'{key.replace("_", " ")} ({_format_override_option(value)})' for key, value in override_options.items() if value != "default"]),
                       }
            return render(
                request, 'studioadmin/upload_timetable_confirmation.html',
                context
            )
        else:
            location_forms = [{
                'index': 0,
                'form': form,
                'location': 'All locations'
            }]
    else:
        location_forms = [{
            'index': 0,
            'form': UploadTimetableForm(location='all'),
            'location': 'All locations'
        }]
        for i, location in enumerate(
                [lc[0] for lc in Event.LOCATION_CHOICES], 1
        ):
            if Session.objects.filter(location=location).exists():
                location_obj = {
                    'index': i,
                    'form': UploadTimetableForm(location=location),
                    'location': location
                }
                location_forms.append(location_obj)

    return render(
        request, template_name,
        {
            'location_forms': location_forms,
            'sidenav_selection': 'upload_timetable'
        }
    )
