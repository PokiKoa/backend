from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """
    Configuración principal de la aplicación de cuentas.
    Establece el tipo de clave primaria por defecto y el nombre
    legible ('Cuentas y Roles') para el panel de administración.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
    verbose_name = "Cuentas y Roles"
