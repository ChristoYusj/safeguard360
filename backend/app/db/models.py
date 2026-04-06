"""
Database Models (SQLAlchemy ORM)
"""
from sqlalchemy import Column, String, Boolean, Integer, Float, DateTime, Text, ForeignKey
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime
import uuid

Base = declarative_base()


def generate_uuid():
    return str(uuid.uuid4())


class Person(Base):
    """Enrolled person for face recognition."""
    __tablename__ = "persons"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(100), nullable=False)
    employee_id = Column(String(50), nullable=True)
    embedding = Column(Text, nullable=True)  # JSON serialized
    thumbnail_path = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    attendance_records = relationship("Attendance", back_populates="person")


class Attendance(Base):
    """Attendance/access log entry."""
    __tablename__ = "attendance"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    person_id = Column(String(36), ForeignKey("persons.id"), nullable=True)
    person_name = Column(String(100), nullable=True)
    direction = Column(String(10), nullable=False)  # ENTRY or EXIT
    timestamp = Column(DateTime, default=datetime.utcnow)
    ppe_compliant = Column(Boolean, default=True)
    access_granted = Column(Boolean, default=True)
    snapshot_path = Column(String(255), nullable=True)
    confidence = Column(Float, nullable=True)
    
    person = relationship("Person", back_populates="attendance_records")


class GateReview(Base):
    """Low-confidence gate recognition awaiting operator review."""
    __tablename__ = "gate_reviews"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    person_id = Column(String(36), ForeignKey("persons.id"), nullable=True)
    person_name = Column(String(100), nullable=True)
    suggested_direction = Column(String(10), nullable=True)
    confidence = Column(Float, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    status = Column(String(20), default="PENDING")
    decision_note = Column(Text, nullable=True)
    decided_at = Column(DateTime, nullable=True)
    decided_by = Column(String(100), nullable=True)
    snapshot_path = Column(String(255), nullable=True)

    person = relationship("Person")


class Event(Base):
    """PPE and driver monitoring events."""
    __tablename__ = "events"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    category = Column(String(20), nullable=False)  # PPE or DRIVER
    event_type = Column(String(50), nullable=False)
    severity = Column(String(20), default="INFO")
    timestamp = Column(DateTime, default=datetime.utcnow)
    data = Column(Text, nullable=True)  # JSON serialized
    snapshot_path = Column(String(255), nullable=True)
    is_resolved = Column(Boolean, default=False)


class Alert(Base):
    """Active and historical alerts."""
    __tablename__ = "alerts"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    event_id = Column(String(36), ForeignKey("events.id"), nullable=True)
    severity = Column(String(20), default="INFO")
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    acknowledged_at = Column(DateTime, nullable=True)
