from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, ValidationError, Optional


def validate_westpoint_email(form, field):
    """Custom validator to ensure email ends with @westpoint.edu"""
    if not field.data.lower().endswith('@westpoint.edu'):
        raise ValidationError('Email must be a @westpoint.edu address.')


class RSVPForm(FlaskForm):
    """Form for collecting RSVP information."""
    
    name = StringField('Full Name', validators=[
        DataRequired(message='Please enter your name.')
    ])
    
    email = StringField('Email Address', validators=[
        DataRequired(message='Please enter your email address.'),
        Email(message='Please enter a valid email address.'),
        validate_westpoint_email
    ])
    
    num_guests = SelectField('Number of Guests', 
                             choices=[('1', '1'), ('2', '2')],
                             default='1',
                             validators=[DataRequired()])
    
    submit = SubmitField('Submit RSVP')


class UpdateConfirmForm(FlaskForm):
    """Form for confirming RSVP update."""
    
    update = SubmitField('Update My RSVP')
    cancel = SubmitField('Cancel')


class PaymentStatusForm(FlaskForm):
    """Form for updating payment status."""
    
    payment_status = SelectField('Payment Status',
                                 choices=[
                                     ('not paid', 'Not Paid'),
                                     ('pending - cash', 'Pending - Cash'),
                                     ('pending - Venmo', 'Pending - Venmo'),
                                     ('cash', 'Cash (Confirmed)'),
                                     ('Venmo', 'Venmo (Confirmed)'),
                                     ('guests changed - not paid', 'Guests Changed - Not Paid')
                                 ],
                                 validators=[DataRequired()])
    
    submit = SubmitField('Update Payment')


class GuestInfoForm(FlaskForm):
    """Form for collecting guest information."""
    
    # Guest 1 fields
    g1_first_name = StringField('First Name', validators=[DataRequired()])
    g1_last_name = StringField('Last Name', validators=[DataRequired()])
    g1_title_rank = StringField('Title/Rank', validators=[Optional()])
    g1_allergy_notes = TextAreaField('Allergy Notes', validators=[Optional()])
    g1_fun_fact = TextAreaField('Fun Fact', validators=[Optional()])
    
    # Guest 2 fields (optional, shown only if num_guests == 2)
    g2_first_name = StringField('First Name', validators=[Optional()])
    g2_last_name = StringField('Last Name', validators=[Optional()])
    g2_title_rank = StringField('Title/Rank', validators=[Optional()])
    g2_allergy_notes = TextAreaField('Allergy Notes', validators=[Optional()])
    g2_fun_fact = TextAreaField('Fun Fact', validators=[Optional()])
    
    submit = SubmitField('Save Guest Information')


class ReservationLookupForm(FlaskForm):
    """Form for looking up a reservation by ID or email."""
    
    lookup_value = StringField('Reservation ID or Email', 
                               validators=[DataRequired(message='Please enter your reservation ID or email address.')])
    
    submit = SubmitField('Look Up Reservation')
