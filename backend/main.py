from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests, os, json, re, random
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
    allow_origins=["*"],  # Changed to allow all origins for deployment
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

# ---------------- Helper Function ----------------
def shuffle_options(questions):
    """Shuffle options for each question while preserving the correct answer"""
    for question in questions:
        # Find the correct answer before shuffling
        correct_answer = None
        for opt in question.get("options", []):
            if isinstance(opt, dict) and opt.get("is_correct"):
                correct_answer = opt["text"]
                break
        
        # If options are already in the correct format (list of dicts)
        if question.get("options") and isinstance(question["options"][0], dict):
            options = question["options"]
            random.shuffle(options)
            question["options"] = options
        # If options need to be converted (list of strings with "answer" key)
        elif "answer" in question:
            correct_answer = question["answer"]
            options_list = question.get("options", [])
            # Shuffle the options
            random.shuffle(options_list)
            # Convert to frontend format
            question["options"] = [
                {"text": opt, "is_correct": opt == correct_answer} 
                for opt in options_list
            ]
            question.pop("answer", None)
    
    return questions

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
    
    # Extract more content based on number of questions
    num_paragraphs = 15 if data.number_of_questions <= 5 else 25
    max_chars = 6000 if data.number_of_questions <= 5 else 10000
    
    paragraphs = [p.get_text().strip() for p in soup.find_all("p") if len(p.get_text().strip()) > 50]
    article_text = "\n".join(paragraphs[:num_paragraphs])[:max_chars]

    if not article_text:
        raise HTTPException(400, "No article text found in the page")

    print(f"\n{'='*60}")
    print(f"📊 QUIZ GENERATION REQUEST")
    print(f"{'='*60}")
    print(f"   Title: {article_title}")
    print(f"   Content length: {len(article_text)} characters")
    print(f"   Questions requested: {data.number_of_questions}")
    print(f"   Difficulty: {data.difficulty}")
    print(f"{'='*60}\n")

    # ---------------- Prepare LLM prompt with difficulty-specific instructions ----------------
    difficulty_instructions = {
        "easy": "Focus on basic facts, definitions, and main concepts that are explicitly stated.",
        "medium": "Include questions that require understanding relationships between concepts and some inference.",
        "hard": "Create questions that require deep understanding, analysis, and connecting multiple pieces of information."
    }

    prompt = f"""You are an expert quiz generator. Create {data.number_of_questions} UNIQUE multiple-choice questions based on this Wikipedia article about "{article_title}".

Article Content:
{article_text}

CRITICAL REQUIREMENTS:
1. Generate EXACTLY {data.number_of_questions} questions - NO MORE, NO LESS
2. Difficulty Level: {data.difficulty} - {difficulty_instructions[data.difficulty]}
3. Each question MUST have EXACTLY 4 different options
4. Questions must be UNIQUE - cover different topics, facts, dates, people, events from the article
5. Base ALL questions on SPECIFIC FACTS from the article above
6. Make incorrect options plausible but clearly wrong
7. Provide clear explanations referencing the article

QUESTION VARIETY - Cover different aspects:
- Key facts and definitions
- Important dates and events
- People and their roles
- Causes and effects
- Locations and geography
- Historical context
- Comparisons and relationships

STRICT FORMAT REQUIREMENT:
Return ONLY valid JSON with NO markdown, NO code blocks, NO extra text.

{{
  "questions": [
    {{
      "question": "Specific factual question from the article?",
      "options": ["Correct answer from article", "Plausible wrong option 1", "Plausible wrong option 2", "Plausible wrong option 3"],
      "answer": "Correct answer from article",
      "difficulty": "{data.difficulty}",
      "explanation": "According to the article, [specific fact that answers the question]."
    }}
  ],
  "related_topics": ["Topic1", "Topic2", "Topic3"]
}}

IMPORTANT: All {data.number_of_questions} questions must be based on DIFFERENT information from the article. Generate exactly {data.number_of_questions} complete questions now.
"""

    # ---------------- Call Gemini API ----------------
    quiz_json = None
    
    if GEMINI_API_KEY:
        try:
            # Adjust parameters based on number of questions
            max_tokens = 2048 if data.number_of_questions <= 5 else (
                4096 if data.number_of_questions <= 7 else 8192
            )
            
            gemini_payload = {
                "contents": [{
                    "parts": [{
                        "text": prompt
                    }]
                }],
                "generationConfig": {
                    "temperature": 0.85,  # High variety but controlled
                    "maxOutputTokens": max_tokens,
                    "topP": 0.95,
                    "topK": 40
                }
            }
            
            print(f"🤖 Calling Gemini API (max_tokens={max_tokens})...")
            gemini_response = requests.post(
                f"{GEMINI_URL}?key={GEMINI_API_KEY}",
                json=gemini_payload,
                headers={"Content-Type": "application/json"},
                timeout=60
            )
            
            print(f"   Response Status: {gemini_response.status_code}")
            
            if gemini_response.status_code == 200:
                response_json = gemini_response.json()
                raw_text = response_json["candidates"][0]["content"]["parts"][0]["text"]
                
                print(f"   Response length: {len(raw_text)} characters")
                
                # Clean JSON
                raw_text = raw_text.strip()
                raw_text = re.sub(r'^```(?:json)?\s*', '', raw_text, flags=re.MULTILINE)
                raw_text = re.sub(r'\s*```$', '', raw_text, flags=re.MULTILINE)
                raw_text = raw_text.strip()
                
                # Parse JSON
                try:
                    quiz_json = json.loads(raw_text)
                    print(f"   ✓ JSON parsed successfully")
                except json.JSONDecodeError as e:
                    print(f"   ⚠️ Direct parse failed, trying regex extraction...")
                    match = re.search(r'\{[\s\S]*\}', raw_text)
                    if match:
                        try:
                            quiz_json = json.loads(match.group())
                            print(f"   ✓ Regex extraction successful")
                        except json.JSONDecodeError as e2:
                            print(f"   ✗ Regex parse failed: {e2}")
                
                # Validate structure
                if quiz_json and "questions" in quiz_json:
                    num_generated = len(quiz_json["questions"])
                    print(f"\n📝 Generated {num_generated} questions (requested: {data.number_of_questions})")
                    
                    # Validate each question has 4 options
                    valid_questions = []
                    for i, q in enumerate(quiz_json["questions"]):
                        if "options" in q and len(q["options"]) == 4 and "answer" in q:
                            valid_questions.append(q)
                        else:
                            print(f"   ⚠️ Question {i+1} invalid (wrong number of options or missing answer)")
                    
                    if len(valid_questions) >= data.number_of_questions:
                        quiz_json["questions"] = valid_questions[:data.number_of_questions]
                        print(f"   ✓ Using {len(quiz_json['questions'])} valid questions")
                    elif len(valid_questions) >= int(data.number_of_questions * 0.6):  # At least 60%
                        quiz_json["questions"] = valid_questions
                        print(f"   ⚠️ Only got {len(valid_questions)} valid questions, using them")
                    else:
                        print(f"   ✗ Not enough valid questions ({len(valid_questions)}/{data.number_of_questions})")
                        quiz_json = None
                else:
                    print(f"   ✗ Invalid quiz structure")
                    quiz_json = None
                    
            else:
                error_text = gemini_response.text
                print(f"   ✗ API Error ({gemini_response.status_code}): {error_text[:200]}")
                
        except requests.exceptions.Timeout:
            print("   ⏱ API timeout")
        except Exception as e:
            print(f"   ✗ Exception: {type(e).__name__}: {str(e)[:200]}")
    else:
        print("⚠️ No API key configured")

    # ---------------- Enhanced Fallback ----------------
    if not quiz_json:
        print(f"\n⚠️ Using fallback for {data.number_of_questions} questions\n")
        
        # Extract sentences and key information
        sentences = [s.strip() for s in article_text.split('.') if len(s.strip()) > 60][:data.number_of_questions * 3]
        
        # Diverse question templates
        templates = [
            ("What does the article state about {topic}?", "content"),
            ("According to the article, which fact about {topic} is accurate?", "fact"),
            ("What information is provided regarding {topic}?", "information"),
            ("The article mentions {topic}. What is emphasized?", "emphasis"),
            ("Which statement about {topic} is supported by the article?", "statement"),
            ("What key detail about {topic} does the article include?", "detail"),
            ("According to the Wikipedia article, what is true about {topic}?", "truth"),
            ("The article discusses {topic}. What is highlighted?", "highlight"),
            ("What aspect of {topic} does the article specifically address?", "aspect"),
            ("Which characteristic of {topic} is described in the article?", "characteristic"),
        ]
        
        # Generate diverse distractors
        distractor_sets = [
            ["Information not mentioned in the article", "An unrelated historical fact", "A different topic entirely"],
            ["Content from another subject", "An incorrect interpretation", "A misattributed fact"],
            ["Unrelated information", "A different time period", "An alternative topic"],
            ["Information outside the article scope", "A contradicting statement", "An unmentioned detail"],
            ["A topic not covered here", "Incorrect historical data", "Unrelated subject matter"],
        ]
        
        fallback_questions = []
        
        for i in range(data.number_of_questions):
            if i < len(sentences):
                template, _ = templates[i % len(templates)]
                correct = sentences[i][:120] + ("..." if len(sentences[i]) > 120 else "")
                distractors = distractor_sets[i % len(distractor_sets)].copy()
                
                fallback_questions.append({
                    "question": template.format(topic=article_title),
                    "options": [correct] + distractors,
                    "answer": correct,
                    "difficulty": data.difficulty,
                    "explanation": f"This information is stated in the article about {article_title}."
                })
            else:
                fallback_questions.append({
                    "question": f"What is this Wikipedia article primarily about?",
                    "options": [
                        article_title,
                        "An unrelated topic",
                        "A different subject",
                        "Another area of study"
                    ],
                    "answer": article_title,
                    "difficulty": data.difficulty,
                    "explanation": f"The article focuses on {article_title}."
                })
        
        quiz_json = {
            "questions": fallback_questions,
            "related_topics": [article_title, "Wikipedia", "General Knowledge"]
        }
        
        print(f"✓ Fallback generated {len(fallback_questions)} questions")

    # ---------------- Shuffle options and convert to frontend format ----------------
    print(f"\n🔀 Shuffling options...")
    quiz_json["questions"] = shuffle_options(quiz_json["questions"])

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

    print(f"✅ Quiz complete! Returning {len(quiz_json['questions'])} questions")
    print(f"{'='*60}\n")

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
            "created_at": str(r.id),
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