import os
import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

# Only initialize once
if not django.apps.apps.ready:
    django.setup()
