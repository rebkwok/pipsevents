from django.conf import settings


def booking(request):
    return {
        "show_vat": settings.SHOW_VAT,
        "vat_number": settings.VAT_NUMBER,
        "studio_email": settings.DEFAULT_STUDIO_EMAIL,
    }
