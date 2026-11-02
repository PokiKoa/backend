"""Punto de entrada WSGI para el proyecto Poki Koa.

WSGI (Web Server Gateway Interface) es el estándar que permite a servidores
web como Gunicorn o uWSGI comunicarse con la aplicación Django en producción.

Para desarrollo local se usa el servidor incluido de Django (`runserver`).
En producción se recomienda usar Gunicorn apuntando a este módulo:

    gunicorn poki_koa.wsgi:application
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "poki_koa.settings")

application = get_wsgi_application()
