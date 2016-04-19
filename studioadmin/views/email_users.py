import ast
import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, User

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
    userfilterform = UserFilterForm(prefix='filter')
    if 'filter' in request.POST:
        event_ids = request.POST.getlist('filter-events')
        lesson_ids = request.POST.getlist('filter-lessons')

        if event_ids == ['']:
            if request.session.get('events'):
                del request.session['events']
            event_ids = []
        elif '' in event_ids:
            event_ids.remove('')
        else:
            request.session['events'] = event_ids

        if lesson_ids == ['']:
            if request.session.get('lessons'):
                del request.session['lessons']
            lesson_ids = []
        elif '' in lesson_ids:
            lesson_ids.remove('')
        else:
            request.session['lessons'] = lesson_ids

        if not event_ids and not lesson_ids:
            usersformset = ChooseUsersFormSet(
                queryset=User.objects.all().order_by('first_name', 'last_name')
            )
        else:
            event_and_lesson_ids = event_ids + lesson_ids
            bookings = Booking.objects.filter(event__id__in=event_and_lesson_ids)
            user_ids = set([booking.user.id for booking in bookings
                            if booking.status == 'OPEN'])
            usersformset = ChooseUsersFormSet(
                queryset=User.objects.filter(id__in=user_ids)
                .order_by('first_name', 'last_name')
            )
            userfilterform = UserFilterForm(
                prefix='filter',
                initial={'events': event_ids, 'lessons': lesson_ids}
            )

    elif request.method == 'POST':
        userfilterform = UserFilterForm(prefix='filter', data=request.POST)
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

            request.session['users_to_email'] = users_to_email

            return HttpResponseRedirect(url_with_querystring(
                reverse('studioadmin:email_users_view'), events=event_ids, lessons=lesson_ids)
            )

    else:
        # for a new GET, remove any event/lesson session data
        if request.session.get('events'):
            del request.session['events']
        if request.session.get('lessons'):
            del request.session['lessons']
        usersformset = ChooseUsersFormSet(
            queryset=User.objects.all().order_by('first_name', 'last_name'),
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
def email_users_view(request, mailing_list=False,
                     template_name='studioadmin/email_users_form.html'):

        if mailing_list:
            subscribed, _ = Group.objects.get_or_create(name='subscribed')
            users_to_email = subscribed.user_set.all()
        else:
            users_to_email = User.objects.filter(
                id__in=request.session['users_to_email']
            )

        if request.method == 'POST':

            form = EmailUsersForm(request.POST)
            test_email = request.POST.get('send_test', False)

            if form.is_valid():
                subject = '{} {}{}'.format(
                    settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,
                    form.cleaned_data['subject'],
                    ' [TEST EMAIL]' if test_email else ''
                )
                from_address = form.cleaned_data['from_address']
                message = form.cleaned_data['message']
                cc = form.cleaned_data['cc']

                # bcc recipients
                email_addresses = [user.email for user in users_to_email]
                host = 'http://{}'.format(request.META.get('HTTP_HOST'))
                try:
                    msg = EmailMultiAlternatives(
                        subject,
                        get_template(
                            'studioadmin/email/email_users.txt').render(
                              {
                                  'subject': subject,
                                  'message': message,
                                  'mailing_list': mailing_list,
                                  'host': host,
                              }),
                        bcc=[from_address] if test_email else email_addresses,
                        cc=[from_address] if cc else [],
                        reply_to=[from_address]
                        )
                    msg.attach_alternative(
                        get_template(
                            'studioadmin/email/email_users.html').render(
                              {
                                  'subject': subject,
                                  'message': message,
                                  'mailing_list': mailing_list,
                                  'host': host,
                              }
                          ),
                        "text/html"
                    )
                    msg.send(fail_silently=False)

                    if not test_email:
                        ActivityLog.objects.create(
                        log='Bulk email with subject "{}" sent to users {} by '
                            'admin user {}'.format(
                            subject, ', '.join(email_addresses),
                            request.user.username
                        )
                    )
                except Exception as e:
                    # send mail to tech support with Exception
                    send_support_email(
                        e, __name__, "Bulk Email to students"
                    )
                    ActivityLog.objects.create(
                        log="Possible error with sending bulk email; "
                            "notification sent to tech support"
                    )

                    if not test_email:
                        ActivityLog.objects.create(
                            log='Bulk email error for users {} '
                                '(email subject "{}"), sent by '
                                'by admin user {}'.format(
                                 ', '.join(email_addresses), subject,
                                    request.user.username
                                )
                        )

                if not test_email:
                    return render(
                        request,
                        'studioadmin/email_users_confirmation.html',
                    )
                else:
                    messages.success(
                        request, 'Test email has been sent to {} only. Click '
                                 '"Send Email" below to send this email to '
                                 'users.'.format(
                                    from_address
                                    )
                    )
            
            # Do this if form not valid OR sending test email
            event_ids = request.session.get('events', [])
            lesson_ids = request.session.get('lessons', [])
            events = Event.objects.filter(id__in=event_ids)
            lessons = Event.objects.filter(id__in=lesson_ids)

            if form.errors:
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

            if test_email:
                form = EmailUsersForm(request.POST)

        else:
            event_ids = ast.literal_eval(request.GET.get('events', '[]'))
            events = Event.objects.filter(id__in=event_ids)
            lesson_ids = ast.literal_eval(request.GET.get('lessons', '[]'))
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
                'sidenav_selection': 'mailing_list'
                if mailing_list else 'email_users',
                'events': events,
                'lessons': lessons,
                'mailing_list': mailing_list
            }
        )

