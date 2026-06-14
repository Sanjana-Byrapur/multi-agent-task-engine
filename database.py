import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = "sqlite:///./tasks.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    assignee = Column(String, index=True, nullable=False)
    priority = Column(String, default="medium")  # low, medium, high
    status = Column(String, default="pending")    # pending, completed
    due_date = Column(String, nullable=True)     # YYYY-MM-DD
    created_at = Column(DateTime, default=datetime.utcnow)
    
Base.metadata.create_all(bind=engine)

# Core Python CRUD Operations (To be wrapped as tools)
def db_create_task(title: str, assignee: str, priority: str = "medium", due_date: str = None):
    db = SessionLocal()
    task = Task(title=title, assignee=assignee, priority=priority, due_date=due_date, status="pending")
    db.add(task)
    db.commit()
    db.refresh(task)
    db.close()
    return f"Success: Task #{task.id} '{task.title}' created and assigned to {task.assignee}."

def db_get_tasks(assignee: str = None, status: str = None, check_overdue: bool = False):
    db = SessionLocal()
    query = db.query(Task)
    # if assignee:
    #     query = query.filter(Task.assignee.ilike(assignee))
    if assignee:
        query = query.filter(Task.assignee.ilike(f"%{assignee}%"))
    if status:
        query = query.filter(Task.status == status)
    
    tasks = query.all()
    db.close()
    
    if check_overdue:
        today = datetime.today().strftime('%Y-%m-%d')
        tasks = [t for t in tasks if t.due_date and t.due_date < today and t.status == "pending"]
        
    return tasks

def db_update_task_status(task_id: int, status: str):
    db = SessionLocal()
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        db.close()
        return f"Error: Task with ID {task_id} not found."
    task.status = status
    db.commit()
    db.close()
    return f"Success: Task #{task_id} marked as {status}."