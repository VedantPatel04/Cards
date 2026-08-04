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

# Point at a scratch Redis database so a developer machine with the real Redis instance never has its merchant cache read or overwritten.
REDIS_URL = 'redis://localhost:6379/15'
