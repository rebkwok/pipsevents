from django.contrib import admin
from django.urls import reverse
from django.utils.safestring import mark_safe 

from booking.models import Booking, Block
from stripe_payments.models import Invoice, StripePaymentIntent, Seller

admin.site.register(Seller)
admin.site.register(StripePaymentIntent)
admin.site.register(Invoice)
