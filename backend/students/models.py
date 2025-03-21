from django.db import models

class Student(models.Model):
    student_name = models.CharField(max_length=250)
    student_email = models.EmailField(max_length=250)
    university_id = models.CharField(max_length=250)

    class Meta:
        unique_together = (('student_name', 'student_email'),)  # Ensure (name, email) is unique