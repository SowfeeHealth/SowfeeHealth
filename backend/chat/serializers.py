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
        request = self.context.get('request')
        if not request:
            return data

        admin = request.user
        counselor = data.get('counselor')
        student = data.get('student')

        # Ensure both users belong to the admin's institution
        if counselor and counselor.institution_details != admin.institution_details:
            raise serializers.ValidationError({'counselor': 'Counselor not in your institution'})
        if student and student.institution_details != admin.institution_details:
            raise serializers.ValidationError({'student': 'Student not in your institution'})

        return data