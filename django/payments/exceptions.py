"""Every API error uses {"error": {"code": ..., "message": ...}} (spec §7)."""

from django.http import Http404, JsonResponse
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler


def error_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


class ApiError(exceptions.APIException):
    """Raise from a view to return a spec error code with a given HTTP status."""

    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(detail=message, code=code)
        self.status_code = status_code
        self.error_code = code
        self.message = message


_DRF_ERROR_CODES = (
    (exceptions.ParseError, "invalid_json"),
    (exceptions.UnsupportedMediaType, "unsupported_media_type"),
    (exceptions.MethodNotAllowed, "method_not_allowed"),
    (exceptions.NotAcceptable, "not_acceptable"),
    (exceptions.NotFound, "not_found"),
    (Http404, "not_found"),
    (exceptions.ValidationError, "invalid_request"),
)


def api_exception_handler(exc, context):
    if isinstance(exc, ApiError):
        return Response(error_body(exc.error_code, exc.message), status=exc.status_code)

    response = exception_handler(exc, context)
    if response is None:
        # Unhandled exception: Django turns it into a 500 via server_error_view.
        return None

    code = next((code for cls, code in _DRF_ERROR_CODES if isinstance(exc, cls)), "api_error")
    detail = response.data.get("detail") if isinstance(response.data, dict) else None
    response.data = error_body(code, str(detail) if detail else "Request failed.")
    return response


# Django-level handlers for errors outside DRF views (active when DEBUG=False).
def not_found_view(request, exception):
    return JsonResponse(error_body("not_found", "Not found."), status=404)


def server_error_view(request):
    return JsonResponse(error_body("server_error", "Internal server error."), status=500)
