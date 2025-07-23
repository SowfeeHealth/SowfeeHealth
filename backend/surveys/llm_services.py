import openai
import json
from django.conf import settings

client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
def analyze_mental_health_responses(text, question_text=""):
    """Analyze text responses for mental health concerns with balanced sensitivity"""
    if not text:
        return {"flag": False, "severity": "none", "reason": "No text provided"}
    
    try:
        prompt = f"""Analyze this student mental health survey response for concerning content that may indicate risk to self or others.

Question: {question_text}
Response: "{text}"

Flag as concerning if the response contains:

**HIGH SEVERITY - Immediate Risk:**
- Direct statements about wanting to die, suicide, or ending life
- Specific mentions of self-harm methods or weapons in harmful context
- Active plans or preparation for self-harm
- Phrases like "gunshot and die", "time to end this life", "want to kill myself", "end it all"
- Threats of violence toward others
- References to obtaining weapons for harmful purposes
- Any mention of specific suicide methods or means

**MEDIUM SEVERITY - Significant Concern:**
- Expressions of hopelessness: "can't take it anymore", "no point in living", "give up"
- Feeling worthless, like a burden, or that others would be better off without them
- Mentions of substance abuse as coping mechanism
- Severe isolation, withdrawal from friends/family
- Persistent thoughts of death (even if not actively suicidal)
- Vague references to ending things: "make it stop", "be done with everything"
- Extreme despair or feeling trapped with no way out

**LOW SEVERITY - Monitor:**
- Persistent sadness, depression, or anxiety
- Sleep/appetite changes, difficulty concentrating
- Loss of interest in activities they used to enjoy
- Academic performance decline
- Relationship problems or social conflicts
- Mild expressions of being overwhelmed or stressed beyond normal levels

**DO NOT FLAG:**
- Basic academic stress without emotional distress indicators
- Mild frustration with school, parents, or friends
- References to death in clearly abstract/philosophical context
- Legitimate activities (hunting, sports, collecting) with no emotional distress
- Single instances of temporary disappointment

**CONTEXT CONSIDERATIONS:**
- Lean toward flagging when uncertain - missing genuine distress is worse than over-flagging
- Pay attention to emotional intensity, not just specific words
- Consider cumulative effect of multiple concerning elements
- Look for genuine distress signals even in casual language

Return JSON only: {{"flag": true/false, "severity": "high/medium/low/none", "reason": "specific concerning elements identified"}}"""
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system", 
                    "content": "You are a mental health screening assistant. Your primary goal is to identify concerning content that could indicate risk. When in doubt, err on the side of caution and flag for review. It's better to over-detect than miss genuine distress. Respond with JSON only."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,  # Lower temperature for more consistent detection
            max_tokens=150
        )
        
        result = json.loads(response.choices[0].message.content)
        return result
        
    except json.JSONDecodeError as e:
        print(f"JSON parsing error: {e}")
        return {"flag": False, "severity": "none", "reason": "Unable to parse AI response"}
    except Exception as e:
        print(f"Mental health analysis error: {e}")
        return {"flag": False, "severity": "none", "reason": f"Analysis failed: {str(e)}"}
