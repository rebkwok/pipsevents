from django.conf import settings
from django.utils import timezone

from booking.models import Event

def booking(request):
    return {
        "show_vat": settings.SHOW_VAT,
        "vat_number": settings.VAT_NUMBER,
        "studio_email": settings.DEFAULT_STUDIO_EMAIL,
        "location_count": Event.objects.filter(date__gte=timezone.now()).order_by().distinct("location").count(),
        "payment_method": settings.PAYMENT_METHOD, 
        # only show room hires if available to book
        "room_hires_exist": Event.objects.filter(event_type__event_type="RH", date__gt=timezone.now(), visible_on_site=True).exists(),
        # hide online tutorials
        "online_tutorials_exist": False
    }
