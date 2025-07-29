from surveys.models import Student, SurveyResponse, FlaggedStudents
from faker import Faker
import random
import datetime
from django.utils import timezone

# 100 random students for College University
def generate_random_students_for_CU():
    faker = Faker()
    for i in range(200):
        random_name = faker.name()
        student = Student(school_email=random_name.replace(" ", "")+"@cu.edu", student_name=random_name, 
                          university_id="cu")
        student.save()



# 66 random responses for students from College University
def generate_random_responses_for_CU():
    students = list(Student.objects.all())
    random.shuffle(students)
    random_students = students[:66]

    for student in random_students:
        survey_response = SurveyResponse(student_name=student.student_name, school_email=student.school_email, 
                                         university_id=student.university_id, q1=random.randrange(1, 6), 
                                         q2=random.randrange(1, 6), q3=random.randrange(1, 6), q4=random.randrange(1, 6), 
                                         q5=random.randrange(1, 6))
        survey_response.save()

        # Randomize the created date
        now = timezone.now()
        survey_response.created = now - datetime.timedelta(days=random.randint(0, (timezone.now() - timezone.now().replace(month=1, day=1, second=0, minute=0, microsecond=0, hour=0)).days))
        survey_response.save()

        # Check if student should be flagged
        if any(getattr(survey_response, f'q{i}') >= 3 for i in range(1, 6)):
                flagged_student = FlaggedStudents(school_email=survey_response.school_email, student_name=survey_response.student_name,
                                                  student_response=survey_response)
                flagged_student.save()

# Clean up
Student.objects.all().delete()
SurveyResponse.objects.all().delete()

generate_random_students_for_CU()
generate_random_responses_for_CU()