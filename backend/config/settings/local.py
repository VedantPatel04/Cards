from .base import *

DEBUG = True

SECRET_KEY = 'local-dev-secret-key-not-for-production'

ALLOWED_HOSTS = ['localhost', '127.0.0.1']

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'cards_db',
        'USER': 'vedan',
        'PASSWORD': 'VPatel',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
