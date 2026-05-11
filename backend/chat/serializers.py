from rest_framework import serializers
from .models import CounselorStudentAssignment


class AssignmentSerializer(serializers.ModelSerializer):
    counselor_email = serializers.EmailField(source='counselor.email', read_only=True)
    student_email = serializers.EmailField(source='student.email', read_only=True)

    class Meta:
        model = CounselorStudentAssignment
        fields = ['id', 'counselor', 'student', 'counselor_email', 'student_email', 'is_active', 'version', 'created_at']
        read_only_fields = ['created_at', 'version']

    def validate(self, data):
        return data