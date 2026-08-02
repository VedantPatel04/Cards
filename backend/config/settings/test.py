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


LLM_ENABLED = False
LLM_API_KEY = ''

# Point at a scratch Redis database so a developer machine with a real Redis
# never has its warm merchant cache read or overwritten by the suite.
REDIS_URL = 'redis://localhost:6379/15'
