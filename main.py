"""
SmileAgent API v4.0 - Emergency Triage + Cosmetic Booking
Features:
- Emergency Triage Flow (Manchester Triage adapted)
- Medical Card / PRSI clinic filtering
- Dentist-Ready Brief generation
- Treatment-specific pricing
- Med 2 tax eligibility check
- PDF generation & Digital Signatures
"""

import os
import json
import uuid
import re
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, List
from enum import Enum
from math import radians, sin, cos, sqrt, atan2

from dotenv import load_dotenv
from cryptography.fernet import Fernet

from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Form, BackgroundTasks
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

cipher_suite = Fernet(
    ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY
)

# PDF manipulation check
try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.colors import black, HexColor
    REPORTLAB_AVAILABLE = True
    print("✅ reportlab available - PDF generation enabled")
except ImportError:
    REPORTLAB_AVAILABLE = False
    print("⚠️ reportlab not installed - PDF features disabled")

# ============================================================
# APP INITIALIZATION
# ============================================================

app = FastAPI(title="SmileAgent API", version="4.0.0")
BASE_DIR = Path(__file__).resolve().parent

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,https://smileagent-heak.onrender.com").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all for debugging/demo, restrict in prod
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# Directories & Files
BOOKINGS_FILE = BASE_DIR / "bookings.json"
SIGNATURES_FILE = BASE_DIR / "signatures.json"
BRIEFS_FILE = BASE_DIR / "briefs.json"
CONSENTS_FILE = BASE_DIR / "consents.json"
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUTS_DIR = BASE_DIR / "outputs"

UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUTS_DIR.mkdir(exist_ok=True)

# ============================================================
# ENUMS FOR TRIAGE (UPDATED TO MATCH FRONTEND)
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
    TOOTH_KNOCKED_OUT = "tooth_knocked_out" # Added to match HTML
    FACIAL_TRAUMA = "facial_trauma"         # Added to match HTML

# ============================================================
# CLINIC DATA
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
        "top_review": "Excellent service. Dr. Murphy explained everything clearly.",
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
        "top_review": "Very professional clinic. The team is friendly.",
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
        "top_review": "Amazing experience from start to finish.",
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
        # Basic leniency for demo - typically \d{7}[A-Z]{1,2}
        if len(clean) < 8: 
            raise ValueError('PPSN seems too short')
        return clean
    
    @validator('phone')
    def validate_phone(cls, v):
        digits = ''.join(c for c in v if c.isdigit())
        if digits.startswith('353'): digits = digits[3:]
        if digits.startswith('0'): digits = digits[1:]
        if len(digits) < 9:
            raise ValueError('Phone number too short')
        return f'+353{digits[-9:]}'

class SignatureSubmission(BaseModel):
    booking_id: str
    signature_data: str
    signed_date: str

class ConsentLog(BaseModel):
    user_identifier: str
    consent_type: str
    consent_given: bool
    consent_version: str = "v1.0"
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def get_clinic_by_id(clinic_id: int):
    for clinic in CLINICS:
        if clinic["id"] == clinic_id:
            return clinic
    return None

def encrypt_field(data: str) -> str:
    if not data: return None
    return cipher_suite.encrypt(data.encode()).decode()

def decrypt_field(encrypted_data: str) -> str:
    if not encrypted_data: return None
    return cipher_suite.decrypt(encrypted_data.encode()).decode()

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
    # Simplified version for demo
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
    
    print(f"\n🎉 NEW BOOKING: {booking_data['name']} @ {booking_data['clinic_name']}")
    return booking_data

def get_booking_by_id(booking_id: str) -> Optional[dict]:
    if not BOOKINGS_FILE.exists(): return None
    try:
        bookings = json.loads(BOOKINGS_FILE.read_text())
        for booking in bookings:
            if booking.get('booking_id') == booking_id:
                return booking
    except: pass
    return None

def update_booking(booking_id: str, updates: dict) -> bool:
    if not BOOKINGS_FILE.exists(): return False
    try:
        bookings = json.loads(BOOKINGS_FILE.read_text())
        for i, booking in enumerate(bookings):
            if booking.get('booking_id') == booking_id:
                bookings[i].update(updates)
                BOOKINGS_FILE.write_text(json.dumps(bookings, indent=2))
                return True
    except: pass
    return False

def log_consent(consent: ConsentLog) -> dict:
    consents = []
    if CONSENTS_FILE.exists():
        try:
            consents = json.loads(CONSENTS_FILE.read_text())
        except:
            consents = []
    
    hashed_id = hashlib.sha256(consent.user_identifier.encode()).hexdigest()[:16]
    record = {
        "consent_id": str(uuid.uuid4())[:8],
        "user_hash": hashed_id,
        "consent_type": consent.consent_type,
        "consent_given": consent.consent_given,
        "consent_version": consent.consent_version,
        "timestamp": datetime.now().isoformat(),
        "ip_address": consent.ip_address,
        "user_agent": consent.user_agent
    }
    consents.append(record)
    CONSENTS_FILE.write_text(json.dumps(consents, indent=2))
    print(f"✅ Consent logged: {consent.consent_type}")
    return record

