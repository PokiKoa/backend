from typing import ClassVar

from django.db import connection
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .dashboard import get_clinical_dashboard_stats


def root_dashboard_view(request: HttpRequest) -> HttpResponse:
    context = get_clinical_dashboard_stats()
    return render(request, "poki_koa/home.html", context)


class HealthCheckView(APIView):
    authentication_classes: ClassVar[list] = []
    permission_classes: ClassVar[list] = [AllowAny]

    @extend_schema(
        summary="Verifica el estado operativo del servicio y la base de datos",
        responses={
            200: inline_serializer(
                name="HealthCheckResponse",
                fields={
                    "status": serializers.CharField(),
                    "version": serializers.CharField(),
                    "database": serializers.CharField(),
                },
            )
        },
    )
    def get(self, request: Request) -> Response:
        connection.ensure_connection()
        return Response(
            {
                "status": "ok",
                "version": "2.0.0",
                "database": "ok",
            },
            status=status.HTTP_200_OK,
        )
