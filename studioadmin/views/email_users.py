import ast
import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User

from django.contrib import messages
from django.core.urlresolvers import reverse
from django.template.loader import get_template
from django.template.response import TemplateResponse
from django.shortcuts import HttpResponseRedirect, render
from django.utils.safestring import mark_safe
from django.core.mail.message import EmailMultiAlternatives

from booking.models import Event, Booking
from booking.email_helpers import send_support_email

from studioadmin.forms import EmailUsersForm, ChooseUsersFormSet, \
    UserFilterForm
from studioadmin.views.helpers import staff_required, url_with_querystring

from activitylog.models import ActivityLog


logger = logging.getLogger(__name__)


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
        usersformset = ChooseUsersFormSet(
            queryset=User.objects.all().order_by('username'),
        )

    userfilterform = UserFilterForm(
        prefix='filter', initial=initial_userfilterdata
    )

    return TemplateResponse(
        request, template_name, {
            'usersformset': usersformset,
            'userfilterform': userfilterform,
            'sidenav_selection': 'email_users',
            }
    )


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

                for email_address in email_addresses:
                    try:
                        msg = EmailMultiAlternatives(
                            subject, message, from_address, [email_address],
                            cc=[from_address] if cc else [], reply_to=[from_address]
                        )
                        msg.attach_alternative(
                            get_template(
                                'studioadmin/email/email_users.html').render(
                                  {
                                      'subject': subject,
                                      'message': message
                                  }
                              ),
                            "text/html"
                        )
                        msg.send(fail_silently=False)
                    except Exception as e:
                        # send mail to tech support with Exception
                        send_support_email(
                            e, __name__, "Bulk Email to students"
                        )
                        ActivityLog.objects.create(
                            log="Possible error with sending bulk email; "
                                "notification sent to tech support"
                        )
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
                messages.error(
                    request,
                    mark_safe(
                        "Please correct errors in form: {}".format(form.errors)
                    )
                )
                form = EmailUsersForm(
                    initial={
                        'subject': "; ".join(
                            (str(event) for event in totalevents)
                        )
                    }
                )

        else:
            event_ids = ast.literal_eval(request.GET.get('events'))
            events = Event.objects.filter(id__in=event_ids)
            lesson_ids = ast.literal_eval(request.GET.get('lessons'))
            lessons = Event.objects.filter(id__in=lesson_ids)
            totaleventids = event_ids + lesson_ids
            totalevents = Event.objects.filter(id__in=totaleventids)
            form = EmailUsersForm(
                initial={
                    'subject': "; ".join((str(event) for event in totalevents))
                }
            )

        return TemplateResponse(
            request, template_name, {
                'form': form,
                'users_to_email': users_to_email,
                'sidenav_selection': 'email_users',
                'events': events,
                'lessons': lessons
            }
        )

