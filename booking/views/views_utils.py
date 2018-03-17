from operator import itemgetter

from django.urls import reverse
from django.shortcuts import HttpResponseRedirect

from accounts.models import DataProtectionPolicy
from accounts.utils import has_active_disclaimer, has_active_data_protection_agreement
from activitylog.models import ActivityLog
from booking.models import Block, UsedBlockVoucher, UsedEventVoucher

class DisclaimerRequiredMixin(object):

    def dispatch(self, request, *args, **kwargs):
        # check if the user has an active disclaimer
        if request.user.is_authenticated and not has_active_disclaimer(request.user):
            return HttpResponseRedirect(reverse('booking:disclaimer_required'))
        return super(DisclaimerRequiredMixin, self).dispatch(request, *args, **kwargs)


class DataProtectionRequiredMixin(object):

    def dispatch(self, request, *args, **kwargs):
        # check if the user has an active disclaimer
        if DataProtectionPolicy.current_version() > 0 and request.user.is_authenticated \
                and not has_active_data_protection_agreement(request.user):
            return HttpResponseRedirect(
                reverse('profile:data_protection_review') + '?next=' + self.request.path
            )
        return super(DataProtectionRequiredMixin, self).dispatch(request, *args, **kwargs)


def validate_voucher_code(voucher, user, event=None):
    if event and not voucher.check_event_type(event.event_type):
        return 'Voucher code is not valid for this event/class type'
    elif voucher.has_expired:
        return 'Voucher code has expired'
    elif voucher.max_vouchers and \
        UsedEventVoucher.objects.filter(voucher=voucher).count() >= \
            voucher.max_vouchers:
        return 'Voucher has limited number of total uses and has now expired'
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
    elif voucher.max_vouchers and \
        UsedBlockVoucher.objects.filter(voucher=voucher).count() >= \
            voucher.max_vouchers:
        return 'Voucher has limited number of uses and has now expired'
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


def _get_block_status(booking, request):
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


def _get_active_user_block(user, booking):
    """
    return the active block for this booking with the soonest expiry date
    """
    blocks = user.blocks.all()
    active_blocks = [
        (block, block.expiry_date)
        for block in blocks if block.active_block()
        and block.block_type.event_type == booking.event.event_type
    ]
    # use the block with the soonest expiry date
    if active_blocks:
        return min(active_blocks, key=itemgetter(1))[0]
    else:
        return None