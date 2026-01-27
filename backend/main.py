from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests, os, json, re
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from database import SessionLocal, Base, engine
from models import QuizHistory
from dotenv import load_dotenv

load_dotenv()

# ---------------- Database Setup ----------------
Base.metadata.create_all(bind=engine)

# ---------------- FastAPI Setup ----------------
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- Gemini API Config ----------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("WARNING: GEMINI_API_KEY not found in environment!")

#GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/embedding-gecko-001"
#GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

# ---------------- DB Dependency ----------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------------- Request Schema ----------------
class QuizRequest(BaseModel):
    url: str
    difficulty: str = "easy"
    number_of_questions: int = 5

# ---------------- Endpoints ----------------
@app.get("/")
def root():
    return {"status": "Backend running", "api_key_set": bool(GEMINI_API_KEY)}

@app.post("/quiz")
def generate_quiz(data: QuizRequest, db: Session = Depends(get_db)):
    # ---------------- Fetch Wikipedia content ----------------
    try:
        response = requests.get(
            data.url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10
        )
        response.raise_for_status()
    except Exception as e:
        raise HTTPException(400, f"Failed to fetch URL: {e}")

    # Extract article title and paragraphs
    soup = BeautifulSoup(response.text, "html.parser")
    title_tag = soup.find("h1", class_="firstHeading") or soup.find("h1")
    article_title = title_tag.get_text().strip() if title_tag else "Wikipedia Article"
    
    paragraphs = [p.get_text().strip() for p in soup.find_all("p") if len(p.get_text().strip()) > 50]
    article_text = "\n".join(paragraphs[:10])[:4000]  # First 10 paragraphs, max 4000 chars

    if not article_text:
        raise HTTPException(400, "No article text found in the page")

    # ---------------- Prepare LLM prompt ----------------
    prompt = f"""You are a quiz generator. Based on the following Wikipedia article about "{article_title}", generate exactly {data.number_of_questions} multiple-choice questions.

Article Content:
{article_text}

IMPORTANT INSTRUCTIONS:
1. Create {data.number_of_questions} unique questions based ONLY on information from the article above
2. Each question must have exactly 4 options (A, B, C, D)
3. Make questions factual and specific to the article content
4. Vary difficulty levels across questions
5. Provide a brief explanation for each answer

Return ONLY a valid JSON object with no markdown formatting, no code blocks, no extra text. Use this exact format:

{{
  "questions": [
    {{
      "question": "Question text here?",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "answer": "Option A",
      "difficulty": {data.difficulty},
      "explanation": "Brief explanation based on the article."
    }}
  ],
  "related_topics": ["Topic1", "Topic2", "Topic3"]
}}
"""

    # ---------------- Call Gemini API ----------------
    quiz_json = None
    
    if GEMINI_API_KEY:
        try:
            gemini_payload = {
                "contents": [{
                    "parts": [{
                        "text": prompt
                    }]
                }],
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": 2048
                }
            }
            
            gemini_response = requests.post(
                f"{GEMINI_URL}?key={GEMINI_API_KEY}",
                json=gemini_payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            print(f"Gemini Status Code: {gemini_response.status_code}")
            
            if gemini_response.status_code == 200:
                response_json = gemini_response.json()
                raw_text = response_json["candidates"][0]["content"]["parts"][0]["text"]
                
                print("===== RAW GEMINI OUTPUT =====")
                print(raw_text[:500])  # Print first 500 chars
                
                # Clean and extract JSON
                raw_text = raw_text.strip()
                raw_text = re.sub(r'^```json\s*', '', raw_text)
                raw_text = re.sub(r'\s*```$', '', raw_text)
                
                match = re.search(r'\{[\s\S]*\}', raw_text)
                if match:
                    quiz_json = json.loads(match.group())
                    
                    # Validate structure
                    if "questions" in quiz_json and len(quiz_json["questions"]) >= data.number_of_questions:
                        print(f"✓ Successfully generated {len(quiz_json['questions'])} questions")
                    else:
                        print("✗ Invalid quiz structure from Gemini")
                        quiz_json = None
            else:
                print(f"Gemini API Error: {gemini_response.text}")
                
        except requests.exceptions.Timeout:
            print("⏱ Gemini API timeout - using fallback")
        except Exception as e:
            print(f"Gemini API call failed: {e}")
    else:
        print("No API key - using fallback")

    # ---------------- Fallback with article-based questions ----------------
    if not quiz_json:
        # Create simple questions from article
        sentences = [s.strip() for s in article_text.split('.') if len(s.strip()) > 30][:data.number_of_questions]
        
        quiz_json = {
            "questions": [
                {
                    "question": f"According to the article about {article_title}, what topic is discussed in section {i+1}?",
                    "options": [
                        f"Information about {article_title}",
                        "Unrelated topic",
                        "Different subject",
                        "Another area"
                    ],
                    "answer": f"Information about {article_title}",
                    "difficulty": data.difficulty,
                    "explanation": f"This question is based on content from the Wikipedia article about {article_title}."
                }
                for i in range(data.number_of_questions)
            ],
            "related_topics": [article_title, "Wikipedia", "General Knowledge"]
        }

    # ---------------- Convert options to frontend format ----------------
    for q in quiz_json["questions"]:
        correct_answer = q.get("answer")
        q["options"] = [
            {"text": opt, "is_correct": opt == correct_answer} 
            for opt in q.get("options", [])
        ]
        q.pop("answer", None)

    # ---------------- Save to DB ----------------
    record = QuizHistory(
        url=data.url,
        title=article_title,
        quiz_json=json.dumps(quiz_json),
        summary=article_text[:500]
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "title": article_title,
        "questions": quiz_json["questions"],
        "related_topics": quiz_json.get("related_topics", [])
    }

# ---------------- History Endpoint ----------------
@app.get("/history")
def get_history(db: Session = Depends(get_db)):
    records = db.query(QuizHistory).order_by(QuizHistory.id.desc()).all()
    return [
        {
           # "id": r.id,
            "url": r.url,
            "title": r.title,
            "created_at": str(r.id),  # Using id as proxy for order
            "quiz_data": json.loads(r.quiz_json)
        }
        for r in records
    ]

@app.get("/quiz/{quiz_id}")
def get_quiz_detail(quiz_id: int, db: Session = Depends(get_db)):
    record = db.query(QuizHistory).filter(QuizHistory.id == quiz_id).first()
    if not record:
        raise HTTPException(404, "Quiz not found")
    
    return {
        "id": record.id,
        "url": record.url,
        "title": record.title,
        "quiz_data": json.loads(record.quiz_json)
    }