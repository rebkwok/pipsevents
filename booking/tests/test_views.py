from django.test import TestCase
from mock import patch
from model_mommy import mommy


"""
Block tests (for forms/views?)

If a block has 5 or 10 bookings, no more bookings can be made
If a user has an active block, they can't buy a new block
Can user book against a block before block payment confirmed?  Maybe allow
booking for 1 week after block start date, then prevent it if payment not
received

Test trying to book with a block for an event that is not a pole class

"""