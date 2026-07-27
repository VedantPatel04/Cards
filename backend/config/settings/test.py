from .base import *

DEBUG = True

SECRET_KEY = 'test-secret-key-not-for-production'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# Central test package (backend/tests/) — keep app tests.py stubs empty.
INSTALLED_APPS = [*INSTALLED_APPS, 'tests.apps.TestsConfig']
