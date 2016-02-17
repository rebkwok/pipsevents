import csv
from datetime import date, datetime
import logging
import os

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils.encoding import smart_str

from accounts.models import OnlineDisclaimer, PrintDisclaimer
from booking.email_helpers import send_support_email
from activitylog.models import ActivityLog


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Import disclaimer data from decrypted csv backup file'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            help='File path of input file'
        )

    def handle(self, *args, **options):

        inputfilepath = options.get('file')

        with open(inputfilepath, 'r') as file:
            reader = csv.reader(file)
            # rows = list(reader)

            for i, row in enumerate(reader):
                if i == 0:
                    pass
                else:
                    try:
                        user = User.objects.get(username=row[1])
                    except User.DoesNotExist:
                        self.stdout.write(
                            "Unknown user {} in backup data; data on "
                            "row {} not imported".format(row[1], i)
                        )
                        logger.info("Unknown user {} in backup data; data on "
                            "row {} not imported".format(row[1], i))

                    bu_date_updated = datetime.strptime(
                        row[3], '%Y-%m-%d %H:%M:%S:%f %z'
                    ) if row[3] else None

                    try:
                        disclaimer = OnlineDisclaimer.objects.get(user=user)
                    except OnlineDisclaimer.DoesNotExist:
                        disclaimer = None

                    if disclaimer:
                        if disclaimer.date == datetime.strptime(
                                row[2], '%Y-%m-%d %H:%M:%S:%f %z'
                        ) and disclaimer.date_updated == bu_date_updated:
                            dates_match = True
                        else:
                            dates_match = False
                        log_msg = "Disclaimer for {} already exists and has " \
                                  "not been overwritten with backup data. " \
                                  "Dates in db and back up {}match.".format(
                                        user.username,
                                        'DO NOT ' if not dates_match else ''
                                    )
                        self.stdout.write(log_msg)
                        logger.info(log_msg)

                    else:
                        OnlineDisclaimer.objects.create(
                            user=user,
                            date=datetime.strptime(
                                row[2], '%Y-%m-%d %H:%M:%S:%f %z'
                            ),
                            date_updated=bu_date_updated,
                            name=row[4],
                            dob=datetime.strptime(row[5], '%Y-%m-%d').date(),
                            address=row[6],
                            postcode=row[7],
                            home_phone=row[8],
                            mobile_phone=row[9],
                            emergency_contact1_name=row[10],
                            emergency_contact1_relationship=row[11],
                            emergency_contact1_phone=row[12],
                            emergency_contact2_name=row[13],
                            emergency_contact2_relationship=row[14],
                            emergency_contact2_phone=row[15],
                            medical_conditions=True
                            if row[16] == "Yes" else False,
                            medical_conditions_details=row[17],
                            joint_problems=True if row[18] == "Yes" else False,
                            joint_problems_details=row[19],
                            allergies=True if row[20] == "Yes" else False,
                            allergies_details=row[21],
                            medical_treatment_terms=row[22],
                            medical_treatment_permission=True
                            if row[23] == "Yes" else False,
                            disclaimer_terms=row[24],
                            terms_accepted=True
                            if row[25] == "Yes" else False,
                            over_18_statement=row[26],
                            age_over_18_confirmed=True
                            if row[27] == "Yes" else False,
                        )
                        log_msg = "Disclaimer for {} imported from " \
                                   "backup.".format(user.username)
                        self.stdout.write(log_msg)
                        logger.info(log_msg)
