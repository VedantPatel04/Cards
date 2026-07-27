from django.apps import AppConfig


class TestsConfig(AppConfig):
    """Empty Django app so DiscoverRunner finds backend/tests/ on manage.py test."""

    name = "tests"
    label = "backend_tests"
    verbose_name = "Backend Tests"
