from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from datetime import datetime
from sqlalchemy.orm import Session
from database import engine, Base, get_db
import models
import schemas
from passlib.context import CryptContext
import os
from fastapi import UploadFile, File
from pypdf import PdfReader
from dotenv import load_dotenv
from google import genai
from fastapi.staticfiles import StaticFiles

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = "HS256"

security = HTTPBearer()
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        user_id = payload.get("user_id")

        if not user_id:
            raise HTTPException(
                status_code=401,
                detail="Invalid token"
            )

    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )

    user = db.query(models.User).filter(
        models.User.id == user_id
    ).first()

    if not user:
        raise HTTPException(
            status_code=401,
            detail="User not found"
        )

    return user


Base.metadata.create_all(bind=engine)

app = FastAPI()
app.mount("/frontend", StaticFiles(directory="frontend", html=True), name="frontend")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@app.get("/")
def home():
    return {"message": "Full Stack Assignment API is working!"}


@app.post("/api/register")
def register(user: schemas.UserRegister, db: Session = Depends(get_db)):

    existing_user = db.query(models.User).filter(
        models.User.email == user.email
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )

    hashed_password = pwd_context.hash(user.password)

    new_user = models.User(
        name=user.name,
        email=user.email,
        password=hashed_password,
        role="user"
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {
        "message": "Registration successful!",
        "user_id": new_user.id
    }
@app.post("/api/login")
def login(user: schemas.UserLogin, db: Session = Depends(get_db)):

    existing_user = db.query(models.User).filter(
        models.User.email == user.email
    ).first()

    if not existing_user:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    if not pwd_context.verify(
        user.password,
        existing_user.password
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    token_data = {
        "user_id": existing_user.id,
        "role": existing_user.role,
        "email": existing_user.email
    }

    token = jwt.encode(
        token_data,
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    return {
        "message": "Login successful!",
        "access_token": token,
        "user_id": existing_user.id,
        "name": existing_user.name,
        "email": existing_user.email,
        "role": existing_user.role
    }
@app.get("/api/subscriptions")
def get_subscriptions(
    current_user: models.User = Depends(get_current_user)
):
    return {
        "plans": [
            {
                "id": 1,
                "name": "Basic",
                "amount": 100,
                "credits": 100
            },
            {
                "id": 2,
                "name": "Premium",
                "amount": 250,
                "credits": 300
            }
        ]
    }
@app.post("/api/subscribe")
def subscribe(
    request: schemas.SubscribeRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    user = current_user

    plans = {
        1: {
            "name": "Basic",
            "amount": 100,
            "credits": 100
        },
        2: {
            "name": "Premium",
            "amount": 250,
            "credits": 300
        }
    }

    if request.plan_id not in plans:
        raise HTTPException(
            status_code=400,
            detail="Invalid plan"
        )

    plan = plans[request.plan_id]

    new_subscription = models.Subscription(
        user_id=user.id,
        plan_name=plan["name"],
        amount=plan["amount"],
        credits=plan["credits"],
        status="active"
    )

    db.add(new_subscription)

    wallet = db.query(models.Wallet).filter(
        models.Wallet.user_id == user.id
    ).first()

    if not wallet:
        wallet = models.Wallet(
            user_id=user.id,
            balance=0
        )
        db.add(wallet)
        db.flush()

    wallet.balance += plan["credits"]

    transaction = models.WalletTransaction(
        user_id=user.id,
        transaction_type="credit",
        amount=plan["credits"],
        description=f"{plan['name']} subscription credit"
    )

    db.add(transaction)

    db.commit()
    db.refresh(wallet)

    return {
        "message": "Subscription successful!",
        "plan": plan["name"],
        "credits_added": plan["credits"],
        "wallet_balance": wallet.balance
    }
@app.get("/api/wallet")
def get_wallet(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    wallet = db.query(models.Wallet).filter(
        models.Wallet.user_id == current_user.id
    ).first()

    if not wallet:
        raise HTTPException(
            status_code=404,
            detail="Wallet not found"
        )

    return {
        "user_id": current_user.id,
        "balance": wallet.balance
    }
@app.get("/api/wallet/transactions")
def get_transactions(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    transactions = db.query(models.WalletTransaction).filter(
        models.WalletTransaction.user_id == current_user.id
    ).all()

    return {
        "user_id": current_user.id,
        "transactions": [
            {
                "id": transaction.id,
                "type": transaction.transaction_type,
                "amount": transaction.amount,
                "description": transaction.description
            }
            for transaction in transactions
        ]
    }
@app.get("/api/users")
def get_users(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    users = db.query(models.User).filter(
        models.User.id != current_user.id
    ).all()

    return {
        "users": [
            {
                "id": user.id,
                "name": user.name,
                "email": user.email
            }
            for user in users
        ]
    }
@app.post("/api/connect")
def send_connection_request(
    request: schemas.ConnectionRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    sender_id = current_user.id
    receiver_id = request.receiver_id

    if sender_id == receiver_id:
        raise HTTPException(
            status_code=400,
            detail="You cannot connect with yourself"
        )

    receiver = db.query(models.User).filter(
        models.User.id == receiver_id
    ).first()

    if not receiver:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    existing_request = db.query(models.Connection).filter(
        (
            (models.Connection.sender_id == sender_id) &
            (models.Connection.receiver_id == receiver_id)
        )
        |
        (
            (models.Connection.sender_id == receiver_id) &
            (models.Connection.receiver_id == sender_id)
        )
    ).first()

    if existing_request:
        raise HTTPException(
            status_code=400,
            detail="Connection request already exists"
        )

    new_connection = models.Connection(
        sender_id=sender_id,
        receiver_id=receiver_id,
        status="pending"
    )

    db.add(new_connection)
    db.commit()
    db.refresh(new_connection)

    return {
        "message": "Connection request sent!",
        "connection_id": new_connection.id
    }
@app.post("/api/connect/{connection_id}/accept")
def accept_connection(
    connection_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    connection = db.query(models.Connection).filter(
        models.Connection.id == connection_id
    ).first()

    if not connection:
        raise HTTPException(
            status_code=404,
            detail="Connection request not found"
        )

    if connection.receiver_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You can only accept requests sent to you"
        )

    if connection.status != "pending":
        raise HTTPException(
            status_code=400,
            detail="This request has already been processed"
        )

    connection.status = "accepted"

    db.commit()
    db.refresh(connection)

    return {
        "message": "Connection request accepted!",
        "connection_id": connection.id,
        "status": connection.status
    }
@app.post("/api/connect/{connection_id}/reject")
def reject_connection(
    connection_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    connection = db.query(models.Connection).filter(
        models.Connection.id == connection_id
    ).first()

    if not connection:
        raise HTTPException(
            status_code=404,
            detail="Connection request not found"
        )

    if connection.receiver_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You can only reject requests sent to you"
        )

    if connection.status != "pending":
        raise HTTPException(
            status_code=400,
            detail="This request has already been processed"
        )

    connection.status = "rejected"

    db.commit()
    db.refresh(connection)

    return {
        "message": "Connection request rejected!",
        "connection_id": connection.id,
        "status": connection.status
    }
@app.get("/api/connections")
def get_connections(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    user_id = current_user.id

    connections = db.query(models.Connection).filter(
        (
            (models.Connection.sender_id == user_id) |
            (models.Connection.receiver_id == user_id)
        ),
        models.Connection.status == "accepted"
    ).all()

    connected_users = []

    for connection in connections:

        if connection.sender_id == user_id:
            other_user_id = connection.receiver_id
        else:
            other_user_id = connection.sender_id

        other_user = db.query(models.User).filter(
            models.User.id == other_user_id
        ).first()

        if other_user:
            connected_users.append({
                "id": other_user.id,
                "name": other_user.name,
                "email": other_user.email
            })

    return {
        "user_id": current_user.id,
        "connections": connected_users
    }
@app.post("/api/calls")
def start_call(
    request: schemas.StartCallRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    caller_id = current_user.id
    receiver_id = request.receiver_id

    if caller_id == receiver_id:
        raise HTTPException(
            status_code=400,
            detail="You cannot call yourself"
        )

    connection = db.query(models.Connection).filter(
        (
            (
                (models.Connection.sender_id == caller_id) &
                (models.Connection.receiver_id == receiver_id)
            )
            |
            (
                (models.Connection.sender_id == receiver_id) &
                (models.Connection.receiver_id == caller_id)
            )
        ),
        models.Connection.status == "accepted"
    ).first()

    if not connection:
        raise HTTPException(
            status_code=403,
            detail="You can only call an accepted connection"
        )

    new_call = models.Call(
        caller_id=caller_id,
        receiver_id=receiver_id,
        status="started"
    )

    db.add(new_call)
    db.commit()
    db.refresh(new_call)

    return {
        "message": "Call started!",
        "call_id": new_call.id,
        "caller_id": new_call.caller_id,
        "receiver_id": new_call.receiver_id,
        "status": new_call.status
    }
@app.post("/api/calls/{call_id}/end")
def end_call(
    call_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    call = db.query(models.Call).filter(
        models.Call.id == call_id
    ).first()

    if not call:
        raise HTTPException(
            status_code=404,
            detail="Call not found"
        )

    # Only the caller or receiver can end this call
    if (
        call.caller_id != current_user.id
        and
        call.receiver_id != current_user.id
    ):
        raise HTTPException(
            status_code=403,
            detail="You cannot end this call"
        )

    if call.status == "ended":
        raise HTTPException(
            status_code=400,
            detail="Call has already ended"
        )

    call.end_time = datetime.utcnow()

    duration = call.end_time - call.start_time
    call.duration = int(duration.total_seconds())

    call.status = "ended"

    db.commit()
    db.refresh(call)

    return {
        "message": "Call ended!",
        "call_id": call.id,
        "duration_seconds": call.duration,
        "status": call.status
    }
@app.get("/api/calls/history")
def get_call_history(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    user_id = current_user.id

    calls = db.query(models.Call).filter(
        (
            (models.Call.caller_id == user_id) |
            (models.Call.receiver_id == user_id)
        )
    ).order_by(
        models.Call.id.desc()
    ).all()

    return {
        "user_id": current_user.id,
        "calls": [
            {
                "call_id": call.id,
                "caller_id": call.caller_id,
                "receiver_id": call.receiver_id,
                "start_time": call.start_time,
                "end_time": call.end_time,
                "duration_seconds": call.duration,
                "status": call.status
            }
            for call in calls
        ]
    }
@app.get("/api/admin/calls")
def admin_calls(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "admin":
        raise HTTPException(
        status_code=403,
        detail="Admin access required"
    )

    calls = db.query(models.Call).order_by(
        models.Call.id.desc()
    ).all()

    return {
        "calls": [
            {
                "call_id": call.id,
                "caller_id": call.caller_id,
                "receiver_id": call.receiver_id,
                "start_time": call.start_time,
                "end_time": call.end_time,
                "duration_seconds": call.duration,
                "status": call.status
            }
            for call in calls
        ]
    }
# =========================
# DOCUMENT UPLOAD
# =========================

@app.post("/api/documents/upload")
def upload_document(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Only allow PDF files
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are allowed"
        )

    # Create the uploads folder
    upload_folder = "uploads"

    os.makedirs(upload_folder, exist_ok=True)

    # Save the PDF
    file_path = os.path.join(upload_folder, file.filename)

    with open(file_path, "wb") as buffer:
        buffer.write(file.file.read())

    # Save document information in database
    new_document = models.Document(
        user_id=current_user.id,
        filename=file.filename,
        filepath=file_path
    )

    db.add(new_document)
    db.commit()
    db.refresh(new_document)

    return {
        "message": "PDF uploaded successfully!",
        "document_id": new_document.id,
        "filename": new_document.filename
    }


# =========================
# GET DOCUMENT TEXT
# =========================

@app.get("/api/documents/{document_id}/text")
def get_document_text(
    document_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    document = db.query(models.Document).filter(
        models.Document.id == document_id
    ).first()

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Document not found"
        )

    # Make sure this document belongs to the logged-in user
    if document.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You cannot access this document"
        )

    try:
        reader = PdfReader(document.filepath)

        text = ""

        for page in reader.pages:
            page_text = page.extract_text()

            if page_text:
                text += page_text + "\n"

        return {
            "document_id": document.id,
            "filename": document.filename,
            "text": text
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Could not read PDF: {str(e)}"
        )


# =========================
# ASK AI ABOUT DOCUMENT
# =========================

@app.post("/api/documents/ask")
def ask_question(
    request: schemas.AskQuestionRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Check whether the document exists
    document = db.query(models.Document).filter(
        models.Document.id == request.document_id
    ).first()

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Document not found"
        )

    # Make sure this document belongs to the logged-in user
    if document.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You cannot access this document"
        )

    # Read PDF text
    try:
        reader = PdfReader(document.filepath)

        document_text = ""

        for page in reader.pages:
            page_text = page.extract_text()

            if page_text:
                document_text += page_text + "\n"

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Could not read PDF: {str(e)}"
        )

    if not document_text.strip():
        raise HTTPException(
            status_code=400,
            detail="Could not extract text from this PDF"
        )

    # Send document and question to Gemini
    prompt = f"""
You are answering a question based only on the provided document.

DOCUMENT:
{document_text}

QUESTION:
{request.question}

Answer the question clearly and simply using information from the document.
If the answer is not present in the document, say that the answer was not found in the document.
"""

    try:
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt
        )

        answer = response.text

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Gemini error: {str(e)}"
        )

    # Save question and answer
    new_qa = models.DocumentQA(
        user_id=current_user.id,
        document_id=request.document_id,
        question=request.question,
        answer=answer
    )

    db.add(new_qa)
    db.commit()
    db.refresh(new_qa)

    return {
        "message": "Question answered successfully!",
        "document_id": request.document_id,
        "question": request.question,
        "answer": answer,
        "qa_id": new_qa.id
    }


# =========================
# QA HISTORY
# =========================

@app.get("/api/documents/qa-history")
def get_qa_history(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    history = db.query(models.DocumentQA).filter(
        models.DocumentQA.user_id == current_user.id
    ).order_by(
        models.DocumentQA.id.desc()
    ).all()

    return {
        "user_id": current_user.id,
        "history": [
            {
                "qa_id": item.id,
                "document_id": item.document_id,
                "question": item.question,
                "answer": item.answer,
                "created_at": item.created_at
            }
            for item in history
        ]
    }
@app.get("/api/admin/dashboard")
def admin_dashboard(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    # Check admin role
    if current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Admin access required"
        )

    # Count total users
    total_users = db.query(models.User).count()

    # Count active subscriptions
    active_subscriptions = db.query(
        models.Subscription
    ).filter(
        models.Subscription.status == "active"
    ).count()

    # Calculate total wallet credits
    wallets = db.query(models.Wallet).all()

    total_wallet_balance = sum(
        wallet.balance for wallet in wallets
    )

    # Calculate total credits spent
    debit_transactions = db.query(
        models.WalletTransaction
    ).filter(
        models.WalletTransaction.transaction_type == "debit"
    ).all()

    total_spent = sum(
        transaction.amount
        for transaction in debit_transactions
    )

    # Count documents
    total_documents = db.query(
        models.Document
    ).count()

    # Count connection requests
    total_connection_requests = db.query(
        models.Connection
    ).count()

    # Count calls
    total_calls = db.query(
        models.Call
    ).count()

    return {
        "total_users": total_users,
        "active_subscriptions": active_subscriptions,
        "total_wallet_balance": total_wallet_balance,
        "total_spent": total_spent,
        "total_documents": total_documents,
        "total_connection_requests": total_connection_requests,
        "total_calls": total_calls
    }
@app.get("/api/connect/requests")
def get_connection_requests(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user_id = current_user.id

    requests = db.query(models.Connection).filter(
        models.Connection.receiver_id == user_id,
        models.Connection.status == "pending"
    ).all()

    result = []

    for request in requests:
        sender = db.query(models.User).filter(
            models.User.id == request.sender_id
        ).first()

        if sender:
            result.append({
                "connection_id": request.id,
                "sender_id": sender.id,
                "sender_name": sender.name,
                "sender_email": sender.email,
                "status": request.status
            })

    return {
        "user_id": current_user.id,
        "requests": result
    }
@app.get("/api/documents")
def get_documents(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    documents = db.query(models.Document).filter(
        models.Document.user_id == current_user.id
    ).order_by(models.Document.id.desc()).all()

    return {
        "user_id": current_user.id,
        "documents": [
            {
                "document_id": document.id,
                "filename": document.filename
            }
            for document in documents
        ]
    }
@app.get("/api/admin/users")
def admin_users(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    # Check admin role
    if current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Admin access required"
        )

    users = db.query(models.User).all()

    user_data = []

    for user in users:

        subscription = db.query(models.Subscription).filter(
            models.Subscription.user_id == user.id,
            models.Subscription.status == "active"
        ).first()

        wallet = db.query(models.Wallet).filter(
            models.Wallet.user_id == user.id
        ).first()

        user_data.append({
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "subscription": subscription.plan_name if subscription else "None",
            "wallet_balance": wallet.balance if wallet else 0
        })

    return {
        "users": user_data
    }