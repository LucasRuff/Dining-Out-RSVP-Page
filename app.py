
from flask import Flask, render_template, redirect, url_for, flash, session, request, make_response
from models import db, RSVP, Guest, generate_reservation_id
from forms import RSVPForm, UpdateConfirmForm, PaymentStatusForm, GuestInfoForm, ReservationLookupForm
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///rsvp.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# Create tables on first request
with app.app_context():
    db.create_all()


@app.context_processor
def inject_rsvp():
    """Inject RSVP into all templates."""
    return {'current_rsvp': get_rsvp_from_cookie()}


def get_rsvp_from_cookie():
    """Get RSVP record from cookie if it exists and is valid."""
    rsvp_id = request.cookies.get('rsvp_id')
    if rsvp_id:
        try:
            return RSVP.query.get(int(rsvp_id))
        except (ValueError, TypeError):
            return None
    return None


def set_rsvp_cookie(response, rsvp_id):
    """Set cookie with RSVP id."""
    response.set_cookie('rsvp_id', str(rsvp_id), max_age=60*60*24*365)  # 1 year
    return response


def delete_rsvp_cookie(response):
    """Delete the RSVP cookie."""
    response.delete_cookie('rsvp_id')
    return response


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
            set_rsvp_cookie(response, existing_rsvp.id)
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
        set_rsvp_cookie(response, new_rsvp.id)
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
            set_rsvp_cookie(response, existing_rsvp.id)
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
        set_rsvp_cookie(response, rsvp.id)
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


@app.route('/responses')
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
                return redirect(url_for('guest_info'))
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
    
    if request.method == 'GET' and guests:
        if guest1:
            form.g1_first_name.data = guest1.first_name
            form.g1_last_name.data = guest1.last_name
            form.g1_title_rank.data = guest1.title_rank
            form.g1_allergy_notes.data = guest1.allergy_notes
            form.g1_fun_fact.data = guest1.fun_fact
        
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


if __name__ == '__main__':
    app.run(debug=True)
