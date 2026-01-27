import { useState, useEffect } from "react";
import "./App.css";

const API_URL = "http://127.0.0.1:8000";
function App() {
  const [activeTab, setActiveTab] = useState("generate");
  const [url, setUrl] = useState("");
  const [difficulty, setDifficulty] = useState("easy");
  const [numQuestions, setNumQuestions] = useState(5);
  const [quiz, setQuiz] = useState(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [score, setScore] = useState(0);
  const [completed, setCompleted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  
  // History state
  const [history, setHistory] = useState([]);
  const [selectedQuiz, setSelectedQuiz] = useState(null);
  const [showModal, setShowModal] = useState(false);

  const generateQuiz = async () => {
    if (!url) {
      setError("Please enter a Wikipedia URL");
      return;
    }
    
    setLoading(true);
    setError("");
    setQuiz(null);
    setCurrentIndex(0);
    setScore(0);
    setCompleted(false);

    try {
      const response = await fetch(`${API_URL}/quiz`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          url, 
          difficulty, 
          number_of_questions: numQuestions 
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to generate quiz");
      }

      const data = await response.json();
      
      if (!data.questions || data.questions.length === 0) {
        throw new Error("No questions generated");
      }

      setQuiz(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const loadHistory = async () => {
    try {
      const response = await fetch(`${API_URL}/history`);
      const data = await response.json();
      setHistory(data);
    } catch (err) {
      console.error("Failed to load history:", err);
    }
  };

  useEffect(() => {
    if (activeTab === "history") {
      loadHistory();
    }
  }, [activeTab]);

  const handleOptionClick = (option) => {
    if (quiz.questions[currentIndex].answered) return;

    if (option.is_correct) setScore(score + 1);

    const updatedQuestions = [...quiz.questions];
    updatedQuestions[currentIndex].answered = true;
    updatedQuestions[currentIndex].selected = option.text;
    setQuiz({ ...quiz, questions: updatedQuestions });
  };

  const handleNext = () => {
    if (currentIndex < quiz.questions.length - 1) {
      setCurrentIndex(currentIndex + 1);
    } else {
      setCompleted(true);
    }
  };

  const handleSkip = () => {
    handleNext();
  };

  const resetQuiz = () => {
    setUrl("");
    setQuiz(null);
    setCurrentIndex(0);
    setScore(0);
    setCompleted(false);
    setError("");
  };

  const openQuizModal = (quizData) => {
    setSelectedQuiz(quizData);
    setShowModal(true);
  };

  const closeModal = () => {
    setShowModal(false);
    setSelectedQuiz(null);
  };

  return (
    <div className="app-container">
      <h1 className="app-title">📚 Wiki Quiz App</h1>
      
      {/* Tabs */}
      <div className="tabs">
        <button
          className={`tab ${activeTab === "generate" ? "active" : ""}`}
          onClick={() => setActiveTab("generate")}
        >
          Generate Quiz
        </button>
        <button
          className={`tab ${activeTab === "history" ? "active" : ""}`}
          onClick={() => setActiveTab("history")}
        >
          Past Quizzes
        </button>
      </div>

      {/* TAB 1: GENERATE QUIZ */}
      {activeTab === "generate" && (
        <div className="content">
          {!quiz && !completed && (
            <div className="input-section">
              <input
                type="text"
                placeholder="Enter Wikipedia URL (e.g., https://en.wikipedia.org/wiki/Alan_Turing)"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                className="url-input"
              />
              
              <div className="options-row">
                <select
                  value={difficulty}
                  onChange={(e) => setDifficulty(e.target.value)}
                  className="select-input"
                >
                  <option value="easy">Easy</option>
                  <option value="medium">Medium</option>
                  <option value="hard">Hard</option>
                </select>
                
                <select
                  value={numQuestions}
                  onChange={(e) => setNumQuestions(parseInt(e.target.value))}
                  className="select-input"
                >
                  <option value="5">5 Questions</option>
                  <option value="7">7 Questions</option>
                  <option value="10">10 Questions</option>
                </select>
              </div>

              <button
                onClick={generateQuiz}
                disabled={loading}
                className={`generate-btn ${loading ? "disabled" : ""}`}
              >
                {loading ? "🔄 Generating Quiz..." : "🎯 Generate Quiz"}
              </button>
              
              {error && <p className="error-message">❌ {error}</p>}
            </div>
          )}

          {quiz && !completed && (
            <div className="quiz-section">
              <div className="quiz-header">
                <h2 className="quiz-title">{quiz.title || "Quiz"}</h2>
                <div className="progress-text">
                  Question {currentIndex + 1} of {quiz.questions.length}
                </div>
              </div>

              <div className="question-card">
                <div className="difficulty-badge">
                  {quiz.questions[currentIndex].difficulty}
                </div>
                
                <p className="question-text">
                  {quiz.questions[currentIndex].question}
                </p>
                
                <div className="options-list">
                  {quiz.questions[currentIndex].options.map((opt, i) => (
                    <button
                      key={i}
                      className={`option-btn ${
                        quiz.questions[currentIndex].answered
                          ? opt.is_correct
                            ? "correct"
                            : opt.text === quiz.questions[currentIndex].selected
                            ? "wrong"
                            : "disabled"
                          : ""
                      }`}
                      onClick={() => handleOptionClick(opt)}
                      disabled={quiz.questions[currentIndex].answered}
                    >
                      {String.fromCharCode(65 + i)}. {opt.text}
                    </button>
                  ))}
                </div>

                {quiz.questions[currentIndex].answered && (
                  <div className="explanation">
                    <strong>💡 Explanation:</strong> {quiz.questions[currentIndex].explanation}
                  </div>
                )}
              </div>

              <div className="quiz-controls">
                <button onClick={handleSkip} className="skip-btn">
                  Skip
                </button>
                {quiz.questions[currentIndex].answered && (
                  <button onClick={handleNext} className="next-btn">
                    {currentIndex < quiz.questions.length - 1 ? "Next →" : "Finish"}
                  </button>
                )}
              </div>
            </div>
          )}

          {completed && (
            <div className="result-section">
              <h2 className="result-title">🎉 Quiz Completed!</h2>
              <div className="score-card">
                <p className="score-label">Your Score</p>
                <p className="score-value">
                  {score} / {quiz.questions.length}
                </p>
                <p className="score-percentage">
                  {Math.round((score / quiz.questions.length) * 100)}%
                </p>
              </div>
              
              {quiz.related_topics && quiz.related_topics.length > 0 && (
                <div className="related-topics">
                  <h3>📖 Related Topics</h3>
                  <div className="topic-list">
                    {quiz.related_topics.map((topic, i) => (
                      <span key={i} className="topic-tag">{topic}</span>
                    ))}
                  </div>
                </div>
              )}
              
              <button onClick={resetQuiz} className="generate-btn">
                Start New Quiz
              </button>
            </div>
          )}
        </div>
      )}

      {/* TAB 2: HISTORY */}
      {activeTab === "history" && (
        <div className="content">
          <h2 className="section-title">Past Quizzes</h2>
          
          {history.length === 0 ? (
            <p className="empty-state">No quizzes yet. Generate your first quiz!</p>
          ) : (
            <div className="table-container">
              <table className="history-table">
                <thead>
                  <tr>
                    <th></th>
                    <th className="tableHeader">Title</th>
                    <th className="tableHeader">URL</th>
                    <th className="tableHeader">Questions</th>
                    <th className="tableHeader">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((item) => (
                    <tr key={item.id}>
                      <td>{item.id}</td>
                      <td className="tableSpacing">{item.title}</td>
                      <td className="tableSpacing">
                        <a href={item.url} target="_blank" rel="noopener noreferrer" className="table-link">
                          View Article
                        </a>
                      </td>
                      <td className="tableSpacing">{item.quiz_data.questions?.length || 0}</td>
                      <td className="tableSpacing">
                        <button
                          onClick={() => openQuizModal(item)}
                          className="detail-btn"
                        >
                          View Details
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* MODAL */}
      {showModal && selectedQuiz && (
        <div className="modal-overlay" onClick={closeModal}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <button onClick={closeModal} className="modal-close">✕</button>
            
            <h2 className="modal-title">{selectedQuiz.title}</h2>
            <a href={selectedQuiz.url} target="_blank" rel="noopener noreferrer" className="modal-link">
              🔗 View Wikipedia Article
            </a>
            
            <div className="modal-questions">
              {selectedQuiz.quiz_data.questions?.map((q, i) => (
                <div key={i} className="modal-question-card">
                  <div className="modal-question-header">
                    <span className="question-number">Q{i + 1}</span>
                    <span className="difficulty-badge">{q.difficulty}</span>
                  </div>
                  
                  <p className="modal-question-text">{q.question}</p>
                  
                  <div className="modal-options">
                    {q.options.map((opt, j) => (
                      <div
                        key={j}
                        className={`modal-option ${opt.is_correct ? "correct-option" : ""}`}
                      >
                        {String.fromCharCode(65 + j)}. {opt.text}
                        {opt.is_correct && <span className="checkmark"> ✓</span>}
                      </div>
                    ))}
                  </div>
                  
                  {q.explanation && (
                    <p className="modal-explanation">
                      <strong>💡 Explanation:</strong> {q.explanation}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );}
export default App;
