from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import random
import string

db = SQLAlchemy()


def generate_reservation_id(name):
    """Generate a 6-character reservation ID from name initials + 4 random digits."""
    # Get first two initials from name (uppercase)
    parts = name.strip().split()
    if len(parts) >= 2:
        initials = (parts[0][0] + parts[1][0]).upper()
    elif len(parts) == 1 and len(parts[0]) >= 2:
        initials = parts[0][:2].upper()
    else:
        initials = 'XX'
    
    # Generate 4 random digits
    digits = ''.join(random.choices(string.digits, k=4))
    
    return initials + digits


class RSVP(db.Model):
    """RSVP model for storing initial save-the-date responses."""
    
    __tablename__ = 'rsvps'
    
    id = db.Column(db.Integer, primary_key=True)
    reservation_id = db.Column(db.String(6), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    num_guests = db.Column(db.Integer, nullable=False, default=1)
    payment_status = db.Column(db.String(20), nullable=False, default='not paid')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship to guests
    guests = db.relationship('Guest', backref='rsvp', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<RSVP {self.reservation_id}: {self.name} ({self.email})>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'reservation_id': self.reservation_id,
            'name': self.name,
            'email': self.email,
            'num_guests': self.num_guests,
            'payment_status': self.payment_status,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }


class Guest(db.Model):
    """Guest model for storing individual guest information."""
    
    __tablename__ = 'guests'
    
    id = db.Column(db.Integer, primary_key=True)
    rsvp_id = db.Column(db.Integer, db.ForeignKey('rsvps.id'), nullable=False)
    guest_number = db.Column(db.Integer, nullable=False)  # 1 or 2
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    title_rank = db.Column(db.String(50))
    meal_preference = db.Column(db.String(20), nullable=False)  # Buffet Dinner
    allergy_notes = db.Column(db.Text)
    fun_fact = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<Guest {self.first_name} {self.last_name} (RSVP: {self.rsvp_id})>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'rsvp_id': self.rsvp_id,
            'guest_number': self.guest_number,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'title_rank': self.title_rank,
            'meal_preference': self.meal_preference,
            'allergy_notes': self.allergy_notes,
            'fun_fact': self.fun_fact,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }
