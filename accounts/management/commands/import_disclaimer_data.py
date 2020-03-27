import csv
from datetime import datetime
from decimal import Decimal
import logging

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

from accounts.models import OnlineDisclaimer



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
            reader = csv.DictReader(file)
            # rows = list(reader)

            for i, row in enumerate(reader):
                if i == 0:
                    pass
                else:
                    try:
                        user = User.objects.get(username=row["User"])
                    except User.DoesNotExist:
                        self.stdout.write(
                            "Unknown user {} in backup data; data on "
                            "row {} not imported".format(row["User"], i)
                        )
                        logger.warning("Unknown user {} in backup data; data on "
                            "row {} not imported".format(row["User"], i))
                        continue

                    bu_date_updated = datetime.strptime(
                        row["Date Updated"], '%Y-%m-%d %H:%M:%S:%f %z'
                    ) if row["Date Updated"] else None

                    try:
                        disclaimer = OnlineDisclaimer.objects.get(user=user, version=Decimal(row["Disclaimer Version"]))
                    except OnlineDisclaimer.DoesNotExist:
                        disclaimer = None

                    if disclaimer:
                        if disclaimer.date == datetime.strptime(
                                row["Date"], '%Y-%m-%d %H:%M:%S:%f %z'
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
                        logger.warning(log_msg)

                    else:
                        OnlineDisclaimer.objects.create(
                            user=user,
                            date=datetime.strptime(
                                row["Date"], '%Y-%m-%d %H:%M:%S:%f %z'
                            ),
                            date_updated=bu_date_updated,
                            name=row["Name (as stated on disclaimer)"],
                            dob=datetime.strptime(row["DOB"], '%Y-%m-%d').date(),
                            address=row["Address"],
                            postcode=row["Postcode"],
                            home_phone=row["Home Phone"],
                            mobile_phone=row["Mobile Phone"],
                            emergency_contact1_name=row["Emergency Contact 1: Name"],
                            emergency_contact1_relationship=row["Emergency Contact 1: Relationship"],
                            emergency_contact1_phone=row["Emergency Contact 1: Phone"],
                            emergency_contact2_name=row["Emergency Contact 2: Name"],
                            emergency_contact2_relationship=row["Emergency Contact 2: Relationship"],
                            emergency_contact2_phone=row["Emergency Contact 2: Phone"],
                            medical_conditions=True if row["Medical Conditions"] == "Yes" else False,
                            medical_conditions_details=row["Medical Conditions Details"],
                            joint_problems=True if row["Joint Problems"] == "Yes" else False,
                            joint_problems_details=row["Joint Problems Details"],
                            allergies=True if row["Allergies"] == "Yes" else False,
                            allergies_details=row["Allergies Details"],
                            medical_treatment_permission=True if row["Medical Treatment Accepted"] == "Yes" else False,
                            terms_accepted=True if row["Disclaimer Terms Accepted"] == "Yes" else False,
                            age_over_18_confirmed=True if row["Over 18 Confirmed"] == "Yes" else False,
                            version=Decimal(row["Disclaimer Version"])
                        )
                        log_msg = "Disclaimer for {} imported from " \
                                   "backup.".format(user.username)
                        self.stdout.write(log_msg)
                        logger.info(log_msg)
