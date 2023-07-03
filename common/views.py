from django.http import HttpResponseForbidden
from django.template import loader


def csrf_failure(request, reason=""):  # pragma: no cover
    context = {"back_url": request.META.get('HTTP_REFERER', "/")}
    template = loader.get_template("403_csrf.html")
    return HttpResponseForbidden(template.render(context))


def _set_pagination_context(context):
    page = context['page_obj']
    context['paginator_range'] = page.paginator.get_elided_page_range(page.number)
