from django.urls import path
from . import views

app_name = "games"

urlpatterns = [
    path("<slug:slug>/", views.game_analysis, name="analysis"),
]
