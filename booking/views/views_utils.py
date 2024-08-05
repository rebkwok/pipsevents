from django.urls import reverse
from django.shortcuts import HttpResponseRedirect
from django.utils import timezone

from accounts.models import DataPrivacyPolicy, has_active_disclaimer, has_active_data_privacy_agreement
from activitylog.models import ActivityLog
from booking.models import Block, UsedBlockVoucher, UsedEventVoucher


class DisclaimerRequiredMixin(object):

    def dispatch(self, request, *args, **kwargs):
        # check if the user has an active disclaimer
        if request.user.is_authenticated and not has_active_disclaimer(request.user):
            return HttpResponseRedirect(reverse('booking:disclaimer_required'))
        return super(DisclaimerRequiredMixin, self).dispatch(request, *args, **kwargs)


class DataPolicyAgreementRequiredMixin(object):

    def dispatch(self, request, *args, **kwargs):
        # check if the user has an active disclaimer
        if DataPrivacyPolicy.current_version() > 0 and request.user.is_authenticated \
                and not has_active_data_privacy_agreement(request.user):
            return HttpResponseRedirect(
                reverse('profile:data_privacy_review') + '?next=' + request.path
            )
        return super().dispatch(request, *args, **kwargs)


def validate_voucher_code(voucher, user, event=None):
    if event and not voucher.check_event_type(event.event_type):
        return 'Voucher code is not valid for this event/class type'
    elif voucher.has_expired:
        return 'Voucher code has expired'
    elif voucher.members_only and not user.has_membership():
        return 'Voucher code is only redeemable by members'
    elif voucher.max_vouchers and \
        UsedEventVoucher.objects.filter(voucher=voucher).count() >= \
            voucher.max_vouchers:
        return 'Voucher has limited number of total uses and has now expired'
    elif not voucher.activated:
        return 'Voucher has not been activated yet'
    elif not voucher.has_started:
        return 'Voucher code is not valid until {}'.format(
            voucher.start_date.strftime("%d %b %y")
        )
    elif voucher.max_per_user and UsedEventVoucher.objects.filter(
            voucher=voucher, user=user
    ).count() >= voucher.max_per_user:
        return 'Voucher code has already been used the maximum number ' \
               'of times ({})'.format(
                voucher.max_per_user
                )


def validate_block_voucher_code(voucher, user):
    if voucher.has_expired:
        return 'Voucher code has expired'
    elif voucher.members_only and not user.has_membership():
        return 'Voucher code is only redeemable by members'
    elif voucher.max_vouchers and \
        UsedBlockVoucher.objects.filter(voucher=voucher).count() >= \
            voucher.max_vouchers:
        return 'Voucher has limited number of uses and has now expired'
    elif not voucher.activated:
        return 'Voucher has not been activated yet'
    elif not voucher.has_started:
        return 'Voucher code is not valid until {}'.format(
            voucher.start_date.strftime("%d %b %y")
        )
    elif voucher.max_per_user and UsedBlockVoucher.objects.filter(
            voucher=voucher, user=user
    ).count() >= voucher.max_per_user:
        return 'Voucher code has already been used the maximum number ' \
               'of times ({})'.format(
                voucher.max_per_user
                )
    else:
        user_unpaid_blocks = [
            block for block in Block.objects.filter(user=user, paid=False)
            if not block.expired
        ]
        for block in user_unpaid_blocks:
            if voucher.check_block_type(block.block_type):
                return None
        return 'Code is not valid for any of your currently unpaid ' \
               'blocks'


def get_block_status(booking, request):
    blocks_used = None
    total_blocks = None
    if booking.block:
        blocks_used = booking.block.bookings_made()
        total_blocks = booking.block.block_type.size
        ActivityLog.objects.create(
            log='Block used for booking id {} (for {}). Block id {}, '
            'by user {}'.format(
                booking.id, booking.event, booking.block.id,
                request.user.username
            )
        )

    return blocks_used, total_blocks


