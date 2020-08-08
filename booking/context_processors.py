from django.conf import settings


def vat(request):
    return {
        "show_vat": settings.SHOW_VAT,
        "vat_number": settings.VAT_NUMBER,
    }
