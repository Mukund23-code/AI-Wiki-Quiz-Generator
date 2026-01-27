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
    
    # INCREASED: More paragraphs and characters for better context, especially for 10 questions
    paragraphs = [p.get_text().strip() for p in soup.find_all("p") if len(p.get_text().strip()) > 50]
    article_text = "\n".join(paragraphs[:20])[:8000]  # 20 paragraphs, max 8000 chars

    if not article_text:
        raise HTTPException(400, "No article text found in the page")

    print(f"\n📊 Article Stats:")
    print(f"   Title: {article_title}")
    print(f"   Content length: {len(article_text)} characters")
    print(f"   Requested questions: {data.number_of_questions}")

    # ---------------- Prepare LLM prompt ----------------
    prompt = f"""You are a quiz generator. Based on the following Wikipedia article about "{article_title}", generate exactly {data.number_of_questions} multiple-choice questions.

Article Content:
{article_text}

CRITICAL INSTRUCTIONS - FOLLOW EXACTLY:
1. Generate EXACTLY {data.number_of_questions} questions - no more, no less
2. Each question MUST have exactly 4 options (A, B, C, D)
3. Base questions on SPECIFIC FACTS from the article (dates, names, events, definitions, etc.)
4. Make each question UNIQUE - cover different aspects of the article
5. Difficulty level: {data.difficulty}
6. Provide a brief explanation for each correct answer
7. Ensure all 4 options are plausible but only ONE is correct
8. DO NOT use generic or repeated question templates

IMPORTANT: You must generate all {data.number_of_questions} questions. If the article is long enough, create questions about:
- Main subject/topic
- Key dates and events
- Important people mentioned
- Definitions and concepts
- Causes and effects
- Locations and geography
- Historical context
- Related information

Return ONLY a valid JSON object with NO markdown formatting, NO code blocks, NO extra text.

Use this EXACT format:

{{
  "questions": [
    {{
      "question": "What year was [specific event] mentioned in the article?",
      "options": ["1950", "1960", "1970", "1980"],
      "answer": "1960",
      "difficulty": "{data.difficulty}",
      "explanation": "According to the article, [specific fact]."
    }},
    {{
      "question": "Who is described as [specific role] in the article?",
      "options": ["Person A", "Person B", "Person C", "Person D"],
      "answer": "Person B",
      "difficulty": "{data.difficulty}",
      "explanation": "The article states that [specific fact]."
    }}
  ],
  "related_topics": ["Topic1", "Topic2", "Topic3"]
}}

Generate EXACTLY {data.number_of_questions} complete questions now.
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
                    "temperature": 0.9,  # Higher temperature for more variety
                    "maxOutputTokens": 8192,  # INCREASED: Support for 10 questions needs more tokens
                    "topP": 0.95,
                    "topK": 40
                }
            }
            
            print(f"\n🤖 Calling Gemini API...")
            gemini_response = requests.post(
                f"{GEMINI_URL}?key={GEMINI_API_KEY}",
                json=gemini_payload,
                headers={"Content-Type": "application/json"},
                timeout=60  # INCREASED: Longer timeout for 10 questions
            )
            
            print(f"   Status Code: {gemini_response.status_code}")
            
            if gemini_response.status_code == 200:
                response_json = gemini_response.json()
                raw_text = response_json["candidates"][0]["content"]["parts"][0]["text"]
                
                print(f"   Response length: {len(raw_text)} characters")
                print(f"\n===== FIRST 1000 CHARS OF GEMINI OUTPUT =====")
                print(raw_text[:1000])
                print("=" * 50)
                
                # Clean and extract JSON - improved regex
                raw_text = raw_text.strip()
                # Remove markdown code blocks
                raw_text = re.sub(r'^```(?:json)?\s*', '', raw_text, flags=re.MULTILINE)
                raw_text = re.sub(r'\s*```$', '', raw_text, flags=re.MULTILINE)
                raw_text = raw_text.strip()
                
                # Try to parse directly first
                try:
                    quiz_json = json.loads(raw_text)
                    print(f"✓ Direct JSON parse successful")
                except json.JSONDecodeError as e:
                    print(f"⚠️ Direct parse failed: {e}")
                    # If that fails, try to extract JSON object
                    match = re.search(r'\{[\s\S]*\}', raw_text)
                    if match:
                        try:
                            quiz_json = json.loads(match.group())
                            print(f"✓ Regex extraction parse successful")
                        except json.JSONDecodeError as e2:
                            print(f"✗ Regex parse also failed: {e2}")
                
                # Validate structure
                if quiz_json and "questions" in quiz_json:
                    num_generated = len(quiz_json["questions"])
                    print(f"\n📝 Generated {num_generated} questions (requested: {data.number_of_questions})")
                    
                    if num_generated >= data.number_of_questions:
                        # Trim to exact number requested
                        quiz_json["questions"] = quiz_json["questions"][:data.number_of_questions]
                        print(f"✓ Successfully generated {len(quiz_json['questions'])} questions from Gemini")
                    elif num_generated >= data.number_of_questions * 0.7:  # At least 70% of requested
                        print(f"⚠️ Generated {num_generated} questions, requested {data.number_of_questions} - using what we have")
                        # Use what we got, it's better than fallback
                    else:
                        print(f"✗ Only got {num_generated} questions, need at least {int(data.number_of_questions * 0.7)}")
                        quiz_json = None
                else:
                    print(f"✗ Invalid quiz structure from Gemini")
                    if quiz_json:
                        print(f"   Keys found: {quiz_json.keys() if isinstance(quiz_json, dict) else 'Not a dict'}")
                    quiz_json = None
            else:
                error_text = gemini_response.text
                print(f"✗ Gemini API Error ({gemini_response.status_code}): {error_text[:500]}")
                
        except requests.exceptions.Timeout:
            print("⏱ Gemini API timeout - using fallback")
        except json.JSONDecodeError as e:
            print(f"✗ JSON parsing error: {e}")
            print(f"   Raw text preview: {raw_text[:500]}")
        except Exception as e:
            print(f"✗ Gemini API call failed: {type(e).__name__}: {e}")
    else:
        print("⚠️ No API key - using fallback")

    # ---------------- Improved Fallback with article-based questions ----------------
    if not quiz_json:
        print(f"\n⚠️ Using fallback question generation for {data.number_of_questions} questions")
        
        # Extract meaningful sentences from the article
        sentences = [s.strip() + '.' for s in article_text.split('.') if len(s.strip()) > 40]
        
        # More diverse question templates
        question_templates = [
            "According to the article about {topic}, what is mentioned regarding {aspect}?",
            "What key fact about {topic} is stated in the article?",
            "The article discusses {topic}. Which detail is provided?",
            "What information does the article give about {topic}?",
            "Which statement about {topic} is accurate according to the article?",
            "The article mentions {topic}. What is a key point?",
            "What does the article reveal about {topic}?",
            "According to the Wikipedia article, what is true about {topic}?",
            "Which of the following facts about {topic} appears in the article?",
            "What aspect of {topic} does the article cover?"
        ]
        
        # Generate varied distractor options
        distractor_templates = [
            "Information not covered in this article",
            "An unrelated historical event",
            "A different subject matter",
            "Content from another topic",
            "An alternative viewpoint not mentioned",
            "A fact about a different subject",
            "Information from a different article",
            "An unrelated piece of information",
            "A topic not discussed here",
            "Content outside the article's scope"
        ]
        
        fallback_questions = []
        
        # Generate questions using different parts of the article
        for i in range(data.number_of_questions):
            if i < len(sentences):
                # Use different templates for variety
                template = question_templates[i % len(question_templates)]
                aspect = f"section {i+1}" if i > 0 else "the main topic"
                
                # Create varied distractors
                distractors = [
                    distractor_templates[j % len(distractor_templates)] 
                    for j in range(i, i+3)
                ]
                
                # Correct answer from article
                correct_answer = sentences[i][:150] + "..." if len(sentences[i]) > 150 else sentences[i]
                
                fallback_questions.append({
                    "question": template.format(topic=article_title, aspect=aspect),
                    "options": [correct_answer] + distractors,
                    "answer": correct_answer,
                    "difficulty": data.difficulty,
                    "explanation": f"This information is directly stated in the Wikipedia article about {article_title}."
                })
            else:
                # Generic questions if not enough sentences
                fallback_questions.append({
                    "question": f"What is the primary subject of this Wikipedia article?",
                    "options": [
                        f"{article_title}",
                        "A different historical period",
                        "An unrelated geographic location",
                        "A separate biographical subject"
                    ],
                    "answer": f"{article_title}",
                    "difficulty": data.difficulty,
                    "explanation": f"This article is primarily about {article_title}."
                })
        
        quiz_json = {
            "questions": fallback_questions,
            "related_topics": [article_title, "Wikipedia", "General Knowledge"]
        }
        
        print(f"✓ Generated {len(fallback_questions)} fallback questions")

    # Final validation
    if len(quiz_json["questions"]) < data.number_of_questions:
        print(f"⚠️ Warning: Only have {len(quiz_json['questions'])} questions, requested {data.number_of_questions}")

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

    print(f"\n✅ Quiz generation complete! Returning {len(quiz_json['questions'])} questions\n")

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