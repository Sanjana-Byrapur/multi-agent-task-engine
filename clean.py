from database import SessionLocal, Task

db = SessionLocal()

# We are targeting the duplicate low-priority tasks for Alice
tasks_to_delete = [2, 3] 

# Find them and delete them
db.query(Task).filter(Task.id.in_(tasks_to_delete)).delete(synchronize_session=False)
db.commit()
db.close()

print("Duplicates successfully deleted!")