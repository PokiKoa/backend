import os

from django.core.wsgi import get_wsgi_application

from poki_koa.env import load_env_file

load_env_file()
# Producción es el valor por defecto deliberado: si falta configuración, falla en vez de exponer DEBUG.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "poki_koa.settings.prod")

application = get_wsgi_application()
