"""Paginación por defecto de la API."""

from rest_framework.pagination import PageNumberPagination


class StandardResultsSetPagination(PageNumberPagination):
    """Paginación por páginas: 20 elementos por defecto, ``page_size`` configurable hasta 100."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
