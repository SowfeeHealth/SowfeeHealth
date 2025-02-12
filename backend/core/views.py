# views.py
from django.shortcuts import render, redirect
from .forms import SurveyForm
from django.http import HttpResponse
from .models import SurveyResult
from django.contrib import messages
from django.http import JsonResponse


def index_view(request):
    return render(request, 'index.html')

def survey_results_view(request):
    results = SurveyResult.objects.all()  # Fetch data from the view
    return render(request, 'survey_results.html', {'results': results})  # Pass data to template

def survey_view(request):
    if request.method == 'POST':
        print("POST Data:", request.POST)

        required_fields = ['name', 'email', 'q1', 'q2', 'q3', 'q4', 'q5']
        missing_fields = [field for field in required_fields if field not in request.POST]

        if missing_fields:
            print(f"Missing fields: {missing_fields}")
            return JsonResponse({"success": False, "error": "Missing fields"})  # Return error if fields are missing

        # Get form data from POST request
        student_name = request.POST.get('name')
        school_email = request.POST.get('email')
        question1_rating = request.POST.get('q1')
        question2_rating = request.POST.get('q2')
        question3_rating = request.POST.get('q3')
        question4_rating = request.POST.get('q4')
        question5_rating = request.POST.get('q5')

        # Create and save SurveyResult instance
        survey_result = SurveyResult(
            name=student_name,
            email=school_email,
            q1=question1_rating,
            q2=question2_rating,
            q3=question3_rating,
            q4=question4_rating,
            q5=question5_rating,
        )
        
        # Use update_or_create() to update if exists, else create new entry
        try:
            survey_result, created = SurveyResult.objects.update_or_create(
                name=student_name,
                email=school_email,
                defaults={
                    "q1": question1_rating,
                    "q2": question2_rating,
                    "q3": question3_rating,
                    "q4": question4_rating,
                    "q5": question5_rating,
                }
            )

            # Return all the fields in JSON response
            response_data = {
                "name": survey_result.name,
                "email": survey_result.email,
                "q1": survey_result.q1,
                "q2": survey_result.q2,
                "q3": survey_result.q3,
                "q4": survey_result.q4,
                "q5": survey_result.q5,
                "flagged": survey_result.flagged,
                "submitted_at": survey_result.submitted_at
            }

            return JsonResponse({"success": True, "message": "Thank you for your honest response! Your input makes a difference.", "data": response_data})

        except Exception as e:
            print(f"Error saving survey result: {e}")
            return JsonResponse({"success": False, "error": "There was an error saving your survey. Please try again."})

    return render(request, 'survey.html')  # Render the form if it's a GET request
