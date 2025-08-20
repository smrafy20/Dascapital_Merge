# DashCapital - Money Request Application

A Flask-based money request application that allows users to send and receive money requests with real-time notifications and transaction processing.

## Features

### 🔐 User Management
- **Registration**: Users sign up with name, phone, email, and password
- **Classification**: Automatic user classification (Native: +8801 numbers, Foreign: others)
- **Authentication**: Secure login using phone number and password
- **Starting Balance**: New users receive 100 BDT welcome bonus

### 💰 Money Request System
- **Send Requests**: Search users by name and send money requests with optional notes
- **Receive Requests**: Real-time notifications with accept/reject options
- **Transaction Processing**: Automatic balance transfers on request acceptance
- **Request History**: Track sent and received requests with status updates

### 📊 Dashboard
- **Balance Display**: Prominent current balance with user type indicator
- **Pending Requests**: Popup notifications for incoming requests
- **Transaction History**: Recent transaction log with detailed information
- **Quick Actions**: Easy access to send requests and view history

## Tech Stack

- **Backend**: Flask (Python)
- **Database**: MySQL with SQLAlchemy ORM
- **Frontend**: HTML, CSS, JavaScript
- **Styling**: Inline CSS with modern gradient design
- **Security**: Werkzeug password hashing

## Installation & Setup

### Prerequisites
- Python 3.7+
- MySQL Server
- pip (Python package manager)

### Step 1: Clone the Repository
```bash
git clone <repository-url>
cd dashcapital
```

### Step 2: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 3: Configure Database
1. Start your MySQL server
2. Update database credentials in `app.py`:
   ```python
   app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://username:password@localhost/dashcapital'
   ```

### Step 4: Setup Database
```bash
python setup_database.py
```

This will:
- Create the `dashcapital` database
- Create all required tables
- Prepare the system for user registration

### Step 5: Run the Application
```bash
python app.py
```

Visit `http://localhost:5000` in your browser.

## Modernized run (this repository variant)
- Preferred entrypoint: `main.py` (blueprints + `models.py`)
- DB config: `config.py` (SQLALCHEMY_DATABASE_URI)
- Initialize DB: `python init_saif_db.py`
- Run app: `python main.py` (http://localhost:1158)

A `wsgi.py` is also provided for production servers (imports `app` from `main.py`).

## Getting Started

The application starts with an empty database. You'll need to register your first user account through the registration page.

## Usage Guide

### 1. Registration
- Navigate to the registration page
- Fill in your details (name, phone, email, password)
- Phone numbers starting with "+8801" are classified as native users
- Receive 100 BDT starting balance

### 2. Login
- Use your phone number and password to login
- Redirected to dashboard after successful authentication

### 3. Sending Money Requests
- Click "Send Money Request" from dashboard
- Search for users by typing their name
- Select recipient from search results
- Enter amount and optional note
- Submit request

### 4. Receiving Money Requests
- Pending requests appear as notifications on dashboard
- View request details (amount, sender, note)
- Accept to transfer money from your balance to sender
- Reject to decline without money transfer

### 5. Dashboard Features
- View current balance prominently displayed
- See pending incoming requests
- Track recent sent requests with status
- View transaction history

## Database Schema

### Users Table
- `id`: Primary key
- `name`: User's full name
- `phone_number`: Unique phone number (login credential)
- `email`: Unique email address
- `password_hash`: Encrypted password
- `user_type`: 'native' or 'foreign' based on phone number
- `balance`: Current account balance (Decimal)
- `created_at`: Registration timestamp

### Money Requests Table
- `id`: Primary key
- `sender_id`: Foreign key to Users (request sender)
- `recipient_id`: Foreign key to Users (request recipient)
- `amount`: Requested amount (Decimal)
- `note`: Optional message
- `status`: 'pending', 'accepted', or 'rejected'
- `created_at`: Request creation timestamp
- `processed_at`: Request processing timestamp

### Transactions Table
- `id`: Primary key
- `user_id`: Foreign key to Users
- `transaction_type`: 'credit' or 'debit'
- `amount`: Transaction amount (Decimal)
- `description`: Transaction description
- `request_id`: Foreign key to Money Requests (optional)
- `created_at`: Transaction timestamp

## API Endpoints

- `GET /`: Redirect to dashboard or login
- `GET /register`: Registration form
- `POST /register`: Process registration
- `GET /login`: Login form
- `POST /login`: Process login
- `GET /logout`: Logout user
- `GET /dashboard`: Main dashboard
- `GET /send_request`: Send money request form
- `POST /send_request`: Process money request
- `GET /search_users`: AJAX user search
- `POST /process_request`: Process accept/reject requests

## Security Features

- Password hashing using Werkzeug
- Session-based authentication
- Input validation and sanitization
- SQL injection prevention via SQLAlchemy ORM
- CSRF protection through form validation

## Future Enhancements

- Phone number verification via OTP
- Email notifications for requests
- Transaction limits and daily caps
- Admin panel for user management
- Mobile app integration
- International currency support
- Request expiration system
- Advanced transaction filtering

## Troubleshooting

### Database Connection Issues
- Verify MySQL server is running
- Check database credentials in `app.py`
- Ensure `dashcapital` database exists

### Import Errors
- Install all dependencies: `pip install -r requirements.txt`
- Check Python version compatibility

### Balance Issues
- Verify transaction logic in `process_request` route
- Check decimal precision in database schema

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is licensed under the MIT License.
