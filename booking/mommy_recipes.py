from datetime import timedelta
from django.contrib.auth.models import User
from django.utils import timezone

from model_mommy.recipe import Recipe, foreign_key

from booking.models import Event, Block, Booking


now = timezone.now()
past = now - timedelta(30)
future = now + timedelta(30)

user = Recipe(User,
              username="test_user",
              password="password",
              email="test_user@test.com")

# events; use defaults apart from dates
# override when using recipes, eg. mommy.make_recipe('future_event', cost=10)

future_EV = Recipe(Event,
                      date=future,
                      type='EV')

future_WS = Recipe(Event,
                   date=future,
                   type='WS')

future_PC = Recipe(Event,
                   date=future,
                   type='PC',
                   )

future_CL = Recipe(Event,
                   date=future,
                   type='CL',
                   )

# past event
past_event = Recipe(Event,
                    date=past,
                    type='WS',
                    advance_payment_required=True,
                    cost=10,
                    payment_due_date=past-timedelta(10)
                    )

block_5 = Recipe(Block,
                 user=foreign_key(user),
                 block_size='SM')

block_10 = Recipe(Block,
                  user=foreign_key(user),
                  block_size='LG')

booking = Recipe(Booking,
                 user=foreign_key(user),
                 )