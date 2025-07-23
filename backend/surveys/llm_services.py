import openai
import json
from django.conf import settings

client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
def analyze_mental_health_responses(text, question_text=""):
    """Analyze text responses for mental health concerns"""
    if not text:
        return {"flag": False, "severity": "none", "reason": "No text"}
    try:
        prompt = f"""Analyze this student mental health survey response for concerning content that may indicate risk to self or others.
        
        Question: {question_text}
        Response: {text}
        
        Flag as concerning if the response contains:
        - Self-harm intentions or behaviors
        - Suicidal thoughts, plans, or ideation
        - Severe depression or hopelessness
        - Violence toward others or violent fantasies
        - Weapon acquisition, possession, or interest (guns, knives, etc.)
        - Threats or aggressive language toward specific people or groups
        - Substance abuse or dangerous drug use
        - Eating order behaviors
        - Extreme anger or rage
        - Plans to hurt others
        - Inappropriate sexual content or behaviors
        - Severe profanity or disturbing language
        
        Consider context: statements about legitimate activities (hunting, sports, collecting) should be evaluated carefully.
        
        Return JSON only: {{"flag": true/false, "severity": "high/medium/low/none", "reason": "brief explanation"}}"""
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a mental health screening assistant trained to identify concerning content in student responses. Be thorough but consider context. Respond with JSON only."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=150
        )
        
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"LLM analysis error: {e}")
        return {"flag": False, "severity": "none", "reason": "Analysis failed"}