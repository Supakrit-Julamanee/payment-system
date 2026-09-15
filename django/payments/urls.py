from django.urls import path

from . import views

# Every path ends with "/" (spec §7).
urlpatterns = [
    path("orders/", views.OrderCreateView.as_view(), name="order-create"),
    path("orders/<str:order_id>/", views.OrderDetailView.as_view(), name="order-detail"),
    path("orders/<str:order_id>/pay/", views.OrderPayView.as_view(), name="order-pay"),
    path("webhooks/omise/", views.OmiseWebhookView.as_view(), name="omise-webhook"),
]
