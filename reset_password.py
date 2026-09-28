from database import SessionLocal
import models
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

db = SessionLocal()

user = db.query(models.User).filter(
    models.User.email == "alice@example.com"
).first()

if user:
    new_password = "Alice123@123"
    user.password = pwd_context.hash(new_password)
    db.commit()

    print("Password reset successfully!")
    print("New password:", new_password)
else:
    print("User not found.")

db.close()