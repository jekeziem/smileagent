"""
SmileAgent API v4.0 - Emergency Triage + Cosmetic Booking
Features:
- NEW: Emergency Triage Flow (Manchester Triage adapted)
- NEW: Medical Card / PRSI clinic filtering
- NEW: Dentist-Ready Brief generation
- Treatment-specific pricing (Invisalign, Composite Bonding, Veneers)
- Med 2 tax eligibility check
- Payer details collection
- Med 2 PDF form filling
- Digital signature for dentists
- Email notification to clinics
"""
import os
from dotenv import load_dotenv

load_dotenv()

DEBUG = os.getenv("DEBUG", "false").lower() == "true"


import os
import json
import uuid
import re
import base64
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from enum import Enum
from math import radians, sin, cos, sqrt, atan2

from dotenv import load_dotenv
from cryptography.fernet import Fernet

from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Form, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field, validator

# --------------------------------------------------
# ENV / CONFIG
# --------------------------------------------------

load_dotenv()

DEBUG = os.getenv("DEBUG", "false").lower() == "true"

ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    ENCRYPTION_KEY = Fernet.generate_key().decode()
    print(f"⚠️  WARNING: Using auto-generated encryption key: {ENCRYPTION_KEY}")
    print("⚠️  Set ENCRYPTION_KEY in .env for production!")

cipher_suite = Fernet(
    ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY
)

# --------------------------------------------------
# APP INIT (MUST COME BEFORE DECORATORS)
# --------------------------------------------------

app = FastAPI()

# --------------------------------------------------
# UTILS
# --------------------------------------------------

def encrypt_field(data: str) -> str:
    if not data:
        return None
    return cipher_suite.encrypt(data.encode()).decode()

def decrypt_field(encrypted_data: str) -> str:
    if not encrypted_data:
        return None
    return cipher_suite.decrypt(encrypted_data.encode()).decode()

# --------------------------------------------------
# GLOBAL ERROR HANDLER
# --------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print(f"❌ Error: {exc}")
    if DEBUG:
        return JSONResponse(status_code=500, content={"detail": str(exc)})
    return JSONResponse(status_code=500, content={"detail": "An internal error occurred"})
# PDF manipulation
try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.colors import black, HexColor
    REPORTLAB_AVAILABLE = True
    print("✅ reportlab available - PDF generation enabled")
except ImportError:
    REPORTLAB_AVAILABLE = False
    print("⚠️ reportlab not installed - run: pip install reportlab")

# ============================================================
# APP INITIALIZATION
# ============================================================

app = FastAPI(title="SmileAgent API", version="4.0.0")
BASE_DIR = Path(__file__).resolve().parent

import os

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # ✅ Only your frontend
    allow_credentials=True,
    allow_methods=["GET", "POST"],  # ✅ Only methods you use
    allow_headers=["Content-Type"],
)

# Directories
BOOKINGS_FILE = BASE_DIR / "bookings.json"
SIGNATURES_FILE = BASE_DIR / "signatures.json"
BRIEFS_FILE = BASE_DIR / "briefs.json"
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUTS_DIR = BASE_DIR / "outputs"
CONSENTS_FILE = BASE_DIR / "consents.json"
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUTS_DIR.mkdir(exist_ok=True)

# ============================================================
# ENUMS FOR TRIAGE
# ============================================================

class UrgencyLevel(str, Enum):
    RED_AE = "red_ae"
    ORANGE_URGENT = "orange"
    YELLOW_SOON = "yellow"
    GREEN_ROUTINE = "green"

class RedFlag(str, Enum):
    BREATHING_DIFFICULTY = "breathing_difficulty"
    SWELLING_SPREADING = "swelling_spreading"
    FEVER_WITH_SWELLING = "fever_with_swelling"
    UNCONTROLLED_BLEEDING = "uncontrolled_bleeding"

# ============================================================
# CLINIC DATA - Extended with MC/Emergency fields
# ============================================================

CLINICS = [
    {
        "id": 1,
        "clinic_name": "Clondalkin Dental",
        "location": "Main Street, Clondalkin Village, Dublin 22",
        "eircode": "D22 Y2K8",
        "coordinates": {"lat": 53.3205, "lng": -6.3947},
        "phone": "+353 1 457 2000",
        "email": "info@clondalkin-dental.ie",
        "verified": True,
        "practitioner": {
            "name": "DR. SARAH MURPHY",
            "qualifications": "BDS NUI, MFDS RCSI",
            "registration_number": "12345"
        },
        "pricing": {
            "invisalign": 3200,
            "composite_bonding": 300,
            "veneers": 650,
            "emergency_exam": 95
        },
        "rating": 4.8,
        "review_count": 89,
        "top_review": "Excellent service. Dr. Murphy explained everything clearly and made me feel at ease.",
        "available_slots": ["Mon 9:00 AM", "Wed 2:00 PM", "Fri 11:00 AM"],
        "medical_card": {
            "accepts": True,
            "accepting_new_patients": True,
            "last_verified": "2026-01-15",
            "treatments_covered": ["exam", "extraction", "xray", "scale_polish"]
        },
        "prsi_dtbs": True,
        "emergency_slots": {
            "offers_same_day": True,
            "typical_wait_hours": 3
        },
        "hours": {
            "mon": "09:00-18:00", "tue": "09:00-18:00", "wed": "09:00-20:00",
            "thu": "09:00-18:00", "fri": "09:00-17:00", "sat": "10:00-14:00", "sun": None
        }
    },
    {
        "id": 2,
        "clinic_name": "Garvey's Tower Dental",
        "location": "Tower Road, Clondalkin, Dublin 22",
        "eircode": "D22 XF82",
        "coordinates": {"lat": 53.3187, "lng": -6.3892},
        "phone": "+353 1 459 3000",
        "email": "info@garveys-dental.ie",
        "verified": True,
        "practitioner": {
            "name": "DR. JAMES KELLY",
            "qualifications": "BDentSc TCD, MSc Ortho",
            "registration_number": "23456"
        },
        "pricing": {
            "invisalign": 3450,
            "composite_bonding": 280,
            "veneers": 600,
            "emergency_exam": 85
        },
        "rating": 4.7,
        "review_count": 67,
        "top_review": "Very professional clinic. The team is friendly and results exceeded expectations.",
        "available_slots": ["Tue 10:30 AM", "Thu 3:00 PM", "Sat 9:30 AM"],
        "medical_card": {
            "accepts": True,
            "accepting_new_patients": False,
            "last_verified": "2026-01-10",
            "treatments_covered": ["exam", "extraction", "xray"]
        },
        "prsi_dtbs": True,
        "emergency_slots": {
            "offers_same_day": True,
            "typical_wait_hours": 2
        },
        "hours": {
            "mon": "08:00-17:00", "tue": "08:00-17:00", "wed": "08:00-17:00",
            "thu": "08:00-19:00", "fri": "08:00-16:00", "sat": None, "sun": None
        }
    },
    {
        "id": 3,
        "clinic_name": "Newland's Dental",
        "location": "Newlands Cross, Clondalkin, Dublin 22",
        "eircode": "D22 P3W9",
        "coordinates": {"lat": 53.3098, "lng": -6.3756},
        "phone": "+353 1 464 1000",
        "email": "info@newlands-dental.ie",
        "verified": True,
        "practitioner": {
            "name": "DR. AOIFE BRENNAN",
            "qualifications": "BDS UCC, MOrth RCS Edin",
            "registration_number": "34567"
        },
        "pricing": {
            "invisalign": 2950,
            "composite_bonding": 320,
            "veneers": 700,
            "emergency_exam": 90
        },
        "rating": 4.9,
        "review_count": 112,
        "top_review": "Amazing experience from start to finish. Dr. Brennan is incredibly skilled.",
        "available_slots": ["Mon 2:00 PM", "Wed 11:30 AM", "Fri 4:00 PM"],
        "medical_card": {
            "accepts": False,
            "accepting_new_patients": False,
            "last_verified": "2026-01-12",
            "treatments_covered": []
        },
        "prsi_dtbs": True,
        "emergency_slots": {
            "offers_same_day": True,
            "typical_wait_hours": 4
        },
        "hours": {
            "mon": "09:00-18:00", "tue": "09:00-18:00", "wed": "09:00-18:00",
            "thu": "09:00-18:00", "fri": "09:00-17:00", "sat": "09:00-13:00", "sun": None
        }
    }
]

