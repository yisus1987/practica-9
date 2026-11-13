import hashlib
from typing import Optional
import requests
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Double, Text, TIMESTAMP, ForeignKey, text
from sqlalchemy.orm import sessionmaker, declarative_base, Session

# Configuración de conexión a MySQL
DATABASE_URL = "mysql+pymysql://root:@localhost/asistencia_gps"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

app = FastAPI()

# Habilitar CORS para peticiones desde Flutter
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MODELOS SQLALCHEMY ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    password = Column(String(32), nullable=False)

class Attendance(Base):
    __tablename__ = "attendance"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    latitude = Column(Double, nullable=False)
    longitude = Column(Double, nullable=False)
    address = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP, server_default=text("CURRENT_TIMESTAMP"))

Base.metadata.create_all(bind=engine)

# --- MODELOS PYDANTIC ---
class RegisterModel(BaseModel):
    username: str
    password: str

class LoginModel(BaseModel):
    username: str
    password: str

class AttendanceModel(BaseModel):
    user_id: int
    latitude: float
    longitude: float

# --- UTILIDADES ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def md5_hash(password: str) -> str:
    return hashlib.md5(password.encode()).hexdigest()

def get_address_from_nominatim(lat: float, lon: float) -> str:
    url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}"
    headers = {"User-Agent": "FlutterAttendanceApp/1.0"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return data.get("display_name", "Dirección no encontrada")
    except Exception:
        pass
    return "Error al consultar la dirección"

# --- ENDPOINTS ---
@app.post("/register/")
def register(user: RegisterModel, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.username == user.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="El usuario ya existe")

    new_user = User(username=user.username, password=md5_hash(user.password))
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": "Usuario registrado exitosamente", "user_id": new_user.id}

@app.post("/login/")
def login(user: LoginModel, db: Session = Depends(get_db)):
    hashed_pw = md5_hash(user.password)
    db_user = db.query(User).filter(User.username == user.username, User.password == hashed_pw).first()
    if not db_user:
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")

    return {"message": "Login exitoso", "user_id": db_user.id, "username": db_user.username}

@app.post("/attendance/")
def register_attendance(data: AttendanceModel, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == data.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    address = get_address_from_nominatim(data.latitude, data.longitude)

    new_record = Attendance(
        user_id=data.user_id,
        latitude=data.latitude,
        longitude=data.longitude,
        address=address
    )

    db.add(new_record)
    db.commit()
    db.refresh(new_record)

    return {
        "message": "Asistencia registrada",
        "address": address,
        "latitude": data.latitude,
        "longitude": data.longitude
    }

@app.get("/attendance/")
def get_attendance(user_id: Optional[int] = None, db: Session = Depends(get_db)):
    if user_id:
        return db.query(Attendance).filter(Attendance.user_id == user_id).order_by(Attendance.id.desc()).all()
    return db.query(Attendance).order_by(Attendance.id.desc()).all()