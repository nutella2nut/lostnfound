"""Audit middleware: records every page visit and form submission."""
from .audit import record_access
from .models import Item, StudentLostItem
from .site_settings import get_site_settings

# Asset requests and the scheduled mailbox poll aren't user actions.
SKIP_PREFIXES = ("/static/", "/media/", "/favicon.ico", "/robots.txt", "/internal/")


class AuditLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Loaded once per request; the site_settings context processor reuses it.
        request.site_settings = get_site_settings()
        response = self.get_response(request)
        if not request.path.startswith(SKIP_PREFIXES) and request.site_settings.log_page_views:
            self._record(request, response)
        return response

    def _record(self, request, response):
        item = student_item = None
        match = getattr(request, "resolver_match", None)
        if match and "pk" in match.kwargs:
            # Link item clicks to the item they opened.
            if match.url_name == "item_detail":
                item = Item.objects.filter(pk=match.kwargs["pk"]).first()
            elif match.url_name == "student_lost_item_detail":
                student_item = StudentLostItem.objects.filter(pk=match.kwargs["pk"]).first()

        details = {"status_code": response.status_code}
        if request.GET:
            details["query"] = request.GET.urlencode()[:1000]
        if match:
            details["view"] = match.view_name

        record_access(
            request,
            "PAGE_VIEW" if request.method in ("GET", "HEAD") else "FORM_SUBMIT",
            item=item, student_item=student_item, details=details,
        )
