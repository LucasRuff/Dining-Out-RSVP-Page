
from flask import Flask, render_template, redirect, url_for, flash, session, request, make_response
from models import db, RSVP, Guest, SeatingPreference, generate_reservation_id
from forms import RSVPForm, UpdateConfirmForm, PaymentStatusForm, GuestInfoForm, ReservationLookupForm, SeatingPreferenceForm
import os
import secrets
from sqlalchemy import text
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///rsvp.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# Create tables on first request
with app.app_context():
    db.create_all()
    # Lightweight migration for RSVP token column
    try:
        columns = {row[1] for row in db.session.execute(text("PRAGMA table_info(rsvps)"))}
        if 'rsvp_token' not in columns:
            db.session.execute(text("ALTER TABLE rsvps ADD COLUMN rsvp_token VARCHAR(128)"))
            db.session.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_rsvps_rsvp_token ON rsvps (rsvp_token)"))
            db.session.commit()
    except Exception:
        db.session.rollback()


@app.context_processor
def inject_rsvp():
    """Inject RSVP into all templates."""
    return {'current_rsvp': get_rsvp_from_cookie()}


def get_rsvp_from_cookie():
    """Get RSVP record from cookie if it exists and is valid."""
    rsvp_token = request.cookies.get('rsvp_token')
    if rsvp_token:
        return RSVP.query.filter_by(rsvp_token=rsvp_token).first()
    return None


def ensure_rsvp_token(rsvp):
    """Ensure RSVP has a unique, unguessable token."""
    if not rsvp.rsvp_token:
        rsvp.rsvp_token = secrets.token_urlsafe(32)
        db.session.commit()
    return rsvp.rsvp_token


def set_rsvp_cookie(response, rsvp):
    """Set cookie with RSVP token."""
    token = ensure_rsvp_token(rsvp)
    response.set_cookie('rsvp_token', token, max_age=60*60*24*365, httponly=True, samesite='Lax')
    return response


def delete_rsvp_cookie(response):
    """Delete the RSVP cookie."""
    response.delete_cookie('rsvp_token')
    return response


