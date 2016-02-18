import csv
import logging
import os

from django.core.management.base import BaseCommand
from django.conf import settings
from django.core.mail.message import EmailMessage
from django.utils.encoding import smart_str

from simplecrypt import encrypt

from accounts.models import OnlineDisclaimer

logger = logging.getLogger(__name__)

PASSWORD = os.environ.get('SIMPLECRYPT_PASSWORD')

class Command(BaseCommand):
    help = 'Encrypt and export disclaimers data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            default=os.path.join(settings.LOG_FOLDER, 'disclaimers.bu'),
            help='File path of output file; if not provided, '
                 'will be stored in log folder as "disclaimers.bu"'
        )

    def handle(self, *args, **options):
        outputfile = options.get('file')

        output_text = []

        output_text.append(
            '@@@@@'.join(
                [
                    smart_str(u"ID"),
                    smart_str(u"User"),
                    smart_str(u"Date"),
                    smart_str(u"Date Updated"),
                    smart_str(u"Name (as stated on disclaimer)"),
                    smart_str(u"DOB"),
                    smart_str(u"Address"),
                    smart_str(u"Postcode"),
                    smart_str(u"Home Phone"),
                    smart_str(u"Mobile Phone"),
                    smart_str(u"Emergency Contact 1: Name"),
                    smart_str(u"Emergency Contact 1: Relationship"),
                    smart_str(u"Emergency Contact 1: Phone"),
                    smart_str(u"Emergency Contact 2: Name"),
                    smart_str(u"Emergency Contact 2: Relationship"),
                    smart_str(u"Emergency Contact 2: Phone"),
                    smart_str(u"Medical Conditions"),
                    smart_str(u"Medical Conditions Details"),
                    smart_str(u"Joint Problems"),
                    smart_str(u"Joint Problems Details"),
                    smart_str(u"Allergies"),
                    smart_str(u"Allergies Details"),
                    smart_str(u"Medical Treatment Terms"),
                    smart_str(u"Medical Treatment Accepted"),
                    smart_str(u"Disclaimer Terms"),
                    smart_str(u"Disclaimer Terms Accepted"),
                    smart_str(u"Over 18 Statement"),
                    smart_str(u"Over 18 Confirmed")
                ]
            )
        )

        for obj in OnlineDisclaimer.objects.all():
            output_text.append(
                '@@@@@'.join(
                    [
                        smart_str(obj.pk),
                        smart_str(obj.user),
                        smart_str(obj.date.strftime('%Y-%m-%d %H:%M:%S:%f %z')),
                        smart_str(obj.date_updated.strftime(
                            '%Y-%m-%d %H:%M:%S:%f %z') if obj.date_updated else ''
                        ),
                        smart_str(obj.name),
                        smart_str(obj.dob.strftime('%Y-%m-%d')),
                        smart_str(obj.address),
                        smart_str(obj.postcode),
                        smart_str(obj.home_phone),
                        smart_str(obj.mobile_phone),
                        smart_str(obj.emergency_contact1_name),
                        smart_str(obj.emergency_contact1_relationship),
                        smart_str(obj.emergency_contact1_phone),
                        smart_str(obj.emergency_contact2_name),
                        smart_str(obj.emergency_contact2_relationship),
                        smart_str(obj.emergency_contact2_phone),
                        smart_str('Yes' if obj.medical_conditions else 'No'),
                        smart_str(obj.medical_conditions_details),
                        smart_str('Yes' if obj.joint_problems else 'No'),
                        smart_str(obj.joint_problems_details),
                        smart_str('Yes' if obj.allergies else 'No'),
                        smart_str(obj.allergies_details),
                        smart_str(obj.medical_treatment_terms),
                        smart_str('Yes' if obj.medical_treatment_permission else 'No'),
                        smart_str(obj.disclaimer_terms),
                        smart_str('Yes' if obj.terms_accepted else 'No'),
                        smart_str(obj.over_18_statement),
                        smart_str('Yes' if obj.age_over_18_confirmed else 'No'),
                    ]
                )
            )

        output_str = '&&&&&'.join(output_text)

        with open(outputfile, 'wb') as out:
            out.write(encrypt(PASSWORD, output_str))

        with open(outputfile, 'rb') as file:
            try:
                msg = EmailMessage(
                    '{} disclaimer backup'.format(
                        settings.ACCOUNT_EMAIL_SUBJECT_PREFIX),
                    'Encrypted disclaimer back up file attached',
                    settings.DEFAULT_FROM_EMAIL,
                    to=[settings.SUPPORT_EMAIL],
                    attachments=[(outputfile, file.read(), 'bytes/bytes')]
                )
                msg.send(fail_silently=False)
            except:
                pass

        self.stdout.write(
            '{} disclaimer records encrypted and written to {}'.format(
                OnlineDisclaimer.objects.count(), outputfile
            )
        )

        logger.info(
            '{} disclaimer records encrypted and backed up'.format(
                OnlineDisclaimer.objects.count()
            )
        )
