import csv
import logging
from pathlib import Path
import os

from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils.encoding import smart_str

from accounts.models import OnlineDisclaimer, DisclaimerContent, NonRegisteredDisclaimer, ArchivedDisclaimer


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Export disclaimers data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            default=os.path.join(settings.LOG_FOLDER, 'disclaimers_bu.csv'),
            help='File path of output files; if not provided, '
                 'will be stored in log folder as "*_disclaimer_bu.csv"'
        )

    def handle(self, *args, **options):

        template_outputfile = Path(options.get('file'))
        outputfile_path = template_outputfile.resolve().parent
        template_outputfile_name = template_outputfile.name

        disclaimer_type_data = {
            "online": {
                "model": OnlineDisclaimer,
                "fields": [smart_str(u"User"), smart_str(u"Name (as stated on disclaimer)"), smart_str(u"Date Updated")],
                "attributes": ["user", "name", "date_updated"]
            },
            "non_registered": {
                "model": NonRegisteredDisclaimer,
                "fields": [smart_str(u"First Name"), smart_str(u"Last Name"), smart_str(u"Email"), smart_str(u"Event Date"), smart_str(u"User UUID")],
                "attributes": ["first_name", "last_name", "email", "event_date", "user_uuid"],
            },
            "archived": {
                "model": ArchivedDisclaimer,
                "fields": [smart_str(u"Name"), smart_str(u"Date Updated"), smart_str(u"Date Archived"), smart_str(u"Event Date")],
                "attributes": ["name", "date_updated", "date_archived", "event_date"]
            }
        }

        for disclaimer_type in disclaimer_type_data.keys():
            outputfile = outputfile_path / f"{disclaimer_type}_{template_outputfile_name}"
            with open(outputfile, 'wt') as out:
                wr = csv.writer(out)
                wr.writerow([
                    smart_str(u"ID"),
                    smart_str(u"Disclaimer version"),
                    *disclaimer_type_data[disclaimer_type]["fields"],
                    smart_str(u"Date"),
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
                    smart_str(u"Over 18 Confirmed"),
                ])
                disclaimer_model = disclaimer_type_data[disclaimer_type]["model"]
                for obj in disclaimer_model.objects.all():
                    disclaimer_content = DisclaimerContent.objects.get(version=obj.version)
                    wr.writerow([
                        smart_str(obj.pk),
                        smart_str(obj.version),
                        *[smart_str(getattr(obj, attrib)) for attrib in disclaimer_type_data[disclaimer_type]["attributes"]],
                        smart_str(obj.date.strftime('%Y-%m-%d %H:%M:%S:%f %z')),
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
                        smart_str(disclaimer_content.medical_treatment_terms),
                        smart_str('Yes' if obj.medical_treatment_permission else 'No'),
                        smart_str(disclaimer_content.disclaimer_terms),
                        smart_str('Yes' if obj.terms_accepted else 'No'),
                        smart_str(disclaimer_content.over_18_statement),
                        smart_str('Yes' if obj.age_over_18_confirmed else 'No'),
                    ])

            self.stdout.write(
                '{} disclaimer records written to {}'.format(
                    disclaimer_model.objects.count(), outputfile
                )
            )