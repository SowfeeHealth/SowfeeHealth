# views.py
from django.shortcuts import render, redirect
from .forms import SurveyForm

def survey(request):
    if request.method == 'POST':
        form = SurveyForm(request.POST)
        if form.is_valid():
            form.save()  # Save the form data to the database
            return redirect('thank_you')  # Redirect to a thank-you page after submission
    else:
        form = SurveyForm()

    return render(request, 'survey.html', {'form': form})
