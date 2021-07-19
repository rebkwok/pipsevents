from django.conf import settings
from django.utils import timezone

from booking.models import Event

def booking(request):
    return {
        "show_vat": settings.SHOW_VAT,
        "vat_number": settings.VAT_NUMBER,
        "studio_email": settings.DEFAULT_STUDIO_EMAIL,
        "location_count": Event.objects.filter(date__gte=timezone.now()).order_by().distinct("location").count()
    }
