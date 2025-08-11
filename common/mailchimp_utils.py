import logging

from mailchimp3 import MailChimp
from mailchimp3.mailchimpclient import MailChimpError
from requests.exceptions import HTTPError

from django.conf import settings

logger = logging.getLogger(__name__)


def update_mailchimp(user, action, old_email=None):
    """
    Update mailchimp mailing list
    user: user to update
    action: str - subscribe/unsubscribe/update_profile/update_email
    old_email: if updating an email, this is the old email address
    """
    client = MailChimp(
        settings.MAILCHIMP_SECRET, settings.MAILCHIMP_USER, timeout=20
    )

    status_mapping = {
        'subscribe': 'subscribed',
        'unsubscribe': 'unsubscribed',
        'update_profile': 'subscribed' if user.subscribed() else 'unsubscribed',
        'update_email': 'subscribed' if user.subscribed() else 'unsubscribed',
    }

    if action == 'update_email':
        # Mailchimp API doesn't allow us to change a user's email address, so
        # we need to unsubscribe the old one and create/update the new one
        old_email_data = {
            'email_address': old_email,
             'status': 'unsubscribed',
             'status_if_new': 'unsubscribed',
             'merge_fields': {
                 'FNAME': user.first_name,
                 'LNAME': user.last_name
             }
        }
        if not update_members(client, [old_email_data]):
            return False

    new_userdata = {
        'email_address': user.email,
         'status': status_mapping[action],
         'status_if_new': status_mapping[action],
         'merge_fields': {
             'FNAME': user.first_name,
             'LNAME': user.last_name
         }
    }
    return update_members(client, [new_userdata])
    

def update_members(client: MailChimp, members: list):
    try:
        client.lists.update_members(
            list_id=settings.MAILCHIMP_LIST_ID,
            data={'members': members,  'update_existing': True}
        )
        return True
    except (HTTPError, MailChimpError) as e:
        logger.error('Error updating mailchimp: {}'.format(e))
        return False