TREATMENTS = {
    "invisalign": {
        "name": "Invisalign", "display_name": "Invisalign",
        "description": "Clear aligners for teeth straightening",
        "med2_eligible": True, "med2_category": "H",
        "med2_category_name": "Orthodontic Treatment", "pricing_type": "fixed"
    },
    "composite_bonding": {
        "name": "Composite Bonding", "display_name": "Composite Bonding",
        "description": "Tooth-colored resin to repair or reshape teeth",
        "med2_eligible": True, "med2_category": "B",
        "med2_category_name": "Veneers / Etched Fillings", "pricing_type": "per_tooth"
    },
    "veneers": {
        "name": "Veneers", "display_name": "Veneers",
        "description": "Porcelain shells to cover front of teeth",
        "med2_eligible": True, "med2_category": "B",
        "med2_category_name": "Veneers / Etched Fillings", "pricing_type": "per_tooth"
    },
    "whitening": {
        "name": "Whitening", "display_name": "Teeth Whitening",
        "description": "Professional teeth whitening treatment",
        "med2_eligible": False, "med2_category": None,
        "med2_category_name": None, "pricing_type": "fixed"
    },
    "emergency_exam": {
        "name": "Emergency Exam", "display_name": "Emergency Exam + X-Ray",
        "description": "Urgent dental assessment with X-rays",
        "med2_eligible": True, "med2_category": "A",
        "med2_category_name": "Routine Oral Examination", "pricing_type": "fixed"
    }
}

# ============================================================
# PYDANTIC MODELS
# ============================================================

class TriageInput(BaseModel):
    red_flags: List[str] = []
    pain_level: int = Field(..., ge=1, le=10)
    pain_worsening: bool = False
    sleep_disrupted: bool = False
    symptom_duration_hours: int = 24
    chief_complaint: str = ""
    visible_damage: bool = False

class TriageOutput(BaseModel):
    urgency: str
    urgency_display: str
    recommended_timeframe: str
    reasoning: str
    show_ae_redirect: bool
    self_care_tips: List[str] = []

class EmergencyClinicSearch(BaseModel):
    latitude: float
    longitude: float
    urgency: str = "green"
    medical_card_only: bool = False
    prsi_only: bool = False
    max_distance_km: float = 15.0

class BriefInput(BaseModel):
    patient_name: Optional[str] = None
    patient_phone: str
    contact_preference: str = "sms"
    chief_complaint: str
    pain_level: int
    pain_worsening: bool = False
    urgency: str
    urgency_display: str
    symptom_duration_hours: int = 24
    sensitive_to_temp: Optional[bool] = None
    previous_treatment: Optional[str] = None
    payment_type: str = "private"
    medical_card_last4: Optional[str] = None
    requested_date: str = "Today"
    requested_time_preference: str = "any"
    clinic_id: int
    clinic_name: str

class TaxEligibilityCheck(BaseModel):
    who_is_paying: str
    pays_irish_tax: str
    payer_name: Optional[str] = None
    payer_ppsn: Optional[str] = None
    payer_address: Optional[str] = None
    payer_relationship: Optional[str] = None

class BookingRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    phone: str
    email: Optional[str] = None
    ppsn: str
    address: str = Field(..., min_length=10, max_length=300)
    clinic_id: int = Field(..., ge=1)
    clinic_name: str
    treatment: str
    selected_slot: str
    photo_id: Optional[str] = None
    who_is_paying: str = "self"
    pays_irish_tax: str = "paye"
    is_eligible_for_relief: bool = True
    payer_name: Optional[str] = None
    payer_ppsn: Optional[str] = None
    payer_address: Optional[str] = None
    payer_relationship: Optional[str] = None
    additional_interests: Optional[List[str]] = None
    estimated_cost: float = Field(..., ge=0)
    is_emergency: bool = False
    triage_brief_id: Optional[str] = None
    
    @validator('ppsn')
    def validate_ppsn(cls, v):
        clean = v.replace(' ', '').upper()
        if not re.match(r'^\d{7}[A-Z]{1,2}$', clean):
            raise ValueError('PPSN must be 7 digits + 1-2 letters')
        return clean
    
    @validator('phone')
    def validate_phone(cls, v):
        digits = ''.join(c for c in v if c.isdigit())
        if digits.startswith('353'):
            digits = digits[3:]
        if digits.startswith('0'):
            digits = digits[1:]
        if len(digits) < 9:
            raise ValueError('Phone number too short')
        return f'+353{digits[-9:]}'

