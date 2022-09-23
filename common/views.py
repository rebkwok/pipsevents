from django.http import HttpResponseForbidden
from django.template import loader


def csrf_failure(request, reason=""):
    context = {"back_url": request.META.get('HTTP_REFERER', "/")}
    template = loader.get_template("403_csrf.html")
    return HttpResponseForbidden(template.render(context))
