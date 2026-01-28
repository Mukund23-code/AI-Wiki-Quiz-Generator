# Quiz Application 🎯

A full-stack Quiz Application where users can select a topic and difficulty level, attempt quizzes, view results, and store quiz history.

---

## 🌐 Live Demo

- **Frontend:** https://poetic-praline-b86131.netlify.app  
- **Backend API:** https://ai-wiki-quiz-generator-9x8p.onrender.com  

---

## 🛠 Tech Stack

### Frontend
- React.js
- HTML5
- CSS3
- JavaScript (ES6)

### Backend
- FastAPI
- Python

### Database
- SQLite
- SQLAlchemy ORM

### Deployment
- Frontend: Netlify
- Backend: Render

---

## ✨ Features

- Select quiz **topic** and **difficulty**
- Dynamic question generation
- Timer-based quiz
- Score calculation
- Result summary after quiz completion
- Quiz history stored using SQLite
- Responsive UI

---

## 🤖 AI Integration & Error Handling

This application uses the **Google Gemini API** for quiz question generation.

Due to **free-tier quota limitations**, the API may occasionally return a  
`429 – Quota Exceeded` error during evaluation or review.

To ensure uninterrupted functionality:
- The backend **automatically falls back** to predefined question generation
- The application continues to work without crashing
- This behavior is **intentional** and demonstrates proper error handling and production-safe design

---

## 📁 Project Structure

- `frontend/` – React application
- `backend/` – FastAPI backend
- SQLite database for quiz history storage
