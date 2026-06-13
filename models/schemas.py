from pydantic import BaseModel
from typing import Optional
from enum import Enum


class AssistType(str, Enum):
    GROCERIES = "GROCERIES"
    TRANSPORT = "TRANSPORT"
    MEDICINE = "MEDICINE"
    FAMILY_CALL = "FAMILY_CALL"
    CAREGIVER = "CAREGIVER"


class RequestStatus(str, Enum):
    PENDING = "PENDING"
    ASSIGNED = "ASSIGNED"
    EN_ROUTE = "EN_ROUTE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str
    phone: str
    role: str
    lat: float
    lng: float
    age: Optional[int] = None


class CreateAssistanceRequest(BaseModel):
    type: AssistType
    elder_note: Optional[str] = None


class UpdateStatusRequest(BaseModel):
    status: RequestStatus


class UpdateLocationRequest(BaseModel):
    lat: float
    lng: float


class UpdateAvailabilityRequest(BaseModel):
    is_available: bool


class SimulateWellnessRequest(BaseModel):
    state: str

