import datetime

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone

STATUS_MAP = {"pending": "active", "administered": "completed", "cancelled": "cancelled"}


def migrate_single_dose_prescriptions(apps, schema_editor):
    Prescription = apps.get_model("medications", "Prescription")
    MedicationAdministration = apps.get_model("medications", "MedicationAdministration")
    tz = timezone.get_default_timezone()

    for prescription in Prescription.objects.all().iterator():
        local_day = timezone.localtime(prescription.created_at, tz).date()
        prescription.starts_at = timezone.make_aware(
            datetime.datetime.combine(local_day, prescription.scheduled_time), tz
        )
        old_status = prescription.status
        prescription.status = STATUS_MAP.get(old_status, "active")
        if old_status == "cancelled":
            prescription.cancelled_at = prescription.updated_at
            prescription.cancellation_reason = prescription.administration_notes
        prescription.save(
            update_fields=["starts_at", "status", "cancelled_at", "cancellation_reason"]
        )

        if old_status == "administered":
            MedicationAdministration.objects.create(
                prescription=prescription,
                scheduled_for=prescription.starts_at,
                administered_at=prescription.administered_at or prescription.updated_at,
                # Si quien administró ya no existe se atribuye a quien prescribió
                administered_by_id=prescription.administered_by_id or prescription.prescribed_by_id,
                units_deducted=prescription.units_per_administration,
                notes=prescription.administration_notes,
            )


class Migration(migrations.Migration):
    dependencies = [
        ("medications", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="prescription",
            name="presc_patient_status_time_idx",
        ),
        migrations.AddField(
            model_name="prescription",
            name="starts_at",
            field=models.DateTimeField(null=True),
        ),
        migrations.AddField(
            model_name="prescription",
            name="frequency_hours",
            field=models.PositiveSmallIntegerField(
                blank=True,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(168),
                ],
            ),
        ),
        migrations.AddField(
            model_name="prescription",
            name="ends_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="prescription",
            name="cancelled_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="prescription",
            name="cancellation_reason",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.CreateModel(
            name="MedicationAdministration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("scheduled_for", models.DateTimeField()),
                ("administered_at", models.DateTimeField()),
                (
                    "units_deducted",
                    models.PositiveSmallIntegerField(
                        validators=[django.core.validators.MinValueValidator(1)]
                    ),
                ),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "administered_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="medication_administrations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "prescription",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="administrations",
                        to="medications.prescription",
                    ),
                ),
            ],
            options={
                "verbose_name": "Administración de Medicamento",
                "verbose_name_plural": "Administraciones de Medicamentos",
                "ordering": ["-scheduled_for", "-id"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("prescription", "scheduled_for"),
                        name="administration_unique_dose_slot",
                    )
                ],
            },
        ),
        # Sin reverse_code: deshacer exigiría reinventar scheduled_time para indicaciones recurrentes
        migrations.RunPython(migrate_single_dose_prescriptions),
        migrations.RemoveField(model_name="prescription", name="scheduled_time"),
        migrations.RemoveField(model_name="prescription", name="administered_by"),
        migrations.RemoveField(model_name="prescription", name="administered_at"),
        migrations.RemoveField(model_name="prescription", name="administration_notes"),
        migrations.AlterField(
            model_name="prescription",
            name="starts_at",
            field=models.DateTimeField(),
        ),
        migrations.AlterField(
            model_name="prescription",
            name="status",
            field=models.CharField(
                choices=[("active", "Vigente"), ("completed", "Completada"), ("cancelled", "Cancelada")],
                db_index=True,
                default="active",
                max_length=16,
            ),
        ),
        migrations.AlterModelOptions(
            name="prescription",
            options={
                "ordering": ["starts_at", "-id"],
                "verbose_name": "Indicación Médica",
                "verbose_name_plural": "Indicaciones Médicas",
            },
        ),
        migrations.AddIndex(
            model_name="prescription",
            index=models.Index(
                fields=["patient", "status", "starts_at"], name="presc_patient_status_start_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="prescription",
            constraint=models.CheckConstraint(
                condition=models.Q(("frequency_hours__isnull", True))
                | models.Q(("frequency_hours__gte", 1), ("frequency_hours__lte", 168)),
                name="prescription_frequency_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="prescription",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("ends_at__isnull", True),
                    models.Q(("ends_at__gt", models.F("starts_at")), ("frequency_hours__isnull", False)),
                    _connector="OR",
                ),
                name="prescription_end_after_start_for_recurring",
            ),
        ),
    ]
