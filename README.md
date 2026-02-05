# EECS Dining-Out RSVP System

A Flask-based web application for managing RSVPs and guest information for the EECS Dining-Out

## Features

- RSVP submission with email validation
- Cookie-based user recognition
- Guest information collection (meal preferences, allergies, fun facts)
- Payment status tracking
- Admin views for responses and payment tracking
- Guest removal workflow when reducing guest count
- Docker containerization for easy deployment

## API Endpoints

### Public Endpoints

#### `GET /`

##### Home Page

- Displays event information and welcome message
- Shows different options based on cookie presence:
  - With cookie: "Provide Guest Information" and "New Reservation" buttons
  - Without cookie: "RSVP Now" and "I Already Have a Reservation" buttons
- Displays payment information ($60/guest) with Venmo QR code

#### `GET/POST /rsvp`

##### RSVP Form

- **Query Parameters:**
  - `action=modify` - Pre-fill form with existing data for editing
  - `action=delete` - Delete existing RSVP
  - `action=new` - Create new reservation (bypasses welcome back page)
- **Form Fields:**
  - `name` - Full name (required)
  - `email` - @westpoint.edu email (required)
  - `num_guests` - Number of guests: 1 or 2 (required)
- **Behavior:**
  - Checks for existing RSVP via cookie
  - Shows welcome back page if RSVP exists
  - Generates 6-character reservation ID (2 initials + 4 digits)
  - Sets 1-year cookie on successful submission
  - Redirects to `/confirm-update` if email already exists

#### `GET/POST /confirm-update`

##### Confirm RSVP Update

- Displays comparison between existing and new RSVP data
- **Actions:**
  - Update - Apply changes to existing RSVP
  - Cancel - Discard changes and return to form
- If guest count decreases, redirects to `/remove-guest`

#### `GET/POST /remove-guest`

##### Guest Removal Selection

- Displayed when user reduces guest count from 2 to 1
- Shows radio button selection of guests to remove
- If guest 1 is removed, automatically renumbers guest 2 to guest 1
- Preserves all guest information during renumbering

#### `GET /success`

##### Success/Confirmation Page

- Displays reservation ID
- Shows payment information with Venmo QR code
- Provides "Return to Home" button

#### `GET/POST /guest-info`

##### Guest Information Form/View

- **Query Parameters:**
  - `rsvp_id` - Direct access to specific RSVP (for admin links)
  - `action=edit` - Force edit mode even if data exists
- **Lookup Mode** (no cookie/session):
  - Shows form to lookup reservation by ID or email
  - Sets session variable on successful lookup
- **View Mode** (data exists):
  - Displays all submitted guest information
  - Shows payment status badge
  - "Modify Guest Information" button
  - "Add a Second Guest" button (if only 1 guest)
  - Payment information section at bottom
- **Form Mode** (no data or edit action):
  - Collects detailed information for each guest:
    - First Name, Last Name, Title/Rank
    - Meal Preference (Beef, Chicken, Vegetarian, Fish, Vegan)
    - Allergy Notes (optional)
    - Fun Fact (optional)
  - Dynamically shows fields based on `num_guests` value

#### `POST /add-guest`

##### Add Second Guest

- Updates RSVP from 1 guest to 2 guests
- If payment status is already paid (cash/check or Venmo):
  - Changes payment status to "guests changed - not paid"
- Redirects to guest info form to enter second guest details

### Admin Endpoints

#### `GET /responses`

##### All RSVP Responses

- Displays table of all RSVPs with:
  - Reservation ID
  - Name
  - Email
  - Number of Guests
  - Submission timestamp
  - Last updated timestamp
  - "View/Edit" link to guest info page
- Uses wide container (1400px) for better table display

#### `GET/POST /payment-tracking`

##### Payment Status Management

- Displays table of all RSVPs with payment tracking
- **Quick Action Buttons:**
  - 💵 Cash - Quick update to "cash/check"
  - 📱 Venmo - Quick update to "Venmo"
  - Only shown for unpaid or "guests changed" statuses
- **Dropdown Selector:**
  - Not Paid
  - Cash/Check
  - Venmo
  - Guests Changed - Not Paid
- Updates occur without flash messages (no page jump)
- Uses wide container (1400px) for better table display

## Database Models

### RSVP

- `id` - Primary key
- `reservation_id` - 6-character unique ID (2 initials + 4 digits)
- `name` - Guest name
- `email` - @westpoint.edu email
- `num_guests` - Number of guests (1 or 2)
- `payment_status` - Payment status (default: "not paid")
- `created_at` - Timestamp
- `updated_at` - Timestamp

### Guest

- `id` - Primary key
- `rsvp_id` - Foreign key to RSVP
- `guest_number` - Guest number (1 or 2)
- `first_name` - First name
- `last_name` - Last name
- `title_rank` - Title or rank (optional)
- `meal_preference` - Buffet dinner (auto-set)
- `allergy_notes` - Allergy information (optional)
- `fun_fact` - Fun fact about guest (optional)
- `created_at` - Timestamp
- `updated_at` - Timestamp

## Cookie Management

- **Cookie Name:** `rsvp_id`
- **Expiration:** 1 year
- **Usage:** Automatically recognizes returning users
- **Storage:** Stores RSVP database ID (integer)

## Session Variables

- `show_reservation_id` - Temporarily stores reservation ID for success page
- `guest_info_rsvp_id` - Stores RSVP ID for guest info access without cookie
- `pending_rsvp` - Temporarily stores RSVP data during update confirmation
- `rsvp_id_for_removal` - Stores RSVP ID during guest removal process

## Payment Information

- **Cost:** $60 per guest
- **Payment Methods:** Cash/Check or Venmo
- **Payment Statuses:**
  - Not Paid (default)
  - Cash/Check
  - Venmo
  - Guests Changed - Not Paid (automatic when adding guest after payment)

## Deployment

The application is containerized with Docker and includes:

- Python 3.12 slim base image
- Gunicorn WSGI server (port 8080)
- SQLite database with volume persistence
- Non-root user for security

### Docker Commands

```bash
# Build image
docker build -t lucasruff/rsvp_system:latest .

# Push to Docker Hub
docker push lucasruff/rsvp_system:latest

# Pull and deploy on server
docker-compose pull
docker-compose down
docker-compose up -d
```

## Environment Variables

- `SECRET_KEY` - Flask secret key (set in docker-compose.yml via .env file)

## Technology Stack

- **Backend:** Flask 3.0.0
- **Database:** SQLite with SQLAlchemy 3.1.1 ORM
- **Forms:** Flask-WTF 1.2.1 with WTForms
- **Server:** Gunicorn 21.2.0
- **Containerization:** Docker + Docker Compose
- **Deployment:** Google Cloud Platform (e2-micro VM)