# ============================================================
# TRIAGE LOGIC
# ============================================================

def assess_triage(triage_input: TriageInput) -> dict:
    # ANY red flag immediately triggers emergency response
    if triage_input.red_flags:
        return {
            "urgency": UrgencyLevel.RED_AE.value,
            "urgency_display": "Emergency - Immediate Care",
            "recommended_timeframe": "Immediately",
            "reasoning": "Your symptoms indicate a potentially serious condition.",
            "show_ae_redirect": True,
            "self_care_tips": []
        }
    
    pl = triage_input.pain_level
    
    if (pl >= 7 and triage_input.pain_worsening) or (pl >= 8) or (pl >= 6 and triage_input.sleep_disrupted):
        return {
            "urgency": UrgencyLevel.ORANGE_URGENT.value,
            "urgency_display": "Urgent",
            "recommended_timeframe": "Within 24 hours",
            "reasoning": "High pain levels suggest urgent care needed.",
            "show_ae_redirect": False,
            "self_care_tips": ["Avoid hot/cold foods", "Take OTC pain relief if safe"]
        }
    
    if pl >= 4 or triage_input.visible_damage:
        return {
            "urgency": UrgencyLevel.YELLOW_SOON.value,
            "urgency_display": "Soon",
            "recommended_timeframe": "Within 2-3 days",
            "reasoning": "Symptoms need assessment but are not immediate emergencies.",
            "show_ae_redirect": False,
            "self_care_tips": ["Keep area clean", "Monitor symptoms"]
        }
    
    return {
        "urgency": UrgencyLevel.GREEN_ROUTINE.value,
        "urgency_display": "Routine",
        "recommended_timeframe": "Within 1-2 weeks",
        "reasoning": "Symptoms appear stable.",
        "show_ae_redirect": False,
        "self_care_tips": ["Maintain hygiene"]
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

def match_clinics_for_emergency(search: EmergencyClinicSearch) -> List[dict]:
    matches = []
    for clinic in CLINICS:
        distance = haversine_distance(
            search.latitude, search.longitude,
            clinic["coordinates"]["lat"], clinic["coordinates"]["lng"]
        )
        
        if distance > search.max_distance_km: continue
        
        mc_info = clinic.get("medical_card", {})
        if search.medical_card_only and not mc_info.get("accepts", False): continue
        if search.prsi_only and not clinic.get("prsi_dtbs", False): continue
        
        match = {
            "id": clinic["id"],
            "clinic_name": clinic["clinic_name"],
            "location": clinic["location"],
            "eircode": clinic["eircode"],
            "phone": clinic["phone"],
            "distance_km": round(distance, 1),
            "rating": clinic.get("rating"),
            "review_count": clinic.get("review_count"),
            "verified": clinic.get("verified", False),
            "accepts_medical_card": mc_info.get("accepts", False),
            "mc_accepting_new": mc_info.get("accepting_new_patients", False),
            "accepts_prsi": clinic.get("prsi_dtbs", False),
            "has_emergency_slots": clinic.get("emergency_slots", {}).get("offers_same_day", False),
            "typical_wait_hours": clinic.get("emergency_slots", {}).get("typical_wait_hours"),
            "pricing": clinic.get("pricing", {}),
            "available_slots": clinic.get("available_slots", [])
        }
        matches.append(match)
    
    matches.sort(key=lambda x: x['distance_km'])
    return matches

# ============================================================
# BRIEF & PDF GENERATION
# ============================================================

def generate_brief(brief_input: BriefInput) -> dict:
    brief_id = datetime.now().strftime("%Y%m%d%H%M%S") + str(uuid.uuid4())[:4]
    brief = brief_input.dict()
    brief["brief_id"] = brief_id
    brief["generated_at"] = datetime.now().isoformat()
    brief["status"] = "pending"
    
    # Encrypt PII
    brief["patient_name"] = encrypt_field(brief["patient_name"])
    brief["patient_phone"] = encrypt_field(brief["patient_phone"])
    brief["chief_complaint"] = encrypt_field(brief["chief_complaint"])
    
    briefs = []
    if BRIEFS_FILE.exists():
        try: briefs = json.loads(BRIEFS_FILE.read_text())
        except: pass
    briefs.append(brief)
    BRIEFS_FILE.write_text(json.dumps(briefs, indent=2))
    
    print(f"📄 Brief generated: {brief_id} for {brief_input.clinic_name}")
    return brief

def send_clinic_email(booking: dict, clinic: dict, signature_link: str, brief: dict = None):
    # Simulated email
    print(f"📧 EMAIL SENT to {clinic['email']} | Subject: New Booking/Brief")

def generate_med2_pdf(booking: dict, clinic: dict) -> tuple:
    if not REPORTLAB_AVAILABLE: return None, None
    booking_id = booking.get('booking_id', 'unknown')
    filename = f"Med2_SmileAgent_{booking_id}.pdf"
    filepath = OUTPUTS_DIR / filename
    
    c = canvas.Canvas(str(filepath), pagesize=A4)
    width, height = A4
    
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, height - 50, "Med 2 Form - SmileAgent")
    c.setFont("Helvetica", 12)
    c.drawString(50, height - 80, f"Patient: {booking.get('name')}")
    c.drawString(50, height - 100, f"PPSN: {booking.get('ppsn')}")
    c.drawString(50, height - 120, f"Clinic: {booking.get('clinic_name')}")
    c.drawString(50, height - 140, f"Cost: EUR {booking.get('estimated_cost')}")
    
    c.save()
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
    return {"status": "healthy", "version": "4.0.0"}

