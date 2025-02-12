# views.py
from django.shortcuts import render, redirect
from .forms import SurveyForm
from django.http import HttpResponse

def index_view(request):
    return render(request, 'index.html')

'''def survey(request):
    if request.method == 'POST':
        form = SurveyForm(request.POST)
        if form.is_valid():
            form.save()  # Save the form data to the database
            return redirect('thank_you')  # Redirect to a thank-you page after submission
    else:
        form = SurveyForm()

    return render(request, 'survey.html', {'form': form})
'''
def survey_view(request):
    return render(request, 'survey.html')
    #return HttpResponse("Form submitted successfully!")
    '''
    if request.method == 'POST':
        # Here you can handle the POST request, e.g., saving data to the database
        # Check the submitted data:
        student_name = request.POST.get('student_name')
        school_email = request.POST.get('school_email')
        q1 = request.POST.get('q1')
        q2 = request.POST.get('q2')
        q3 = request.POST.get('q3')
        q4 = request.POST.get('q4')
        q5 = request.POST.get('q5')
        
        # Process or save this data as needed
        
        return HttpResponse("Form submitted successfully!")
    else:
        return render(request, 'survey.html')
    '''