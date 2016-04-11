"""
Read data from CSV file and email users to confirm account info
CSV in format: (allows for 2 or 3 duplicated accounts)
Name,Username1,Email 1,Used?,Verified?,Disclaimer?,FB Account?,username2,Email 2,Used?,Verified?,Disclaimer?,FB Account?,Username3,Email3,Used?,Verified?,Disclaimer?,FB Account?
John Smith,jsmith,j.smith@email.com,Y,Y,Y,N,jsmith1,j.smith1@email.com,Y,Y,N,N,jsmith2,j.smith2@email.com,N,Y,N,Y
"""
import csv

from django.core.management.base import BaseCommand
from django.conf import settings
from django.core.mail import send_mail, EmailMessage
from django.template.loader import get_template

from booking.email_helpers import send_support_email


class Command(BaseCommand):
    help = 'Email duplicate users from csv file'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            help='File path of input file'
        )

    def handle(self, *args, **options):

        inputfilepath = options.get('file')

        with open(inputfilepath, 'r') as file:
            reader = csv.reader(file)
            fail_count = 0
            for i, row in enumerate(reader):
                if i == 0:  # header row
                    pass
                else:
                    name = row[0]
                    first_name = name.split()[0]
                    username1 = row[1]
                    email1 = row[2]
                    email1_used = True if row[3].lower() == 'y' else False
                    email1_is_fb = True if row[6].lower() == 'y' else False
                    username2 = row[7]
                    email2 = row[8]
                    email2_used = True if row[9].lower() == 'y' else False
                    email2_is_fb = True if row[12].lower() == 'y' else False
                    username3 = row[13] if row[13] else None
                    email3 = row[14] if row[14] else None
                    email3_used = True if row[15].lower() == 'y' else False
                    email3_is_fb = True if row[18].lower() == 'y' else False

                    emails = [
                        em for em in [email1, email2, email3]
                        if em is not None
                        ]

                    email_used = None
                    num_used = sum([email1_used, email2_used, email3_used])
                    if num_used == 1:  # only include email_used if one
                        # and only one used
                        email_used = [
                            em[0] for em in [
                                (email1, email1_used),
                                (email2, email2_used),
                                (email3, email3_used)
                            ] if em[1] is True
                            ][0]

                    ctx = {
                        'first_name': first_name,
                        'username1': username1,
                        'email1': email1,
                        'email1_is_fb': email1_is_fb,
                        'username2': username2,
                        'email2': email2,
                        'email2_is_fb': email2_is_fb,
                        'username3': username3,
                        'email3': email3,
                        'email3_is_fb': email3_is_fb,
                        'email_count': 3 if username3 else 2,
                        'more_than_1_used': True if num_used > 1 else False,
                        'email_used': email_used
                    }

                    # send email
                    try:
                        email_msg = EmailMessage(
                            '{} Duplicate accounts on booking system'.format(
                                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,
                            ),
                            get_template(
                                'account/email/duplicate_account.txt'
                            ).render(ctx),
                            from_email=settings.DEFAULT_FROM_EMAIL,
                            to=emails,
                            reply_to=[settings.SUPPORT_EMAIL]
                            )
                        email_msg.send()
                    except Exception as e:
                        fail_count += 1
                        # send mail to tech support with Exception
                        send_support_email(
                            e, __name__, "Duplicate account emails"
                        )

            self.stdout.write(
                'Emails sent for {} accounts'.format(i - fail_count)
            )
            self.stdout.write('{} failed sends'.format(fail_count))

