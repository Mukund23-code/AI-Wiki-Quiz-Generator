from sqlalchemy import Column, Integer, String, Text
from database import Base

class QuizHistory(Base):
    __tablename__ = "quiz_history"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, nullable=False)
    title = Column(String, default="")
    quiz_json = Column(Text, nullable=False)
    summary = Column(Text, default="")
