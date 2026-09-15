from django.urls import include, path

urlpatterns = [
    path("api/", include("payments.urls")),
]

# Keep the {"error": {...}} format for errors outside DRF views (spec §7).
handler404 = "payments.exceptions.not_found_view"
handler500 = "payments.exceptions.server_error_view"
