from pydantic import BaseModel


class UserRegister(BaseModel):
    name: str
    email: str
    password: str
class UserLogin(BaseModel):
    email: str
    password: str
class SubscribeRequest(BaseModel):
    plan_id: int
class ConnectionRequest(BaseModel):
    receiver_id: int
class StartCallRequest(BaseModel):
    receiver_id: int
class AskQuestionRequest(BaseModel):
    document_id: int
    question: str