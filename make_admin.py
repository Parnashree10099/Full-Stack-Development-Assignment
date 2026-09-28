from database import SessionLocal
import models

db = SessionLocal()

user = db.query(models.User).filter(
    models.User.email == "alice@example.com"
).first()

if user:
    user.role = "admin"
    db.commit()
    print("User is now an admin!")
else:
    print("User not found.")

db.close()