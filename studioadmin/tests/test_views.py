from datetime import datetime, timedelta
from mock import Mock, patch
from model_mommy import mommy

from django.core.urlresolvers import reverse
from django.test import TestCase, RequestFactory
from django.test.client import Client
from django.contrib.messages.storage.fallback import FallbackStorage
from django.utils import timezone

from booking.models import Event, Booking, Block
from booking.tests.helpers import set_up_fb, _create_session, setup_view


class ConfirmPaymentViewTests(TestCase):

    pass


class ConfirmRefundViewTests(TestCase):

    pass


class EventRegisterListViewTests(TestCase):

    pass


class EventRegisterViewTests(TestCase):

    pass


class EventAdminListTests(TestCase):

    pass


class EventAdminUpdateViewTests(TestCase):

    pass


class EventAdminCreateViewTests(TestCase):

    pass


class TimetableAdminListView(TestCase):

    pass


class TimetableSessionUpdateView(TestCase):

    pass


class TimetableSessionCreateView(TestCase):

    pass


class UploadTimetableTests(TestCase):

    pass


class UserListViewTests(TestCase):

    pass


class BlockListViewTests(TestCase):

    pass


class EmailUsersTests(TestCase):

    pass


class UserBookingsViewTests(TestCase):

    pass
    # try to rebook cancelled


class UserBlocksViewTests(TestCase):

    pass
