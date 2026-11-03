from rest_framework import serializers

from vitals.serializers import CribStatusCountsSerializer


class CountsByKeySerializer(serializers.DictField):
    child = serializers.IntegerField()


class PatientCountsSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    active = serializers.IntegerField()
    discharged = serializers.IntegerField()


class CribReportSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    by_status = CribStatusCountsSerializer()
    occupancy_percent = serializers.FloatField()


class PrescriptionReportSerializer(serializers.Serializer):
    by_status = CountsByKeySerializer()
    administrations_today = serializers.IntegerField()


class AlertReportSerializer(serializers.Serializer):
    open = serializers.IntegerField()
    open_by_severity = CountsByKeySerializer()
    open_by_type = CountsByKeySerializer()


class StaffReportSerializer(serializers.Serializer):
    active = serializers.IntegerField()
    by_shift = CountsByKeySerializer()
    assignments_current_shift_day = serializers.IntegerField()


class OperationsSummarySerializer(serializers.Serializer):
    generated_at = serializers.DateTimeField()
    patients = PatientCountsSerializer()
    cribs = CribReportSerializer()
    prescriptions = PrescriptionReportSerializer()
    medications_low_stock = serializers.IntegerField()
    alerts = AlertReportSerializer()
    care_plans_active = serializers.IntegerField()
    staff = StaffReportSerializer()


class ActivityPointSerializer(serializers.Serializer):
    date = serializers.DateField()
    admissions = serializers.IntegerField()
    alerts = serializers.IntegerField()
