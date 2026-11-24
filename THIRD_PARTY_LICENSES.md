# Licencias de terceros (backend)

Dependencias directas de ejecución, con las versiones fijadas en `uv.lock` (v2.1.0). Todas son licencias permisivas: al redistribuir el software hay que **conservar el aviso de copyright y el texto de la licencia** de cada una (BSD, MIT, Apache-2.0). Los textos completos están en cada paquete instalado (`.venv/lib/python3.12/site-packages/<paquete>*/licenses`).

| Paquete | Versión | Licencia | Proyecto |
|---|---|---|---|
| channels | 4.3.2 | BSD License | http://github.com/django/channels |
| channels-redis | 4.3.0 | BSD | http://github.com/django/channels_redis/ |
| django | 6.1 | BSD-3-Clause | https://www.djangoproject.com/ |
| django-cors-headers | 4.9.0 | MIT | https://github.com/adamchainz/django-cors-headers |
| django-environ | 0.14.0 | MIT | https://django-environ.readthedocs.org |
| django-filter | 26.2 | BSD License | https://github.com/carltongibson/django-filter/tree/main |
| djangorestframework | 3.18.0 | BSD-3-Clause | https://www.django-rest-framework.org |
| djangorestframework-simplejwt | 5.5.1 | MIT License | https://github.com/jazzband/djangorestframework-simplejwt |
| drf-spectacular | 0.30.0 | BSD-3-Clause | https://github.com/tfranzel/drf-spectacular |
| psycopg | 3.3.6 | LGPL-3.0-only | https://psycopg.org/ |
| uvicorn | 0.54.0 | BSD-3-Clause | https://uvicorn.dev/ |
| whitenoise | 6.12.0 | MIT | https://github.com/evansd/whitenoise |

Para regenerar la lista completa (incluidas las transitivas):

```bash
uv run --no-project --with pip-licenses --with-requirements <(uv export --no-dev --no-hashes) pip-licenses --format=markdown --with-urls
```

## Nota sobre `psycopg` (LGPL-3.0)

`psycopg` es la única dependencia directa con licencia copyleft débil. Se usa como librería externa sin modificarla (enlace dinámico mediante `import`), por lo que el código propio no queda sujeto a la LGPL. Obligaciones al redistribuir: incluir el texto de la LGPL-3.0 y el aviso de copyright, indicar dónde obtener su código fuente (<https://github.com/psycopg/psycopg>) y no impedir que el usuario la reemplace por otra versión (en este proyecto se instala desde `uv.lock`).
