import time

from django.conf import settings
from django.contrib.auth.models import User, Group

from allauth.account.models import EmailAddress

from rest_framework import status
from rest_framework.response import Response
from rest_framework.serializers import ModelSerializer
from rest_framework.views import APIView

from activitylog.models import ActivityLog

import logging

logger = logging.getLogger(__name__)

class UserSerializer(ModelSerializer):
    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name')


class MailingListAPIView(APIView):
    """
    List mailing list users, or update.
    Webhook for mailchimp to update mailing list and user info.
    """
    def __init__(self, *args, **kwargs):
        super(MailingListAPIView, self).__init__(*args, **kwargs)
        self.group, _ = Group.objects.get_or_create(name='subscribed')

    def get(self, request, format=None):
        list_users = self.group.user_set.all().order_by('first_name', 'last_name')
        serializer = UserSerializer(list_users, many=True)
        return Response(serializer.data)

    def post(self, request, format=None):
        """
        Data is received once per user, in format:

        SUBSCRIBE
        {"type": "subscribe",
        "fired_at": "2009-03-26 21:35:57",
        "data[id]": "8a25ff1d98",
        "data[list_id]": "a6b5da1054",
        "data[email]": "api@mailchimp.com",
        "data[email_type]": "html",
        "data[merges][EMAIL]": "api@mailchimp.com",
        "data[merges][FNAME]": "MailChimp",
        "data[merges][LNAME]": "API",
        "data[merges][INTERESTS]": "Group1,Group2",
        "data[ip_opt]": "10.20.10.30",
        "data[ip_signup]": "10.20.10.30"}

        UNSUBSCRIBE
        {"type": "unsubscribe",
        "fired_at": "2009-03-26 21:40:57",
        "data[action]": "unsub",
        "data[reason]": "manual",
        "data[id]": "8a25ff1d98",
        "data[list_id]": "a6b5da1054",
        "data[email]": "api+unsub@mailchimp.com",
        "data[email_type]": "html",
        "data[merges][EMAIL]": "api+unsub@mailchimp.com",
        "data[merges][FNAME]": "MailChimp",
        "data[merges][LNAME]": "API",
        "data[merges][INTERESTS]": "Group1,Group2",
        "data[ip_opt]": "10.20.10.30",
        "data[campaign_id]": "cb398d21d2",
        "data[reason]": "hard"}

        PROFILE CHANGES
        {"type": "profile",
        "fired_at": "2009-03-26 21:31:21",
        "data[id]": "8a25ff1d98",
        "data[list_id]": "a6b5da1054",
        "data[email]": "api@mailchimp.com",
        "data[email_type]": "html",
        "data[merges][EMAIL]": "api@mailchimp.com",
        "data[merges][FNAME]": "MailChimp",
        "data[merges][LNAME]": "API",
        "data[merges][INTERESTS]": "Group1,Group2",
        "data[ip_opt]": "10.20.10.30"}

        EMAIL ADDRESS CHANGES
        {"type": "upemail",
        "fired_at": "2009-03-26 22:15:09",
        "data[list_id]": "a6b5da1054",
        "data[new_id]": "51da8c3259",
        "data[new_email]": "api+new@mailchimp.com",
        "data[old_email]": "api+old@mailchimp.com"}

        NOTE: for an email change, BOTH profile and email updates are sent

        """
        list_id = request.data['data[list_id]']
        if list_id != settings.MAILCHIMP_LIST_ID:
            return Response(
                'Unexpected List ID',
                status=status.HTTP_400_BAD_REQUEST
            )

        action = request.data['type']

        if action == 'profile':
            email = request.data.get('data[email]')
            # delay for 5 secs in case we have email update at the same time
            # If we update the email before the profile update is processed,
            # we won't be able to retrieve the user
            time.sleep(5)
        elif action == 'upemail':
            email = request.data.get('data[old_email]')
        else:
            email = request.data.get('data[email]')

        logger.info('Mailchimp request: Email: {}, Action: {}'.format(email, action))

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                'User with email {} not found'.format(email),
                status=status.HTTP_400_BAD_REQUEST
            )

        if action == 'unsubscribe':
            self.group.user_set.remove(user)
            ActivityLog.objects.create(
                log='User {} {} ({}) unsubscribed from mailing list '
                    'via API request from MailChimp'.format(
                    user.first_name, user.last_name, user.username
                )
            )
        elif action == 'subscribe':
            self.group.user_set.add(user)
            ActivityLog.objects.create(
                log='User {} {} ({}) subscribed from mailing list '
                    'via API request from MailChimp'.format(
                    user.first_name, user.last_name, user.username
                )
            )
        elif action == 'profile':
            # update first and last name from Mailchimp
            first_name = request.data['data[merges][FNAME]']
            last_name = request.data['data[merges][LNAME]']
            changed = []
            if user.first_name != first_name:
                user.first_name = first_name
                user.save()
                changed.append('first name')
            if user.last_name != last_name:
                user.last_name = last_name
                user.save()
                changed.append('last name')
            if changed:
                ActivityLog.objects.create(
                    log='User profile updated for {} ({}); {} changed '
                        'via API request from MailChimp'.format(
                        user.username, user.email, ', '.join(changed)
                    )
                )
        elif action == 'upemail':
            # update email address for user
            new_email = request.data.get('data[new_email]')

            # check if an email address exists for this email
            try:
                existing_email = EmailAddress.objects.get(email=new_email)
            except EmailAddress.DoesNotExist:
                existing_email = None

            if existing_email:
                # email already exists for this user; make it the primary one
                if existing_email.user == user:
                    # remove other primary emails and set primary for this one
                    EmailAddress.objects.filter(user=user, primary=True).update(primary=False)
                    existing_email.primary = True
                    existing_email.save()
                else:
                    ActivityLog.objects.create(
                        log='Mailchimp API request to update email address '
                            'for {} (from {} to {}) failed; another user with '
                            'this email already exists'.format(
                            user.username, email, new_email
                        )
                    )
                    return Response(
                        'User with email {} already exists'.format(email),
                        status=status.HTTP_400_BAD_REQUEST
                    )
            else:
                # remove other primary emails
                EmailAddress.objects.filter(user=user, primary=True).update(primary=False)
                # create new email as primary
                EmailAddress.objects.create(
                    user=user, email=new_email, primary=True
                )
            # update the email on the User model to the new one
            user.email = new_email
            user.save()

            ActivityLog.objects.create(
                log='Email address updated for {} (from {} to {}) '
                    'via API request from MailChimp'.format(
                    user.username, email, new_email
                )
            )

        return Response('OK', status=status.HTTP_204_NO_CONTENT)