class SignatureSubmission(BaseModel):
    booking_id: str
    signature_data: str
    signed_date: str

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def get_clinic_by_id(clinic_id: int):
    for clinic in CLINICS:
        if clinic["id"] == clinic_id:
            return clinic
    return None

def calculate_med2_relief(gross_cost: float) -> dict:
    relief_amount = gross_cost * 0.20
    net_cost = gross_cost - relief_amount
    return {
        "gross_cost": round(gross_cost, 2),
        "relief_rate": 0.20,
        "relief_amount": round(relief_amount, 2),
        "net_cost": round(net_cost, 2)
    }

def number_to_words(amount: int) -> str:
    ones = ['', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine',
            'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen',
            'seventeen', 'eighteen', 'nineteen']
    tens = ['', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety']
    
    if amount < 20:
        return ones[amount]
    elif amount < 100:
        return tens[amount // 10] + ('' if amount % 10 == 0 else '-' + ones[amount % 10])
    elif amount < 1000:
        return ones[amount // 100] + ' hundred' + ('' if amount % 100 == 0 else ' and ' + number_to_words(amount % 100))
    elif amount < 10000:
        return number_to_words(amount // 1000) + ' thousand' + ('' if amount % 1000 == 0 else ' ' + number_to_words(amount % 1000))
    else:
        return str(amount)

def save_booking(booking_data: dict) -> dict:
    bookings = []
    if BOOKINGS_FILE.exists():
        try:
            bookings = json.loads(BOOKINGS_FILE.read_text())
        except:
            bookings = []
    
    booking_data['booking_id'] = datetime.now().strftime("%Y%m%d%H%M%S") + str(uuid.uuid4())[:4]
    booking_data['created_at'] = datetime.now().isoformat()
    booking_data['status'] = 'confirmed'
    booking_data['signature_status'] = 'pending'
    
    bookings.append(booking_data)
    BOOKINGS_FILE.write_text(json.dumps(bookings, indent=2))
    
    print(f"\n{'='*50}")
    print(f"🎉 NEW BOOKING: {booking_data['name']}")
    print(f"📍 Clinic: {booking_data['clinic_name']}")
    print(f"⏰ Time: {booking_data['selected_slot']}")
    print(f"💰 Treatment: {booking_data['treatment']}")
    if booking_data.get('is_emergency'):
        print(f"🚨 Emergency: Yes")
    print(f"{'='*50}\n")
    
    return booking_data

def get_booking_by_id(booking_id: str) -> Optional[dict]:
    if not BOOKINGS_FILE.exists():
        return None
    try:
        bookings = json.loads(BOOKINGS_FILE.read_text())
        for booking in bookings:
            if booking.get('booking_id') == booking_id:
                return booking
    except:
        pass
    return None

def update_booking(booking_id: str, updates: dict) -> bool:
    if not BOOKINGS_FILE.exists():
        return False
    try:
        bookings = json.loads(BOOKINGS_FILE.read_text())
        for i, booking in enumerate(bookings):
            if booking.get('booking_id') == booking_id:
                bookings[i].update(updates)
                BOOKINGS_FILE.write_text(json.dumps(bookings, indent=2))
                return True
    except:
        pass
    return False

# ============================================================
# TRIAGE ENGINE
# ============================================================

def get_urgent_self_care() -> List[str]:
    return [
        "Take over-the-counter pain relief (ibuprofen or paracetamol) as directed",
        "Avoid very hot or cold foods and drinks",
        "If swelling, apply a cold compress to the outside of your cheek",
        "Do not place aspirin directly on gums",
    ]

def get_moderate_self_care() -> List[str]:
    return [
        "Rinse with warm salt water (1/2 teaspoon salt in 8oz water)",
        "Take over-the-counter pain relief if needed",
        "Avoid chewing on the affected side",
    ]

def get_routine_self_care() -> List[str]:
    return [
        "Maintain normal brushing and flossing",
        "Note any changes in symptoms",
    ]

def assess_triage(triage_input: TriageInput) -> dict:
    """Core triage logic - rules-based, no AI. Routes, does NOT diagnose."""
    
    if triage_input.red_flags:
        return {
            "urgency": UrgencyLevel.RED_AE.value,
            "urgency_display": "Emergency - Hospital Required",
            "recommended_timeframe": "Immediately",
            "reasoning": "Your symptoms suggest a potentially serious condition that needs hospital assessment.",
            "show_ae_redirect": True,
            "self_care_tips": []
        }
    
    pl = triage_input.pain_level
    pw = triage_input.pain_worsening
    sd = triage_input.sleep_disrupted
    
    if (pl >= 7 and pw) or (pl >= 8) or (pl >= 6 and sd):
        return {
            "urgency": UrgencyLevel.ORANGE_URGENT.value,
            "urgency_display": "Urgent",
            "recommended_timeframe": "Within 24 hours",
            "reasoning": "Based on your pain level and symptoms, you should be seen as soon as possible.",
            "show_ae_redirect": False,
            "self_care_tips": get_urgent_self_care()
        }
    
    if pl >= 4 or triage_input.visible_damage:
        return {
            "urgency": UrgencyLevel.YELLOW_SOON.value,
            "urgency_display": "Soon",
            "recommended_timeframe": "Within 2-3 days",
            "reasoning": "Your symptoms should be assessed soon, but are not immediately urgent.",
            "show_ae_redirect": False,
            "self_care_tips": get_moderate_self_care()
        }
    
    return {
        "urgency": UrgencyLevel.GREEN_ROUTINE.value,
        "urgency_display": "Routine",
        "recommended_timeframe": "Within 1-2 weeks",
        "reasoning": "Your symptoms don't appear urgent, but should still be checked.",
        "show_ae_redirect": False,
        "self_care_tips": get_routine_self_care()
    }

# ============================================================
# CLINIC MATCHER
# ============================================================

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    return R * c

def check_if_open(hours: dict) -> bool:
    now = datetime.now()
    day_map = {0: 'mon', 1: 'tue', 2: 'wed', 3: 'thu', 4: 'fri', 5: 'sat', 6: 'sun'}
    day = day_map.get(now.weekday(), 'mon')
    day_hours = hours.get(day)
    if day_hours is None:
        return False
    try:
        open_time, close_time = day_hours.split("-")
        current_time = now.strftime("%H:%M")
        return open_time <= current_time <= close_time
    except:
        return False

def match_clinics_for_emergency(search: EmergencyClinicSearch) -> List[dict]:
    matches = []
    
    for clinic in CLINICS:
        distance = haversine_distance(
            search.latitude, search.longitude,
            clinic["coordinates"]["lat"], clinic["coordinates"]["lng"]
        )
        
        if distance > search.max_distance_km:
            continue
        
        mc_info = clinic.get("medical_card", {})
        if search.medical_card_only and not mc_info.get("accepts", False):
            continue
        
        if search.prsi_only and not clinic.get("prsi_dtbs", False):
            continue
        
        emergency_info = clinic.get("emergency_slots", {})
        emergency_suitable = True
        if search.urgency in [UrgencyLevel.RED_AE.value, UrgencyLevel.ORANGE_URGENT.value]:
            emergency_suitable = emergency_info.get("offers_same_day", False)
        
        match = {
            "id": clinic["id"],
            "clinic_name": clinic["clinic_name"],
            "location": clinic["location"],
            "eircode": clinic["eircode"],
            "phone": clinic["phone"],
            "email": clinic.get("email"),
            "distance_km": round(distance, 1),
            "rating": clinic.get("rating"),
            "review_count": clinic.get("review_count"),
            "verified": clinic.get("verified", False),
            "practitioner": clinic.get("practitioner", {}),
            "accepts_medical_card": mc_info.get("accepts", False),
            "mc_accepting_new": mc_info.get("accepting_new_patients", False),
            "mc_last_verified": mc_info.get("last_verified"),
            "accepts_prsi": clinic.get("prsi_dtbs", False),
            "has_emergency_slots": emergency_info.get("offers_same_day", False),
            "typical_wait_hours": emergency_info.get("typical_wait_hours"),
            "is_open_now": check_if_open(clinic.get("hours", {})),
            "emergency_suitable": emergency_suitable,
            "pricing": clinic.get("pricing", {}),
            "available_slots": clinic.get("available_slots", [])
        }
        
        matches.append((match, distance, emergency_suitable))
    
    matches.sort(key=lambda x: (not x[2], x[1]))
    return [m[0] for m in matches]

# ============================================================
# BRIEF GENERATOR
# ============================================================

def yes_no(val):
    if val is None:
        return "Not specified"
    return "Yes" if val else "No"


def generate_brief(brief_input: BriefInput) -> dict:
    """Generate a patient brief for the clinic."""
    brief_id = datetime.now().strftime("%Y%m%d%H%M%S") + str(uuid.uuid4())[:4]
    
    brief = {
        "brief_id": brief_id,
        "patient_name": encrypt_field(brief_input.patient_name) if brief_input.patient_name else None,
        "patient_phone": encrypt_field(brief_input.patient_phone),
        "contact_preference": brief_input.contact_preference,
        "chief_complaint": encrypt_field(brief_input.chief_complaint),
        "pain_level": brief_input.pain_level,
        "pain_worsening": brief_input.pain_worsening,
        "urgency": brief_input.urgency,
        "urgency_display": brief_input.urgency_display,
        "symptom_duration_hours": brief_input.symptom_duration_hours,
        "sensitive_to_temp": brief_input.sensitive_to_temp,
        "previous_treatment": encrypt_field(brief_input.previous_treatment) if brief_input.previous_treatment else None,
        "payment_type": brief_input.payment_type,
        "medical_card_last4": brief_input.medical_card_last4,
        "requested_date": brief_input.requested_date,
        "requested_time_preference": brief_input.requested_time_preference,
        "clinic_id": brief_input.clinic_id,
        "clinic_name": brief_input.clinic_name,
        "generated_at": datetime.now().isoformat(),
        "status": "pending"
    }
    
    briefs = []
    if BRIEFS_FILE.exists():
        try:
            briefs = json.loads(BRIEFS_FILE.read_text())
        except:
            briefs = []
    
    briefs.append(brief)
    BRIEFS_FILE.write_text(json.dumps(briefs, indent=2))
    
    print(f"\n{'='*50}")
    print(f"EMERGENCY BRIEF: {brief_id}")
    print(f"Clinic: {brief_input.clinic_name}")
    print(f"Urgency: {brief_input.urgency_display}")
    print(f"{'='*50}\n")
    
    return brief


def format_brief_for_email(brief: dict) -> str:
    """Format a brief into a readable string for email."""
    patient_name = decrypt_field(brief.get('patient_name')) if brief.get('patient_name') else 'Not provided'
    patient_phone = decrypt_field(brief.get('patient_phone'))
    chief_complaint = decrypt_field(brief.get('chief_complaint'))
    previous_treatment = decrypt_field(brief.get('previous_treatment')) if brief.get('previous_treatment') else 'None mentioned'

    urgency_map = {"orange": "[URGENT]", "yellow": "[SOON]", "green": "[ROUTINE]", "red_ae": "[EMERGENCY]"}
    urgency_label = urgency_map.get(brief["urgency"], "[UNKNOWN]")

    return f"""
SMILEAGENT PATIENT BRIEF
Ref: {brief['brief_id']} | Generated: {brief['generated_at'][:16].replace('T', ' ')}

PATIENT CONTACT
--------------
Name: {patient_name}
Phone: {patient_phone}
Preferred contact: {brief['contact_preference'].upper()}
Requested: {brief['requested_date']} ({brief['requested_time_preference']})

CLINICAL SUMMARY
----------------
{urgency_label} Urgency: {brief['urgency_display']}
Pain Level: {brief['pain_level']}/10 {'(worsening)' if brief['pain_worsening'] else ''}
Duration: {brief['symptom_duration_hours']} hours
Chief Complaint: {chief_complaint}
Sensitive to temp: {yes_no(brief.get('sensitive_to_temp'))}
Previous treatment: {previous_treatment}

PAYMENT
-------
Type: {brief['payment_type'].upper()}
{'Medical Card (last 4): ' + brief['medical_card_last4'] if brief.get('medical_card_last4') else ''}

---
Generated by SmileAgent Emergency Triage
"""


def send_clinic_email(booking: dict, clinic: dict, signature_link: str, brief: dict = None):
    """Send email notification to clinic (simulated for MVP)."""
    clinic_email = clinic.get('email', 'unknown@clinic.ie')
    clinic_name = clinic.get('clinic_name', 'Unknown Clinic')
    
    if brief:
        email_body = format_brief_for_email(brief)
        subject = f"SmileAgent Emergency: {brief.get('urgency_display', 'Urgent')} - New Patient"
    else:
        subject = f"New SmileAgent Booking: {booking.get('name', 'Patient')}"
        email_body = f"""
NEW BOOKING via SmileAgent
--------------------------
Patient: {booking.get('name')}
Phone: {booking.get('phone')}
Email: {booking.get('email', 'Not provided')}
Treatment: {booking.get('treatment')}
Time: {booking.get('selected_slot')}
Estimated Cost: EUR {booking.get('estimated_cost', 0):.2f}

Digital Signature Link: {signature_link}

---
SmileAgent Booking System
"""
    
    print(f"\n{'='*50}")
    print(f"EMAIL TO CLINIC (Simulated)")
    print(f"{'='*50}")
    print(f"To: {clinic_email}")
    print(f"Subject: {subject}")
    print(f"{'='*50}")
    print(email_body)
    print(f"{'='*50}\n")


# ============================================================
# PDF GENERATION
# ============================================================

def generate_med2_pdf(booking: dict, clinic: dict) -> tuple:
    if not REPORTLAB_AVAILABLE:
        return None, None
    
    booking_id = booking.get('booking_id', 'unknown')
    filename = f"Med2_SmileAgent_{booking_id}.pdf"
    filepath = OUTPUTS_DIR / filename
    
    width, height = A4
    c = canvas.Canvas(str(filepath), pagesize=A4)
    
    if booking.get('who_is_paying') == 'other_paying_for_me' and booking.get('payer_name'):
        claimant_name = booking.get('payer_name', '').upper()
        claimant_ppsn = booking.get('payer_ppsn', '')
        claimant_address = booking.get('payer_address', '')
    else:
        claimant_name = booking.get('name', '').upper()
        claimant_ppsn = booking.get('ppsn', '')
        claimant_address = booking.get('address', '')
    
    treatment_key = booking.get('treatment', 'invisalign')
    treatment_info = TREATMENTS.get(treatment_key, TREATMENTS['invisalign'])
    med2_category = treatment_info.get('med2_category', 'H')
    cost = booking.get('estimated_cost', 0)
    treatment_date = datetime.now().strftime("%d/%m/%Y")
    
    # PAGE 1: Cover
    c.setFillColor(HexColor('#059669'))
    c.rect(0, height - 70, width, 70, fill=True, stroke=False)
    c.setFillColor(HexColor('#FFFFFF'))
    c.setFont("Helvetica-Bold", 22)
    c.drawString(30, height - 45, "SmileAgent")
    c.setFont("Helvetica", 11)
    c.drawString(30, height - 62, "Your Pre-Filled Med 2 Tax Relief Form")
    
    c.setFillColor(black)
    y = height - 110
    c.setFont("Helvetica-Bold", 16)
    c.drawString(30, y, "Important Instructions")
    y -= 30
    
    c.setFont("Helvetica", 11)
    instructions = [
        "This Med 2 form has been pre-filled with your details by SmileAgent.",
        "", "WHAT HAPPENS NEXT:", "",
        "1. Attend your dental consultation", "",
        "2. After treatment, your dentist will sign this form digitally", "",
        "3. Once signed, you'll receive the completed form by email", "",
        "4. Use the signed form to claim your tax relief via Revenue.ie", "", "",
        "YOUR TAX RELIEF SUMMARY:"
    ]
    for line in instructions:
        c.drawString(30, y, line)
        y -= 16
    
    y -= 10
    c.setFillColor(HexColor('#ECFDF5'))
    c.rect(30, y - 80, 300, 90, fill=True, stroke=False)
    c.setStrokeColor(HexColor('#059669'))
    c.rect(30, y - 80, 300, 90, fill=False, stroke=True)
    
    relief = calculate_med2_relief(cost)
    c.setFillColor(black)
    c.setFont("Helvetica", 11)
    c.drawString(45, y - 20, f"Treatment Cost:")
    c.drawString(200, y - 20, f"€{cost:,.2f}")
    c.setFillColor(HexColor('#059669'))
    c.drawString(45, y - 40, f"Tax Relief (20%):")
    c.drawString(200, y - 40, f"-€{relief['relief_amount']:,.2f}")
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(45, y - 65, f"Your Net Cost:")
    c.drawString(200, y - 65, f"€{relief['net_cost']:,.2f}")
    
    c.setFont("Helvetica", 9)
    c.setFillColor(HexColor('#666666'))
    c.drawString(30, 80, f"Generated by SmileAgent on {datetime.now().strftime('%d %B %Y at %H:%M')}")
    c.drawString(30, 65, f"Booking Reference: {booking_id}")
    
    c.showPage()
    
    # PAGE 2: Med 2 Form
    c.setFillColor(HexColor('#1a472a'))
    c.rect(0, height - 50, width, 50, fill=True, stroke=False)
    c.setFillColor(HexColor('#FFFFFF'))
    c.setFont("Helvetica-Bold", 12)
    c.drawString(30, height - 32, "Form MED 2 - Dental Expenses Certified by Dental Practitioner")
    
    y = height - 75
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(30, y, "Claimant's Name and Address")
    c.setStrokeColor(black)
    c.setLineWidth(0.5)
    c.rect(30, y - 55, 230, 50, stroke=True, fill=False)
    c.setFont("Helvetica", 9)
    c.drawString(35, y - 15, claimant_name)
    
    address_lines = claimant_address.split(',') if claimant_address else ['']
    addr_y = y - 28
    for line in address_lines[:3]:
        c.drawString(35, addr_y, line.strip().upper()[:40])
        addr_y -= 11
    
    c.setFont("Helvetica", 7)
    c.drawString(280, y, "Note: This form is a receipt and should be")
    c.drawString(280, y - 9, "retained by you as evidence of expenses.")
    
    y -= 70
    c.setFont("Helvetica-Bold", 9)
    c.drawString(30, y, "PPSN")
    ppsn = claimant_ppsn.upper().replace(' ', '')
    box_x = 65
    box_size = 16
    for i in range(9):
        c.rect(box_x + (i * (box_size + 2)), y - 15, box_size, box_size, stroke=True, fill=False)
        if i < len(ppsn):
            c.setFont("Helvetica", 10)
            c.drawString(box_x + (i * (box_size + 2)) + 4, y - 12, ppsn[i])
    
    y -= 45
    c.setFont("Helvetica-Bold", 7)
    headers = ["Nature of", "Insert ☒", "Date(s) treatment", "Date(s) payments", "Amount paid"]
    col_x = [30, 75, 120, 220, 320]
    c.rect(30, y - 25, 510, 25, stroke=True, fill=False)
    for i, h in enumerate(headers):
        c.drawString(col_x[i] + 3, y - 10, h)
    
    y -= 25
    categories = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J']
    row_height = 20
    for cat in categories:
        c.rect(30, y - row_height, 45, row_height, stroke=True, fill=False)
        c.rect(75, y - row_height, 45, row_height, stroke=True, fill=False)
        c.rect(120, y - row_height, 100, row_height, stroke=True, fill=False)
        c.rect(220, y - row_height, 100, row_height, stroke=True, fill=False)
        c.rect(320, y - row_height, 220, row_height, stroke=True, fill=False)
        
        c.setFont("Helvetica-Bold", 12)
        c.drawString(48, y - 14, cat)
        c.rect(90, y - 16, 12, 12, stroke=True, fill=False)
        
        if cat == med2_category:
            c.setFont("Helvetica-Bold", 10)
            c.drawString(92, y - 14, "✓")
            c.setFont("Helvetica", 8)
            c.drawString(125, y - 12, treatment_date)
            c.drawString(225, y - 12, treatment_date)
            c.drawString(325, y - 12, f"€{cost:,.2f}")
        
        y -= row_height
    
    y -= 25
    practitioner = clinic.get('practitioner', {})
    c.setFont("Helvetica-Bold", 8)
    c.drawString(30, y, "Signature of Dental Practitioner")
    c.rect(170, y - 3, 150, 20, stroke=True, fill=False)
    c.setFont("Helvetica", 7)
    c.drawString(175, y + 2, "[Digital signature pending]")
    
    y -= 30
    c.setFont("Helvetica-Bold", 7)
    c.drawString(30, y, "Name and Address of Dental Practitioner")
    c.rect(30, y - 40, 220, 38, stroke=True, fill=False)
    c.setFont("Helvetica", 8)
    c.drawString(35, y - 12, practitioner.get('name', ''))
    c.drawString(35, y - 23, clinic.get('location', '')[:40])
    c.drawString(35, y - 34, clinic.get('eircode', ''))
    
    c.setFont("Helvetica-Bold", 7)
    c.drawString(270, y, "Qualifications")
    c.rect(270, y - 18, 200, 16, stroke=True, fill=False)
    c.setFont("Helvetica", 8)
    c.drawString(275, y - 14, practitioner.get('qualifications', ''))
    
    y -= 50
    c.setFont("Helvetica-Bold", 7)
    c.drawString(30, y, "Dental Council Reg No")
    c.rect(140, y - 3, 80, 16, stroke=True, fill=False)
    c.setFont("Helvetica", 9)
    c.drawString(145, y, practitioner.get('registration_number', ''))
    
    c.drawString(270, y, "Total Amount paid")
    c.rect(380, y - 3, 80, 16, stroke=True, fill=False)
    c.drawString(385, y, f"€{cost:,.2f}")
    
    y -= 25
    c.setFont("Helvetica-Bold", 7)
    c.drawString(30, y, "Amount in words")
    c.rect(30, y - 18, 510, 16, stroke=True, fill=False)
    c.setFont("Helvetica", 8)
    amount_words = number_to_words(int(cost)) + " euro"
    c.drawString(35, y - 14, amount_words.upper())
    
    y -= 40
    c.setFillColor(HexColor('#059669'))
    c.setFont("Helvetica-Bold", 7)
    c.drawString(30, y, "PRE-FILLED BY SMILEAGENT — Dentist signature required after treatment")
    
    c.save()
    print(f"📄 Med 2 PDF generated: {filename}")
    return str(filepath), filename

# ============================================================
# API ENDPOINTS
# ============================================================

@app.get("/")
def serve_index():
    index = BASE_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return HTMLResponse("<h1>SmileAgent API v4.0</h1><p>index.html not found</p>")

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "version": "4.0.0",
        "pdf_enabled": REPORTLAB_AVAILABLE,
        "clinics_loaded": len(CLINICS),
        "treatments_loaded": len(TREATMENTS),
        "features": ["cosmetic_booking", "emergency_triage", "medical_card_filter", "dentist_brief"]
    }

@app.get("/api/treatments")
def get_treatments():
    return {"treatments": TREATMENTS}

@app.get("/api/clinics")
def get_clinics(treatment: Optional[str] = None):
    result = []
    for clinic in CLINICS:
        clinic_data = {
            "id": clinic["id"],
            "clinic_name": clinic["clinic_name"],
            "location": clinic["location"],
            "eircode": clinic["eircode"],
            "phone": clinic["phone"],
            "verified": clinic["verified"],
            "rating": clinic["rating"],
            "review_count": clinic["review_count"],
            "top_review": clinic["top_review"],
            "available_slots": clinic["available_slots"],
            "accepts_medical_card": clinic.get("medical_card", {}).get("accepts", False),
            "mc_accepting_new": clinic.get("medical_card", {}).get("accepting_new_patients", False),
            "mc_last_verified": clinic.get("medical_card", {}).get("last_verified"),
            "accepts_prsi": clinic.get("prsi_dtbs", False),
            "has_emergency_slots": clinic.get("emergency_slots", {}).get("offers_same_day", False)
        }
        
        if treatment and treatment in clinic.get("pricing", {}):
            clinic_data["price"] = clinic["pricing"][treatment]
            clinic_data["treatment"] = treatment
        else:
            clinic_data["pricing"] = clinic.get("pricing", {})
        
        result.append(clinic_data)
    
    return {"clinics": result}

# ============================================================
# NEW: TRIAGE ENDPOINTS
# ============================================================

@app.post("/api/triage/assess", response_model=TriageOutput)
async def run_triage(triage_input: TriageInput):
    """Process triage input and return urgency assessment."""
    try:
        result = assess_triage(triage_input)
        return TriageOutput(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Triage assessment failed: {str(e)}")

@app.post("/api/clinics/emergency")
async def search_emergency_clinics(search: EmergencyClinicSearch):
    """Search clinics with emergency/MC filters."""
    try:
        results = match_clinics_for_emergency(search)
        return {"clinics": results, "count": len(results)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Clinic search failed: {str(e)}")

@app.post("/api/briefs/generate")
async def create_brief(brief_input: BriefInput, background_tasks: BackgroundTasks):
    """Generate patient brief and queue email to clinic."""
    try:
        brief = generate_brief(brief_input)
        clinic = get_clinic_by_id(brief_input.clinic_id)
        
        if clinic:
            background_tasks.add_task(
                send_clinic_email,
                booking={},
                clinic=clinic,
                signature_link=f"/sign/emergency-{brief['brief_id']}",
                brief=brief
            )
        
        return brief
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
# ============================================================
# CONSENT LOGGING (GDPR)
# ============================================================

class ConsentLog(BaseModel):
    user_identifier: str
    consent_type: str
    consent_given: bool
    consent_version: str = "v1.0"
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

def log_consent(consent: ConsentLog) -> dict:
    """Log GDPR consent with timestamp"""
    consents = []
    if CONSENTS_FILE.exists():
        try:
            consents = json.loads(CONSENTS_FILE.read_text())
        except:
            consents = []
    
    hashed_id = hashlib.sha256(consent.user_identifier.encode()).hexdigest()[:16]
    
    consent_record = {
        "consent_id": str(uuid.uuid4())[:8],
        "user_hash": hashed_id,
        "consent_type": consent.consent_type,
        "consent_given": consent.consent_given,
        "consent_version": consent.consent_version,
        "timestamp": datetime.now().isoformat(),
        "ip_address": consent.ip_address,
        "user_agent": consent.user_agent
    }
    
    consents.append(consent_record)
    CONSENTS_FILE.write_text(json.dumps(consents, indent=2))
    
    print(f"✅ Consent logged: {consent.consent_type} - {hashed_id}")
    return consent_record

@app.post("/api/consent/log")
async def log_user_consent(consent: ConsentLog, request: Request):
    """Log GDPR consent"""
    try:
        consent.ip_address = request.client.host
        consent.user_agent = request.headers.get("user-agent", "")[:100]
        record = log_consent(consent)
        return {"status": "success", "consent_id": record["consent_id"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# EXISTING ENDPOINTS (preserved)
# ============================================================

# ============================================================
# EXISTING ENDPOINTS (preserved)
# ============================================================

@app.post("/api/analyze-smile")
async def analyze_smile(file: UploadFile = File(...), save_for_med2: bool = Form(default=False)):
    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(400, detail="File must be an image")
    
    photo_id = str(uuid.uuid4())
    ext = file.filename.split('.')[-1] if file.filename else 'jpg'
    filepath = UPLOAD_DIR / f"{photo_id}.{ext}"
    
    content = await file.read()
    filepath.write_bytes(content)
    
    print(f"📸 Photo uploaded: {photo_id}")
    
    diagnosis = {
        "confidence_score": 92,
        "primary_issue": "Mild Crowding",
        "recommended_treatment": "invisalign",
        "notes": "Based on the scan, we detected mild crowding that could be corrected with Invisalign."
    }
    
    return {
        "status": "success",
        "photo_id": photo_id,
        "saved_for_med2": save_for_med2,
        "diagnosis": diagnosis
    }

@app.post("/api/check-eligibility")
async def check_tax_eligibility(check: TaxEligibilityCheck):
    is_eligible = False
    message = ""
    strategy_tip = None
    
    if check.who_is_paying == "self":
        if check.pays_irish_tax in ["paye", "self_assessed"]:
            is_eligible = True
            message = "You're eligible for Med 2 tax relief. You can claim 20% back."
        else:
            message = "Based on your details, you are not eligible for Med 2 tax relief."
            strategy_tip = "If a tax-paying family member pays instead, THEY can claim the 20% relief."
    elif check.who_is_paying == "paying_for_other":
        if check.pays_irish_tax in ["paye", "self_assessed"]:
            is_eligible = True
            message = "You're eligible to claim Med 2 relief for someone else's treatment."
        else:
            message = "Based on your details, you are not eligible for Med 2 tax relief."
    elif check.who_is_paying == "other_paying_for_me":
        if check.pays_irish_tax in ["paye", "self_assessed"]:
            is_eligible = True
            message = "The person paying is eligible to claim Med 2 tax relief."
        else:
            message = "Based on the payer's details, they are not eligible."
            strategy_tip = "If a different tax-paying family member pays, they could claim the relief."
    
    return {
        "is_eligible": is_eligible,
        "message": message,
        "strategy_tip": strategy_tip,
        "relief_rate": 0.20 if is_eligible else 0
    }

@app.post("/api/book-appointment")
async def book_appointment(booking: BookingRequest):
    clinic = get_clinic_by_id(booking.clinic_id)
    if not clinic:
        raise HTTPException(404, detail="Clinic not found")
    
    relief = calculate_med2_relief(booking.estimated_cost)
    
    booking_data = {
        "name": booking.name,
        "phone": booking.phone,
        "email": booking.email,
        "ppsn": booking.ppsn,
        "address": booking.address,
        "clinic_id": booking.clinic_id,
        "clinic_name": booking.clinic_name,
        "treatment": booking.treatment,
        "selected_slot": booking.selected_slot,
        "photo_id": booking.photo_id,
        "who_is_paying": booking.who_is_paying,
        "pays_irish_tax": booking.pays_irish_tax,
        "is_eligible_for_relief": booking.is_eligible_for_relief,
        "payer_name": booking.payer_name,
        "payer_ppsn": booking.payer_ppsn,
        "payer_address": booking.payer_address,
        "payer_relationship": booking.payer_relationship,
        "additional_interests": booking.additional_interests or [],
        "estimated_cost": booking.estimated_cost,
        "relief_amount": relief["relief_amount"],
        "net_cost": relief["net_cost"],
        "is_emergency": booking.is_emergency,
        "triage_brief_id": booking.triage_brief_id
    }
    
    saved = save_booking(booking_data)
    booking_id = saved['booking_id']
    
    pdf_path, pdf_filename = None, None
    if REPORTLAB_AVAILABLE:
        pdf_path, pdf_filename = generate_med2_pdf(saved, clinic)
    
    signature_link = f"/sign/{booking_id}"
    send_clinic_email(saved, clinic, signature_link)
    
    return {
        "status": "success",
        "booking_id": booking_id,
        "clinic_name": clinic["clinic_name"],
        "clinic_address": clinic["location"],
        "clinic_phone": clinic["phone"],
        "appointment_time": booking.selected_slot,
        "estimated_cost": booking.estimated_cost,
        "relief_amount": relief["relief_amount"],
        "net_cost": relief["net_cost"],
        "pdf_url": f"/api/download-pdf/{pdf_filename}" if pdf_filename else None,
        "pdf_filename": pdf_filename,
        "signature_link": signature_link
    }

@app.get("/api/download-pdf/{filename}")
def download_pdf(filename: str):
    safe_filename = Path(filename).name
    filepath = OUTPUTS_DIR / safe_filename
    if not filepath.exists():
        raise HTTPException(404, detail="PDF not found")
    return FileResponse(str(filepath), media_type='application/pdf', filename=safe_filename)

@app.get("/sign/{booking_id}", response_class=HTMLResponse)
def signature_page(booking_id: str):
    booking = get_booking_by_id(booking_id)
    if not booking:
        return HTMLResponse("<h1>Booking not found</h1>", status_code=404)
    
    patient_name = booking.get('name', 'N/A')
    treatment = booking.get('treatment', 'N/A')
    cost = booking.get('estimated_cost', 0)
    cost_display = f"€{cost:,.2f}"

    html = f"""

    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <title>Sign Med 2 Form - SmileAgent</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-100 min-h-screen flex items-center justify-center p-4">
        <div class="bg-white rounded-2xl shadow-xl max-w-md w-full p-6">
            <div class="text-center mb-6">
                <h1 class="text-xl font-bold text-gray-900">Sign Med 2 Form</h1>
                <p class="text-sm text-gray-500">SmileAgent Digital Signature</p>
            </div>
            <div class="bg-gray-50 rounded-xl p-4 mb-6">
                <p class="text-sm text-gray-600"><strong>Patient:</strong> {booking.get('name', 'N/A')}</p>
                <p class="text-sm text-gray-600"><strong>Treatment:</strong> {booking.get('treatment', 'N/A')}</p>
               <p class="text-sm text-gray-600"><strong>Amount:</strong> {cost_display}</p>
            </div>
            <canvas id="signature-pad" width="350" height="150" class="w-full bg-white border-2 border-emerald-500 rounded-xl"></canvas>
            <div class="flex gap-3 mt-4">
                <button onclick="clearSig()" class="flex-1 px-4 py-2 bg-gray-200 rounded-lg">Clear</button>
                <button onclick="submitSig()" class="flex-1 px-4 py-2 bg-emerald-500 text-white rounded-lg">Submit</button>
            </div>
            <div id="success" class="hidden mt-4 p-4 bg-emerald-50 rounded-xl text-center text-emerald-800">Signature submitted!</div>
        </div>
        <script>
            const c=document.getElementById('signature-pad'),ctx=c.getContext('2d');
            let drawing=false,lastX=0,lastY=0;
            ctx.strokeStyle='#000';ctx.lineWidth=2;ctx.lineCap='round';
            function getPos(e){{const r=c.getBoundingClientRect();return[(e.touches?e.touches[0].clientX:e.clientX)-r.left,(e.touches?e.touches[0].clientY:e.clientY)-r.top];}}
            c.onmousedown=e=>{{drawing=true;[lastX,lastY]=getPos(e);}};
            c.onmousemove=e=>{{if(!drawing)return;const[x,y]=getPos(e);ctx.beginPath();ctx.moveTo(lastX,lastY);ctx.lineTo(x,y);ctx.stroke();[lastX,lastY]=[x,y];}};
            c.onmouseup=c.onmouseout=()=>drawing=false;
            c.ontouchstart=e=>{{e.preventDefault();drawing=true;[lastX,lastY]=getPos(e);}};
            c.ontouchmove=e=>{{e.preventDefault();if(!drawing)return;const[x,y]=getPos(e);ctx.beginPath();ctx.moveTo(lastX,lastY);ctx.lineTo(x,y);ctx.stroke();[lastX,lastY]=[x,y];}};
            c.ontouchend=()=>drawing=false;
            function clearSig(){{ctx.clearRect(0,0,c.width,c.height);}}
            function submitSig(){{
                fetch('/api/submit-signature',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{booking_id:'{booking_id}',signature_data:c.toDataURL(),signed_date:new Date().toISOString()}})
                }}).then(r=>r.json()).then(d=>{{if(d.status==='success')document.getElementById('success').classList.remove('hidden');}});
            }}
        </script>
    </body>
    </html>
    """
    return HTMLResponse(html)

@app.post("/api/submit-signature")
async def submit_signature(submission: SignatureSubmission):
    booking = get_booking_by_id(submission.booking_id)
    if not booking:
        raise HTTPException(404, detail="Booking not found")
    
    signatures = []
    if SIGNATURES_FILE.exists():
        try:
            signatures = json.loads(SIGNATURES_FILE.read_text())
        except:
            signatures = []
    
    signatures.append({
        "booking_id": submission.booking_id,
        "signature_data": submission.signature_data[:100] + "...",
        "signed_date": submission.signed_date,
        "created_at": datetime.now().isoformat()
    })
    SIGNATURES_FILE.write_text(json.dumps(signatures, indent=2))
    update_booking(submission.booking_id, {"signature_status": "signed"})
    
    print(f"✍️ Signature received for booking: {submission.booking_id}")
    return {"status": "success", "message": "Signature submitted successfully"}

# ============================================================
# STARTUP
# ============================================================

@app.on_event("startup")
async def startup_event():
    print("\n" + "=" * 60)
    print("🚀 SmileAgent API v4.0 Started")
    print("=" * 60)
    print(f"📁 Base directory: {BASE_DIR}")
    print(f"🏥 Clinics loaded: {len(CLINICS)}")
    print(f"💊 Treatments: {', '.join(TREATMENTS.keys())}")
    print(f"📄 PDF generation: {'✅' if REPORTLAB_AVAILABLE else '❌'}")
    print(f"🚨 Emergency Triage: ✅")
    print(f"💳 Medical Card Filter: ✅")
    print(f"📋 Dentist Brief: ✅")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)