def require_admin(f):
    """Decorator to require admin authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_authenticated'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function


# Home page
@app.route('/')
def home():
    """Simple home page with link to RSVP form."""
    rsvp = get_rsvp_from_cookie()
    return render_template('home.html', rsvp=rsvp)


@app.route('/menu')
def menu():
    """Menu page with buffet details."""
    return render_template('menu.html')


# RSVP form page
@app.route('/rsvp', methods=['GET', 'POST'])
def rsvp():
    """Save-the-date RSVP form page."""
    # Check for existing RSVP via cookie
    existing_rsvp = get_rsvp_from_cookie()
    action = request.args.get('action')
    
    # If user has an RSVP and hasn't chosen an action, show welcome back page
    # (unless they're starting a new reservation)
    if existing_rsvp and action is None:
        return render_template('welcome_back.html', rsvp=existing_rsvp)
    
    # Handle delete action
    if action == 'delete' and existing_rsvp:
        db.session.delete(existing_rsvp)
        db.session.commit()
        flash('Your RSVP has been deleted.', 'info')
        response = make_response(redirect(url_for('rsvp')))
        delete_rsvp_cookie(response)
        return response
    
    # Handle new action (bypass welcome back)
    if action == 'new':
        existing_rsvp = None
    
    # For modify action, pre-fill the form
    form = RSVPForm()
    if action == 'modify' and existing_rsvp and request.method == 'GET':
        form.name.data = existing_rsvp.name
        form.email.data = existing_rsvp.email
        form.num_guests.data = str(existing_rsvp.num_guests)
    
    if form.validate_on_submit():
        email = form.email.data.lower()
        
        # If modifying, update existing record
        if action == 'modify' and existing_rsvp:
            existing_rsvp.name = form.name.data
            existing_rsvp.email = email
            existing_rsvp.num_guests = int(form.num_guests.data)
            db.session.commit()
            session['show_reservation_id'] = existing_rsvp.reservation_id
            flash('Your RSVP has been updated successfully.', 'success')
            response = make_response(redirect(url_for('success')))
            set_rsvp_cookie(response, existing_rsvp)
            return response
        
        # Check if email already exists (for new RSVPs)
        email_rsvp = RSVP.query.filter_by(email=email).first()
        if email_rsvp and (action == 'new' or not existing_rsvp):
            session['pending_rsvp'] = {
                'name': form.name.data,
                'email': email,
                'num_guests': int(form.num_guests.data)
            }
            return redirect(url_for('confirm_update'))
        
        # Create new RSVP
        new_rsvp = RSVP(
            name=form.name.data,
            email=email,
            num_guests=int(form.num_guests.data),
            reservation_id=generate_reservation_id(form.name.data)
        )
        db.session.add(new_rsvp)
        db.session.commit()
        flash('Thank you! Your RSVP has been submitted successfully.', 'success')
        session['show_reservation_id'] = new_rsvp.reservation_id
        response = make_response(redirect(url_for('success')))
        set_rsvp_cookie(response, new_rsvp)
        return response
    
    return render_template('index.html', form=form, action=action)


@app.route('/confirm-update', methods=['GET', 'POST'])
def confirm_update():
    """Page to confirm whether to update existing RSVP."""
    if 'pending_rsvp' not in session:
        return redirect(url_for('rsvp'))
    
    pending = session['pending_rsvp']
    existing_rsvp = RSVP.query.filter_by(email=pending['email']).first()
    
    if not existing_rsvp:
        session.pop('pending_rsvp', None)
        return redirect(url_for('rsvp'))
    
    form = UpdateConfirmForm()
    
    if form.validate_on_submit():
        if form.update.data:
            # Check if guest count is being reduced
            old_guest_count = existing_rsvp.num_guests
            new_guest_count = pending['num_guests']
            
            # Update existing RSVP
            existing_rsvp.name = pending['name']
            existing_rsvp.num_guests = pending['num_guests']
            db.session.commit()
            
            session.pop('pending_rsvp', None)
            
            # If guest count decreased, redirect to guest removal page
            if new_guest_count < old_guest_count:
                session['rsvp_id_for_removal'] = existing_rsvp.id
                session['show_reservation_id'] = existing_rsvp.reservation_id
                return redirect(url_for('remove_guest'))
            
            session['show_reservation_id'] = existing_rsvp.reservation_id
            flash('Your RSVP has been updated successfully.', 'success')
            response = make_response(redirect(url_for('success')))
            set_rsvp_cookie(response, existing_rsvp)
            return response
        
        elif form.cancel.data:
            session.pop('pending_rsvp', None)
            flash('RSVP submission cancelled.', 'info')
            return redirect(url_for('rsvp'))
    
    return render_template('confirm_update.html', 
                          form=form, 
                          existing=existing_rsvp, 
                          pending=pending)


@app.route('/remove-guest', methods=['GET', 'POST'])
def remove_guest():
    """Remove guest when reservation guest count is reduced."""
    rsvp_id = session.get('rsvp_id_for_removal')
    if not rsvp_id:
        return redirect(url_for('home'))
    
    rsvp = RSVP.query.get(rsvp_id)
    if not rsvp:
        session.pop('rsvp_id_for_removal', None)
        return redirect(url_for('home'))
    
    # Get existing guests
    guests = Guest.query.filter_by(rsvp_id=rsvp.id).order_by(Guest.guest_number).all()
    
    if request.method == 'POST':
        guest_to_remove_id = request.form.get('guest_id')
        if guest_to_remove_id:
            guest = Guest.query.get(int(guest_to_remove_id))
            if guest and guest.rsvp_id == rsvp.id:
                guest_number_removed = guest.guest_number
                db.session.delete(guest)
                
                # If guest 1 was removed and guest 2 exists, renumber guest 2 to guest 1
                if guest_number_removed == 1:
                    guest_2 = Guest.query.filter_by(rsvp_id=rsvp.id, guest_number=2).first()
                    if guest_2:
                        guest_2.guest_number = 1
                
                db.session.commit()
                flash(f'Guest removed successfully.', 'success')
        
        session.pop('rsvp_id_for_removal', None)
        response = make_response(redirect(url_for('success')))
        set_rsvp_cookie(response, rsvp)
        return response
    
    return render_template('remove_guest.html', rsvp=rsvp, guests=guests)


@app.route('/success')
def success():
    """Success page after RSVP submission."""
    reservation_id = session.pop('show_reservation_id', None)
    if not reservation_id:
        # Try to get from cookie
        rsvp = get_rsvp_from_cookie()
        if rsvp:
            reservation_id = rsvp.reservation_id
    return render_template('success.html', reservation_id=reservation_id)


@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():
    """Admin login page."""
    if request.method == 'POST':
        password = request.form.get('password')
        admin_password = os.environ.get('ADMIN_PASSWORD', 'admin')
        
        if admin_password and password == admin_password:
            session['admin_authenticated'] = True
            flash('Logged in successfully.', 'success')
            return redirect(request.args.get('next') or url_for('responses'))
        else:
            flash('Incorrect password.', 'error')
    
    return render_template('admin_login.html')


@app.route('/responses')
@require_admin
def responses():
    """View all current RSVP responses."""
    rsvps = RSVP.query.order_by(RSVP.created_at.desc()).all()
    return render_template('responses.html', rsvps=rsvps)


@app.route('/mark-payment', methods=['POST'])
def mark_payment():
    """User marks that they have paid."""
    payment_method = request.form.get('payment_method')
    
    # Get RSVP from cookie or session
    rsvp = get_rsvp_from_cookie()
    if not rsvp and 'guest_info_rsvp_id' in session:
        rsvp = RSVP.query.get(session['guest_info_rsvp_id'])
    
    if rsvp and payment_method in ['cash', 'Venmo']:
        rsvp.payment_status = f'pending - {payment_method}'
        db.session.commit()
        flash(f'Thank you! Your {payment_method} payment has been marked as pending confirmation.', 'success')
    
    return redirect(request.referrer or url_for('home'))


@app.route('/payment-tracking', methods=['GET', 'POST'])
@require_admin
def payment_tracking():
    """Payment tracking page to update payment status for each RSVP."""
    rsvps = RSVP.query.order_by(RSVP.name).all()
    
    if request.method == 'POST':
        rsvp_id = request.form.get('rsvp_id')
        new_status = request.form.get('payment_status')
        
        if rsvp_id and new_status in ['not paid', 'pending - cash', 'pending - Venmo', 'cash', 'Venmo', 'guests changed - not paid']:
            rsvp = RSVP.query.get(int(rsvp_id))
            if rsvp:
                rsvp.payment_status = new_status
                db.session.commit()
        
        return redirect(url_for('payment_tracking'))
    
    return render_template('payment_tracking.html', rsvps=rsvps)


@app.route('/guest-info', methods=['GET', 'POST'])
def guest_info():
    """Guest information page for entering guest details."""
    # Try to get RSVP from cookie first
    rsvp = get_rsvp_from_cookie()
    
    # Check for rsvp_id parameter in URL
    rsvp_id_param = request.args.get('rsvp_id')
    if rsvp_id_param:
        try:
            rsvp = RSVP.query.get(int(rsvp_id_param))
            if rsvp:
                session['guest_info_rsvp_id'] = rsvp.id
        except (ValueError, TypeError):
            pass
    
    # If we have an RSVP from session, retrieve it
    if not rsvp and 'guest_info_rsvp_id' in session:
        rsvp = RSVP.query.get(session['guest_info_rsvp_id'])
        if not rsvp:
            session.pop('guest_info_rsvp_id', None)
    
    # If no RSVP found, show lookup form
    if not rsvp:
        lookup_form = ReservationLookupForm()
        
        if lookup_form.validate_on_submit():
            lookup_value = lookup_form.lookup_value.data.strip()
            
            # Try to find by reservation ID or email
            rsvp = RSVP.query.filter(
                (RSVP.reservation_id == lookup_value.upper()) | 
                (RSVP.email == lookup_value.lower())
            ).first()
            
            if rsvp:
                # Set a temporary session to allow guest info entry
                session['guest_info_rsvp_id'] = rsvp.id
                response = make_response(redirect(url_for('guest_info')))
                set_rsvp_cookie(response, rsvp)
                return response
            else:
                flash('Reservation not found. Please check your Reservation ID or email.', 'error')
        
        return render_template('guest_info_lookup.html', form=lookup_form)
    
    # Check for action parameter
    action = request.args.get('action')
    
    # Load existing guest data if available
    guests = Guest.query.filter_by(rsvp_id=rsvp.id).order_by(Guest.guest_number).all()
    guest1 = next((g for g in guests if g.guest_number == 1), None)
    guest2 = next((g for g in guests if g.guest_number == 2), None)
    
    # If guests exist and no action specified, show the view page
    if guest1 and action != 'edit':
        return render_template('guest_info_view.html', rsvp=rsvp, guest1=guest1, guest2=guest2)
    
    # Show the form for editing or initial entry
    form = GuestInfoForm()
    
    if request.method == 'GET':
        if guest1:
            form.g1_first_name.data = guest1.first_name
            form.g1_last_name.data = guest1.last_name
            form.g1_title_rank.data = guest1.title_rank
            form.g1_allergy_notes.data = guest1.allergy_notes
            form.g1_fun_fact.data = guest1.fun_fact
        else:
            # Auto-populate guest 1 from RSVP name as best guess
            parts = rsvp.name.strip().split()
            if len(parts) >= 2:
                form.g1_first_name.data = parts[0]
                form.g1_last_name.data = parts[-1]
            elif len(parts) == 1:
                form.g1_first_name.data = parts[0]
        
        if guest2:
            form.g2_first_name.data = guest2.first_name
            form.g2_last_name.data = guest2.last_name
            form.g2_title_rank.data = guest2.title_rank
            form.g2_allergy_notes.data = guest2.allergy_notes
            form.g2_fun_fact.data = guest2.fun_fact
    
    if form.validate_on_submit():
        # Save or update Guest 1
        if not guest1:
            guest1 = Guest(rsvp_id=rsvp.id, guest_number=1)
            db.session.add(guest1)
        
        guest1.first_name = form.g1_first_name.data
        guest1.last_name = form.g1_last_name.data
        guest1.title_rank = form.g1_title_rank.data
        guest1.meal_preference = 'Buffet Dinner'
        guest1.allergy_notes = form.g1_allergy_notes.data
        guest1.fun_fact = form.g1_fun_fact.data
        
        # Save or update Guest 2 if num_guests == 2
        if rsvp.num_guests == 2:
            if form.g2_first_name.data and form.g2_last_name.data:
                if not guest2:
                    guest2 = Guest(rsvp_id=rsvp.id, guest_number=2)
                    db.session.add(guest2)
                
                guest2.first_name = form.g2_first_name.data
                guest2.last_name = form.g2_last_name.data
                guest2.title_rank = form.g2_title_rank.data
                guest2.meal_preference = 'Buffet Dinner'
                guest2.allergy_notes = form.g2_allergy_notes.data
                guest2.fun_fact = form.g2_fun_fact.data
        
        db.session.commit()
        flash('Guest information saved successfully!', 'success')
        return redirect(url_for('guest_info'))
    
    return render_template('guest_info.html', form=form, rsvp=rsvp)


@app.route('/guest-list')
def guest_list():
    """View all guests across all reservations."""
    guests = Guest.query.order_by(Guest.rsvp_id, Guest.guest_number).all()
    return render_template('guest_list.html', guests=guests)


@app.route('/remove-guest-2', methods=['POST'])
def remove_guest_2():
    """Remove guest 2 and reduce reservation to 1 guest."""
    return remove_guest_by_number(2)


@app.route('/remove-guest/<int:guest_number>', methods=['POST'])
def remove_guest_by_number(guest_number):
    """Remove a guest and keep numbering consistent."""
    rsvp = get_rsvp_from_cookie()

    if not rsvp:
        flash('Reservation not found.', 'error')
        return redirect(url_for('guest_info'))

    if guest_number not in [1, 2]:
        flash('Invalid guest selection.', 'error')
        return redirect(url_for('guest_info'))

    # Remove selected guest
    guest = Guest.query.filter_by(rsvp_id=rsvp.id, guest_number=guest_number).first()
    if guest:
        db.session.delete(guest)

    # If guest 1 was removed and guest 2 exists, renumber guest 2 to guest 1
    if guest_number == 1:
        guest2 = Guest.query.filter_by(rsvp_id=rsvp.id, guest_number=2).first()
        if guest2:
            guest2.guest_number = 1

    # Reduce num_guests to 1
    rsvp.num_guests = 1
    db.session.commit()

    flash(f'Guest {guest_number} removed. Reservation is now for 1 guest.', 'success')
    return redirect(url_for('guest_info'))


@app.route('/add-guest', methods=['POST'])
def add_guest():
    """Add a second guest to a reservation."""
    rsvp = get_rsvp_from_cookie()
    
    if not rsvp:
        flash('Reservation not found.', 'error')
        return redirect(url_for('guest_info'))
    
    if rsvp.num_guests >= 2:
        flash('Your reservation already has 2 guests.', 'info')
        return redirect(url_for('guest_info'))
    
    # Update to 2 guests
    rsvp.num_guests = 2
    
    # Update payment status if already paid
    if rsvp.payment_status != 'not paid':
        rsvp.payment_status = 'guests changed - not paid'
    
    db.session.commit()
    flash('Guest added! Please provide their information.', 'success')
    
    # Redirect to edit mode
    return redirect(url_for('guest_info', action='edit'))


@app.route('/seating-preferences', methods=['GET', 'POST'])
def seating_preferences():
    """Seating preferences page for ranking other reservations."""
    rsvp = get_rsvp_from_cookie()
    
    if not rsvp:
        flash('Please look up your reservation first.', 'info')
        return redirect(url_for('guest_info'))
    
    # Get all other RSVPs
    other_rsvps = RSVP.query.filter(RSVP.id != rsvp.id).order_by(RSVP.name).all()
    
    if not other_rsvps:
        flash('No other reservations to prefer.', 'info')
        return redirect(url_for('guest_info'))
    
    # Get existing preferences or create new
    preference = SeatingPreference.query.filter_by(rsvp_id=rsvp.id).first()
    ranked_ids = preference.get_ranked_list() if preference else []
    
    if request.method == 'POST':
        # Get ranked RSVP IDs from form
        ranked_rsvp_ids = []
        for i in range(len(other_rsvps)):
            rsvp_id = request.form.get(f'rank_{i}')
            if rsvp_id:
                try:
                    ranked_rsvp_ids.append(int(rsvp_id))
                except (ValueError, TypeError):
                    pass
        
        # Save or update preference
        if not preference:
            preference = SeatingPreference(rsvp_id=rsvp.id)
            db.session.add(preference)
        
        preference.set_ranked_list(ranked_rsvp_ids)
        db.session.commit()
        flash('Seating preferences saved successfully!', 'success')
        # Refresh the page to show updated state
        return redirect(url_for('seating_preferences'))
    
    # Build list of other RSVPs with guest names for display, separated into ranked and unranked
    ranked_rsvps_info = []
    unranked_rsvps_info = []
    
    for other_rsvp in other_rsvps:
        guests = Guest.query.filter_by(rsvp_id=other_rsvp.id).order_by(Guest.guest_number).all()
        
        # Display name: use guest names if available, otherwise fall back to RSVP name
        if guests:
            display_name = ' and '.join([f"{g.first_name} {g.last_name}" for g in guests])
        else:
            display_name = other_rsvp.name
        
        rsvp_info = {
            'rsvp': other_rsvp,
            'display_name': display_name,
            'rank': ranked_ids.index(other_rsvp.id) + 1 if other_rsvp.id in ranked_ids else None
        }
        
        if other_rsvp.id in ranked_ids:
            ranked_rsvps_info.append(rsvp_info)
        else:
            unranked_rsvps_info.append(rsvp_info)
    
    # Sort ranked by their position in ranked_ids
    ranked_rsvps_info.sort(key=lambda x: ranked_ids.index(x['rsvp'].id))
    
    form = SeatingPreferenceForm()
    return render_template('seating_preferences.html', form=form, rsvp=rsvp, ranked_rsvps_info=ranked_rsvps_info, unranked_rsvps_info=unranked_rsvps_info, ranked_ids=ranked_ids)


if __name__ == '__main__':
    app.run(debug=True)