@app.get("/api/clinics")
def get_clinics(treatment: Optional[str] = None):
    result = []
    for clinic in CLINICS:
        c_data = clinic.copy()
        if treatment and treatment in clinic.get("pricing", {}):
            c_data["price"] = clinic["pricing"][treatment]
        result.append(c_data)
    return {"clinics": result}

@app.post("/api/triage/assess", response_model=TriageOutput)
async def run_triage(triage_input: TriageInput):
    return assess_triage(triage_input)

@app.post("/api/clinics/emergency")
async def search_emergency_clinics(search: EmergencyClinicSearch):
    results = match_clinics_for_emergency(search)
    return {"clinics": results, "count": len(results)}

@app.post("/api/briefs/generate")
async def create_brief(brief_input: BriefInput, background_tasks: BackgroundTasks):
    brief = generate_brief(brief_input)
    clinic = get_clinic_by_id(brief_input.clinic_id)
    if clinic:
        background_tasks.add_task(send_clinic_email, {}, clinic, "", brief)
    return brief

@app.post("/api/consent/log")
async def log_user_consent(consent: ConsentLog, request: Request):
    consent.ip_address = request.client.host
    consent.user_agent = request.headers.get("user-agent", "")[:100]
    record = log_consent(consent)
    return {"status": "success", "consent_id": record["consent_id"]}

@app.post("/api/analyze-smile")
async def analyze_smile(file: UploadFile = File(...), save_for_med2: bool = Form(default=False)):
    photo_id = str(uuid.uuid4())
    filepath = UPLOAD_DIR / f"{photo_id}.jpg"
    filepath.write_bytes(await file.read())
    return {
        "status": "success",
        "photo_id": photo_id,
        "saved_for_med2": save_for_med2,
        "diagnosis": {"primary_issue": "Crowding", "confidence_score": 95}
    }

@app.post("/api/check-eligibility")
async def check_tax_eligibility(check: TaxEligibilityCheck):
    is_eligible = check.pays_irish_tax in ["paye", "self_assessed"]
    msg = "Eligible for 20% relief" if is_eligible else "Not eligible"
    return {"is_eligible": is_eligible, "message": msg, "relief_rate": 0.20 if is_eligible else 0}

@app.post("/api/book-appointment")
async def book_appointment(booking: BookingRequest):
    clinic = get_clinic_by_id(booking.clinic_id)
    if not clinic: raise HTTPException(404, detail="Clinic not found")
    
    relief = calculate_med2_relief(booking.estimated_cost)
    booking_dict = booking.dict()
    booking_dict.update(relief)
    
    saved = save_booking(booking_dict)
    pdf_path, pdf_filename = generate_med2_pdf(saved, clinic)
    
    return {
        "status": "success",
        "booking_id": saved['booking_id'],
        "clinic_name": clinic["clinic_name"],
        "clinic_address": clinic["location"],
        "clinic_phone": clinic["phone"],
        "appointment_time": booking.selected_slot,
        "pdf_url": f"/api/download-pdf/{pdf_filename}" if pdf_filename else None
    }

@app.get("/api/download-pdf/{filename}")
def download_pdf(filename: str):
    filepath = OUTPUTS_DIR / Path(filename).name
    if not filepath.exists(): raise HTTPException(404)
    return FileResponse(str(filepath), media_type='application/pdf', filename=filename)

# ============================================================
# STARTUP
# ============================================================

@app.on_event("startup")
async def startup_event():
    print(f"🚀 SmileAgent API v4.0 Started")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
