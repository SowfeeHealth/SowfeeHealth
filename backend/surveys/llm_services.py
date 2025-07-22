import openai
import json
from django.conf import settings

client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
def analyze_mental_health_responses(text, question_text=""):
    """Analyze text responses for mental health concerns"""
    if not text:
        return {"flag": False, "severity": "none", "reason": "No text"}
    try:
        prompt = f"""Analyze this student mental health survey response for concerning content.
        Question: {question_text}
        Response: {text}
        Look for: self-harm, suicide ideation, severe depression, violence, substance abuse, eating disorders, profanity content
        Return JSON only: {{"flag": true/false, "severity": "high/medium/low/none", "reason": "brief explanation"}}"""
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a mental health screening assistant. Respond with JSON only."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=100
        )
        
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"LLM analysis error: {e}")
        return {"flag": False, "severity": "none", "reason": "Analysis failed"}