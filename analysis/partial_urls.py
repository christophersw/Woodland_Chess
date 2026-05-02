from django.urls import path
from . import views

urlpatterns = [
    path("analysis/queue/", views.queue_partial, name="analysis-queue-partial"),
]
