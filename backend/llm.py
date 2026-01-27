from openai import OpenAI
import os
import json

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def generate_quiz(article_text, num_questions=5, difficulty="easy"):
    prompt = f"""
You are an educational quiz generator.

ONLY use the information from the article below.
DO NOT use outside knowledge.

ARTICLE:
\"\"\"
{article_text}
\"\"\"

Generate {num_questions} {difficulty} level multiple-choice questions.

For each question provide:
- question
- 4 options
- correct answer
- short explanation based on the article

Return JSON ONLY in this format:
{{
  "questions": [
    {{
      "question": "...",
      "options": ["A", "B", "C", "D"],
      "answer": "...",
      "explanation": "..."
    }}
  ]
}}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        # Return error as JSON to avoid FastAPI crash
        return {"error": str(e)}
