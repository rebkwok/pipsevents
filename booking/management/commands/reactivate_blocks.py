import csv
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from django.conf import settings
from django.core.mail.message import EmailMultiAlternatives
from django.template.loader import get_template
from django.core.management.base import BaseCommand, CommandError

from booking.models import Block, BlockType, EventType
from activitylog.models import ActivityLog


def get_reactivated_count(user):
    return sum([
        bl.block_type.size for bl in
        user.blocks.filter(block_type__identifier="Reactivated") if
        bl.active_block()
    ])


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('file', nargs=1)
        parser.add_argument("--reactivate", action="store_true", help="Reactivate blocks")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--reactivation-date", type=str, help="Reactivation date")

    def handle(self, *args, **options):
        filepath = options["file"][0]
        reactivate = options["reactivate"]
        dry_run = options["dry_run"]
        reactivation_date = datetime.strptime(options["reactivation_date"], "%d-%b-%Y") if options["reactivation_date"] else None
        if reactivation_date:
            reactivation_date = reactivation_date.replace(tzinfo=dt_timezone.utc)
        if reactivate and reactivation_date is None:
            raise Exception("Reactivating blocks: reactivation date is required")
        with open(filepath, "r") as infile:
            csvreader = csv.DictReader(infile)
            user_credits = {}

            for row in csvreader:
                if row["block_id"]:
                    obj = Block.objects.get(id=int(row["block_id"]))
                    user = obj.user
                    user_credits.setdefault(user, {"total_due": 0, "blocks": []})
                    credit_due = int(row["Credit still due"])
                    user_credits[user]["total_due"] += credit_due
                    original_expiry = datetime.strptime(row["expiry date"], "%d-%b-%Y")
                    days_left_on_block = (original_expiry - datetime(2020, 3, 17)).days

                    block = {
                        "obj": obj,
                        "valid_for": obj.block_type.event_type.subtype,
                        "block_id": row["block_id"],
                        "original_start_date": obj.start_date,
                        "original_expiry": original_expiry,
                        "total_credits": obj.block_type.size,
                        "credits_left": row["bookings left on block"],
                        "transfer_block": row['transferred booking_id'],
                        "waived": row["Waived"],
                        "refunded": row["Refunded"],
                        "converted_to_online": row['Convert to online credit'],
                        "converted_to_voucher": row['Converted to vouchers'],
                        "used_for_raffle_or_merch": row['Used for raffle/merch'],
                        "used_for_private": row['Used for private'],
                        "used_for_credit_class": row['Used for credit classes'],
                        "used_for_individual_training": row['Used for individual training classes'],
                        "blocks_reactivated": row['Blocks reactived'],
                        "returned_from_cancelled_credit_classes": row['Returned from cancelled credit classes 30 Oct 2020'],
                        "credit_due": credit_due,
                        "days_left_on_block": days_left_on_block,
                        "weeks_left": days_left_on_block // 7,
                        "days_left": days_left_on_block % 7
                    }
                    if reactivation_date:
                        block["new_expiry_date"] = reactivation_date + timedelta(days=days_left_on_block)
                    user_credits[user]["blocks"].append(block)

        users_with_credit_due = {k: v for k, v in user_credits.items() if v["total_due"] > 0}

        used_for_map = {
            "waived": "Waived",
            "refunded": "Refunded",
            "converted_to_online": 'Converted to credit for online classes',
            "converted_to_voucher": "Converted to vouchers",
            "used_for_raffle_or_merch": 'Used for raffle/merchandise',
            "used_for_private": 'Used for private class',
            "used_for_credit_class": 'Used for credit classes',
            "used_for_individual_training": 'Used for individual training classes',
            "blocks_reactivated": 'Pole practice blocks already reactived',
        }
        for user, user_data in users_with_credit_due.items():
            # check their blocks haven't already been activated
            reactivated_count = get_reactivated_count(user)
            total_due = user_data["total_due"]
            if reactivated_count >= total_due:
                self.stdout.write(f"All blocks already activated for {user.username}, skipping")
                continue

            blocks = sorted(
                user_data["blocks"], key=lambda x: (x["credit_due"], -x["days_left_on_block"]),
                reverse=True
            )
            blocks = {i: block for i, block in enumerate(blocks, start=1)}

            user_report = {
                "total_due": total_due,
                "reactivation_date": reactivation_date,
                "blocks": {}
            }
            user_blocks_report = {}
            for i, block in blocks.items():
                user_blocks_report[i] = {
                    "valid_for": block['valid_for'],
                    "weeks_left": block['weeks_left'],
                    "days_left": block['days_left'],
                    "original_start_date": block['original_start_date'],
                    "original_expiry": block['original_expiry'],
                    "total_credits": block["total_credits"],
                    "credits_left": block["credits_left"],
                    "new_expiry_date": block.get("new_expiry_date"),
                    "used_for": {},
                    "credit_due": block["credit_due"],
                    "reporting_action": "REACTIVATED" if reactivate else "STILL DUE"
                }
                for key in used_for_map.keys():
                    if block[key]:
                        user_blocks_report[i]["used_for"][used_for_map[key]] = block[key]
                    if block["returned_from_cancelled_credit_classes"]:
                        user_blocks_report[i]["used_for"]["Returned from cancelled credit classes (second lockdown)"]: block['returned_from_cancelled_credit_classes']
            user_report["blocks"] = user_blocks_report

            # CREATE BLOCKS FIRST
            for block_to_reactivate in user_report["blocks"].values():
                if block_to_reactivate['credit_due'] and reactivate:
                    event_type = EventType.objects.get(event_type="CL",
                                                       subtype="Pole level class")
                    if dry_run:
                        block_type = BlockType.objects.filter(
                            event_type=event_type,
                            identifier="Reactivated",
                            size=block_to_reactivate['credit_due'],
                            duration=1,
                            active=False,
                            cost=0
                        )
                        if not block_type.exists():
                            self.stdout.write(
                                f"Would create reactivated blocktype ({block_to_reactivate['credit_due']})")
                        self.stdout.write(
                            f"Would create reactivated block for {user.username}; ({block_to_reactivate['credit_due']}, "
                            f"expires {block_to_reactivate['new_expiry_date']}"
                        )

                    else:
                        exp = block_to_reactivate["new_expiry_date"].replace(tzinfo=dt_timezone.utc)
                        block_type, _ = BlockType.objects.get_or_create(
                            event_type=event_type,
                            identifier="Reactivated",
                            size=block_to_reactivate['credit_due'],
                            duration=1,
                            active=False,
                            cost=0
                        )
                        new_block = Block.objects.create(
                            block_type=block_type, user=user, paid=True,
                            start_date=reactivation_date,
                            extended_expiry_date=exp,
                        )
                        assert new_block.expiry_date.date() == new_block.extended_expiry_date.date() == \
                               block_to_reactivate["new_expiry_date"].date()
                        msg = f"Reactivated block {new_block.id} ({new_block.block_type.size}) for user {user.username}"
                        self.stdout.write(msg)
                        ActivityLog.objects.create(log=msg)
            reactivated_count = sum([
                bl.block_type.size for bl in
                user.blocks.filter(block_type__identifier="Reactivated") if
                bl.active_block()
            ])
            if reactivate and not dry_run:
                assert reactivated_count == user_report["total_due"], (user.username, reactivated_count, user_report["total_due"])
            else:
                assert reactivated_count == 0

            # PRINT DATA / SEND EMAILS
            self.stdout.write("===========")
            self.stdout.write(f"{user.username} - TOTAL CREDIT DUE: {user_report['total_due']}")
            self.stdout.write(f"Block breakdown:")
            for i, user_block in user_report["blocks"].items():
                self.stdout.write(f"{i}. Time left after reactivation: {user_block['weeks_left']} weeks {user_block['days_left']} days")
                self.stdout.write(f"Valid for: {user_block['valid_for']}")
                if user_report["reactivation_date"]:
                    self.stdout.write(f"Blocks reactivated on {user_report['reactivation_date'].strftime('%d-%b-%Y')}")
                    self.stdout.write(f"Expiry: {user_block['new_expiry_date'].strftime('%d-%b-%Y')}")
                self.stdout.write(f"Original start date: {user_block['original_start_date'].strftime('%d-%b-%Y')}")
                self.stdout.write(f"Original expiry date: {user_block['original_expiry'].strftime('%d-%b-%Y')}")
                self.stdout.write(f"Total credits on block: {user_block['total_credits']}"),
                self.stdout.write(f"Credits left on block on 17 Mar 2020: {user_block['credits_left']}")
                for reason, count in user_block["used_for"].items():
                    self.stdout.write(f"{reason}: {count}")
                self.stdout.write(f"CREDIT {user_block['reporting_action']}: {user_block['credit_due']}")
            if not dry_run:
                context = {
                    "user": user,
                    "total_due": user_report["total_due"],
                    "reactivation_date": reactivation_date,
                    "blocks": user_report["blocks"],
                    "report_type": "reactivation" if reactivate else "notification"
                }
                msg = EmailMultiAlternatives(
                    f'{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Credit blocks reactivation',
                    get_template('booking/email/reactivated_credit.txt').render(context),
                    settings.DEFAULT_FROM_EMAIL,
                    to=[user.email],
                )
                msg.attach_alternative(
                    get_template('booking/email/reactivated_credit.html').render(context),
                    "text/html"
                )
                msg.send(fail_silently=False)
