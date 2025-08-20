from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Response, stream_with_context
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import DECIMAL, text, inspect
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os
import json
from decimal import Decimal, ROUND_HALF_UP

app = Flask(__name__)

# Load configuration
try:
    from config import Config
    app.config.from_object(Config)
except ImportError:
    # Fallback configuration if config.py doesn't exist
    app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:1234@localhost/dascapital_2'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Database Models
class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone_number = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    user_type = db.Column(db.String(20), nullable=False)  # 'native' or 'foreign'
    balance = db.Column(DECIMAL(10, 2), default=100.00, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    sent_requests = db.relationship('MoneyRequest', foreign_keys='MoneyRequest.sender_id', backref='sender', lazy='dynamic')
    received_requests = db.relationship('MoneyRequest', foreign_keys='MoneyRequest.recipient_id', backref='recipient', lazy='dynamic')

    def __repr__(self):
        return f'<User {self.name} ({self.phone_number})>'

    def classify_user_type(self):
        """Classify user as native or foreign based on phone number"""
        if self.phone_number.startswith('+8801'):
            return 'native'
        return 'foreign'

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class MoneyRequest(db.Model):
    __tablename__ = 'money_requests'

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount = db.Column(DECIMAL(10, 2), nullable=False)
    note = db.Column(db.Text)
    status = db.Column(db.String(20), default='pending', nullable=False)  # 'pending', 'accepted', 'rejected'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime)

    def __repr__(self):
        return f'<MoneyRequest {self.amount} from {self.sender_id} to {self.recipient_id}>'

class Transaction(db.Model):
    __tablename__ = 'transactions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    transaction_type = db.Column(db.String(20), nullable=False)  # 'credit', 'debit'
    amount = db.Column(DECIMAL(10, 2), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    request_id = db.Column(db.Integer, db.ForeignKey('money_requests.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='transactions')
    money_request = db.relationship('MoneyRequest', backref='transactions')

    def __repr__(self):
        return f'<Transaction {self.transaction_type} {self.amount} for user {self.user_id}>'


class SplitBill(db.Model):
    __tablename__ = 'split_bills'

    id = db.Column(db.Integer, primary_key=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    destination_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # receiver
    title = db.Column(db.String(120), nullable=False)
    note = db.Column(db.Text)
    total_amount = db.Column(DECIMAL(10, 2), nullable=False)
    status = db.Column(db.String(20), default='open', nullable=False)  # 'open', 'completed', 'cancelled'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)

    creator = db.relationship('User', foreign_keys=[creator_id], backref='split_bills_created')
    destination = db.relationship('User', foreign_keys=[destination_id], backref='split_bills_received')
    shares = db.relationship('SplitBillShare', backref='split_bill', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<SplitBill {self.title} total={self.total_amount} created_by={self.creator_id}>'


class SplitBillShare(db.Model):
    __tablename__ = 'split_bill_shares'

    id = db.Column(db.Integer, primary_key=True)
    split_bill_id = db.Column(db.Integer, db.ForeignKey('split_bills.id'), nullable=False)
    participant_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount = db.Column(DECIMAL(10, 2), nullable=False)
    status = db.Column(db.String(20), default='pending', nullable=False)  # 'pending', 'paid', 'rejected'
    paid_at = db.Column(db.DateTime)

    participant = db.relationship('User', backref='split_shares')

    def __repr__(self):
        return f'<SplitBillShare bill={self.split_bill_id} participant={self.participant_id} amount={self.amount} status={self.status}>'

# Lightweight startup migration to add destination_id if missing (Flask >=3 safe)
# Runs once at module import/startup instead of using removed before_first_request

def ensure_destination_column():
    try:
        inspector = inspect(db.engine)
        # If tables are not created yet, skip silently
        if 'split_bills' not in inspector.get_table_names():
            return
        cols = [c['name'] for c in inspector.get_columns('split_bills')]
        if 'destination_id' not in cols:
            with db.engine.connect() as conn:
                conn.execute(text('ALTER TABLE split_bills ADD COLUMN destination_id INTEGER'))
                # Default existing rows to creator_id
                conn.execute(text('UPDATE split_bills SET destination_id = creator_id WHERE destination_id IS NULL'))
                conn.commit()
    except Exception as e:
        # Safe fail: just log to console; app can still run
        print('ensure_destination_column warning:', e)

# Invoke once at startup
try:
    with app.app_context():
        ensure_destination_column()
except Exception as e:
    print('startup ensure_destination_column error:', e)

# Routes
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name'].strip()
        phone_number = request.form['phone_number'].strip()
        email = request.form['email'].strip()
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        # Basic validation
        if not all([name, phone_number, email, password]):
            flash('All fields are required!', 'error')
            return render_template('register.html')

        if password != confirm_password:
            flash('Passwords do not match!', 'error')
            return render_template('register.html')

        if len(password) < 6:
            flash('Password must be at least 6 characters long!', 'error')
            return render_template('register.html')

        # Check if user already exists
        if User.query.filter_by(phone_number=phone_number).first():
            flash('Phone number already registered!', 'error')
            return render_template('register.html')

        if User.query.filter_by(email=email).first():
            flash('Email already registered!', 'error')
            return render_template('register.html')

        # Create new user
        user = User(
            name=name,
            phone_number=phone_number,
            email=email,
            password_hash=generate_password_hash(password),
            user_type='native' if phone_number.startswith('+8801') else 'foreign',
            balance=Decimal('100.00')
        )

        try:
            db.session.add(user)
            db.session.commit()
            flash('Registration successful! You can now login.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash('Registration failed. Please try again.', 'error')
            return render_template('register.html')

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        phone_number = request.form['phone_number'].strip()
        password = request.form['password']

        if not phone_number or not password:
            flash('Phone number and password are required!', 'error')
            return render_template('login.html')

        user = User.query.filter_by(phone_number=phone_number).first()

        if user and user.check_password(password):
            session['user_id'] = user.id
            session['user_name'] = user.name
            flash(f'Welcome back, {user.name}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid phone number or password!', 'error')
            return render_template('login.html')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('login'))

    # Get pending money requests (received)
    pending_requests = MoneyRequest.query.filter_by(
        recipient_id=user.id,
        status='pending'
    ).order_by(MoneyRequest.created_at.desc()).all()

    # Get recent transactions
    recent_transactions = Transaction.query.filter_by(
        user_id=user.id
    ).order_by(Transaction.created_at.desc()).limit(5).all()

    # Get sent requests status
    sent_requests = MoneyRequest.query.filter_by(
        sender_id=user.id
    ).order_by(MoneyRequest.created_at.desc()).limit(5).all()

    # Get pending split bill shares for current user
    from sqlalchemy.orm import aliased
    DestUser = aliased(User)
    pending_split_shares = db.session.query(
        SplitBillShare.id,
        SplitBillShare.amount,
        SplitBill.title.label('bill_title'),
        SplitBill.created_at,
        User.name.label('creator_name'),
        DestUser.name.label('destination_name')
    ).join(SplitBill, SplitBillShare.split_bill_id == SplitBill.id) \
     .join(User, SplitBill.creator_id == User.id) \
     .outerjoin(DestUser, SplitBill.destination_id == DestUser.id) \
     .filter(
        SplitBillShare.participant_id == user.id,
        SplitBillShare.status == 'pending'
    ).order_by(SplitBill.created_at.desc()).all()

    return render_template('dashboard.html',
                         user=user,
                         pending_requests=pending_requests,
                         recent_transactions=recent_transactions,
                         sent_requests=sent_requests,
                         pending_split_shares=pending_split_shares)

# In-memory per-session SSE queues (simple; non-persistent)
from collections import defaultdict, deque
sse_queues = defaultdict(lambda: deque(maxlen=100))

def sse_push(user_id, event_type, payload):
    try:
        sse_queues[user_id].append({'type': event_type, 'data': payload})
    except Exception as e:
        print('sse_push warning:', e)

@app.route('/events')
def sse_events():
    if 'user_id' not in session:
        return Response('unauthorized', status=401)
    user_id = session['user_id']

    def event_stream(uid):
        # Send an initial ping
        yield 'event: ping\ndata: {}\n\n'
        while True:
            q = sse_queues.get(uid)
            if q and len(q):
                # drain queue
                while True:
                    try:
                        evt = q.popleft()
                    except IndexError:
                        break
                    yield f"event: {evt['type']}\ndata: {json.dumps(evt['data'])}\n\n"
            # heartbeat to keep connection alive
            yield 'event: ping\ndata: {}\n\n'
            import time; time.sleep(5)

    return Response(stream_with_context(event_stream(user_id)), mimetype='text/event-stream')


@app.route('/dashboard_data')
def dashboard_data():
    """Optimized API endpoint for dashboard data updates"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    user_id = session['user_id']

    # Get user balance
    user_balance = db.session.query(User.balance).filter_by(id=user_id).first()
    if not user_balance:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    # Pending money requests (received)
    pending_requests = db.session.query(
        MoneyRequest.id,
        MoneyRequest.amount,
        MoneyRequest.note,
        MoneyRequest.created_at,
        User.name.label('sender_name'),
        User.phone_number.label('sender_phone')
    ).join(User, MoneyRequest.sender_id == User.id).filter(
        MoneyRequest.recipient_id == user_id,
        MoneyRequest.status == 'pending'
    ).order_by(MoneyRequest.created_at.desc()).all()

    pending_requests_data = [{
        'id': req.id,
        'sender_name': req.sender_name,
        'sender_phone': req.sender_phone,
        'amount': float(req.amount),
        'note': req.note,
        'created_at': req.created_at.strftime('%B %d, %Y at %I:%M %p')
    } for req in pending_requests]

    # Recent sent money requests (by current user)
    sent_requests = db.session.query(
        MoneyRequest.id,
        MoneyRequest.amount,
        MoneyRequest.status,
        MoneyRequest.created_at,
        User.name.label('recipient_name')
    ).join(User, MoneyRequest.recipient_id == User.id).filter(
        MoneyRequest.sender_id == user_id
    ).order_by(MoneyRequest.created_at.desc()).limit(3).all()

    sent_requests_data = [{
        'id': req.id,
        'recipient_name': req.recipient_name,
        'amount': float(req.amount),
        'status': req.status,
        'created_at': req.created_at.strftime('%b %d, %Y')
    } for req in sent_requests]

    # Recent transactions
    recent_transactions = Transaction.query.filter_by(
        user_id=user_id
    ).order_by(Transaction.created_at.desc()).limit(3).all()

    recent_transactions_data = [{
        'id': trans.id,
        'description': trans.description,
        'amount': float(trans.amount),
        'transaction_type': trans.transaction_type,
        'created_at': trans.created_at.strftime('%b %d, %Y at %I:%M %p')
    } for trans in recent_transactions]

    # Pending split bill shares for current user
    from sqlalchemy.orm import aliased
    DestUser = aliased(User)
    pending_split_shares = db.session.query(
        SplitBillShare.id,
        SplitBillShare.amount,
        SplitBillShare.split_bill_id,
        SplitBill.title.label('bill_title'),
        SplitBill.created_at,
        User.name.label('creator_name'),
        DestUser.name.label('destination_name')
    ).join(SplitBill, SplitBillShare.split_bill_id == SplitBill.id)
    pending_split_shares = pending_split_shares.join(User, SplitBill.creator_id == User.id).outerjoin(DestUser, SplitBill.destination_id == DestUser.id).filter(
        SplitBillShare.participant_id == user_id,
        SplitBillShare.status == 'pending'
    ).order_by(SplitBill.created_at.desc()).all()

    pending_split_shares_data = [{
        'id': s.id,
        'bill_title': s.bill_title,
        'creator_name': s.creator_name,
        'destination_name': s.destination_name,
        'amount': float(s.amount),
        'created_at': s.created_at.strftime('%B %d, %Y at %I:%M %p')
    } for s in pending_split_shares]

    return jsonify({
        'success': True,
        'balance': float(user_balance.balance),
        'pending_requests': pending_requests_data,
        'sent_requests': sent_requests_data,
        'recent_transactions': recent_transactions_data,
        'pending_split_shares': pending_split_shares_data,
    })

@app.route('/split_bill', methods=['GET', 'POST'])
def split_bill():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('login'))

    if request.method == 'POST':  # POST request
        title = request.form.get('title', '').strip()
        note = request.form.get('note', '').strip()
        total_amount = request.form.get('total_amount')
        split_mode = request.form.get('split_mode', 'equal')
        destination_phone = request.form.get('destination_phone', '').strip()
        # Participants: comma-separated ids from client
        participants_raw = request.form.get('participants', '').strip()

        # Basic validation
        if not title or not total_amount or not participants_raw or not destination_phone:
            flash('Please fill in title, total amount, destination phone, and at least one participant.', 'error')
            return render_template('split_bill.html', user=user)

        # Resolve destination user
        destination_user = User.query.filter_by(phone_number=destination_phone).first()
        if not destination_user:
            flash('Destination phone number not found. Enter a registered phone number.', 'error')
            return render_template('split_bill.html', user=user)

        try:
            total_amount = Decimal(total_amount)
            if total_amount <= 0:
                flash('Total amount must be greater than 0.', 'error')
                return render_template('split_bill.html', user=user)
        except:
            flash('Please enter a valid total amount.', 'error')
            return render_template('split_bill.html', user=user)

        # Parse participants
        try:
            participant_ids = [int(pid) for pid in participants_raw.split(',') if pid]
        except:
            flash('Invalid participants list.', 'error')
            return render_template('split_bill.html', user=user)

        # Remove duplicates only (self allowed)
        participant_ids = list(dict.fromkeys(participant_ids))
        if not participant_ids:
            flash('Please select at least one participant.', 'error')
            return render_template('split_bill.html', user=user)

        # Fetch participants and validate
        participants = User.query.filter(User.id.in_(participant_ids)).all()
        if len(participants) != len(participant_ids):
            flash('One or more selected participants were not found.', 'error')
            return render_template('split_bill.html', user=user)

        # Compute shares
        shares = []  # list of (participant_id, amount)
        if split_mode == 'equal':
            n = len(participants)
            # compute equal share to 2 decimal places, fix rounding on last share
            per = (total_amount / n).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            accumulated = Decimal('0.00')
            for idx, p in enumerate(participants):
                if idx == n - 1:
                    amount = (total_amount - accumulated).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                else:
                    amount = per
                    accumulated += per
                shares.append((p.id, amount))
        else:
            # custom mode: client sends shares as JSON-like string in 'shares' -> 'id:amount;id:amount'
            shares_raw = request.form.get('shares', '').strip()
            if not shares_raw:
                flash('Please provide custom shares for each participant.', 'error')
                return render_template('split_bill.html', user=user)
            try:
                tmp_map = {}
                for pair in shares_raw.split(';'):
                    if not pair:
                        continue
                    pid_str, amt_str = pair.split(':')
                    pid = int(pid_str)
                    amt = Decimal(amt_str)
                    if amt <= 0:
                        raise ValueError('Share must be > 0')
                    tmp_map[pid] = amt.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                # Validate all participants covered
                if set(tmp_map.keys()) != set(participant_ids):
                    raise ValueError('All participants must have a share')
            except Exception:
                flash('Invalid custom shares format.', 'error')
                return render_template('split_bill.html', user=user)

            sum_shares = sum(tmp_map.values(), Decimal('0.00')).quantize(Decimal('0.01'))
            if sum_shares != total_amount.quantize(Decimal('0.01')):
                flash('Sum of shares must equal total amount.', 'error')
                return render_template('split_bill.html', user=user)
            for pid in participant_ids:
                shares.append((pid, tmp_map[pid]))

        # Create SplitBill and Shares
        bill = SplitBill(
            creator_id=user.id,
            destination_id=destination_user.id,
            title=title,
            note=note,
            total_amount=total_amount,
            status='open'
        )

        try:
            db.session.add(bill)
            db.session.flush()  # get bill.id
            for pid, amt in shares:
                db.session.add(SplitBillShare(
                    split_bill_id=bill.id,
                    participant_id=pid,
                    amount=amt,
                    status='pending'
                ))
            db.session.commit()
            # AJAX vs normal form (robust content-type check)
            ct = request.headers.get('Content-Type', '') or request.content_type or ''
            if isinstance(ct, str) and ct.lower().startswith('application/x-www-form-urlencoded'):
                return f'Split bill "{title}" created successfully!'
            else:
                flash(f'Split bill "{title}" created successfully!', 'success')
                return redirect(url_for('dashboard'))
        except Exception:
            db.session.rollback()
            ct = request.headers.get('Content-Type', '') or request.content_type or ''
            if isinstance(ct, str) and ct.lower().startswith('application/x-www-form-urlencoded'):
                return 'Failed to create split bill. Please try again.'
            else:
                flash('Failed to create split bill. Please try again.', 'error')

        return render_template('split_bill.html', user=user)

    # GET request - render the form
    return render_template('split_bill.html', user=user)



@app.route('/process_split_share', methods=['POST'])
def process_split_share():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    data = request.get_json()
    share_id = data.get('share_id')
    action = data.get('action')  # 'pay' or 'reject'

    if not share_id or action not in ['pay', 'reject']:
        return jsonify({'success': False, 'message': 'Invalid request'}), 400

    user = User.query.get(session['user_id'])
    share = SplitBillShare.query.get(share_id)

    if not share or share.participant_id != user.id:
        return jsonify({'success': False, 'message': 'Share not found'}), 404

    if share.status != 'pending':
        return jsonify({'success': False, 'message': 'Share already processed'}), 400

    bill = SplitBill.query.get(share.split_bill_id)
    creator = User.query.get(bill.creator_id)
    destination = User.query.get(bill.destination_id) if bill.destination_id else creator

    try:
        if action == 'pay':
            # Balance check
            if user.balance < share.amount:
                return jsonify({'success': False, 'message': 'Insufficient balance'}), 400

            # Transfer to destination (fallback to creator if not set)
            user.balance -= share.amount
            destination.balance += share.amount

            # Transactions
            db.session.add(Transaction(
                user_id=user.id,
                transaction_type='debit',
                amount=share.amount,
                description=f'Split bill share paid to {destination.name}: {bill.title}'
            ))
            db.session.add(Transaction(
                user_id=destination.id,
                transaction_type='credit',
                amount=share.amount,
                description=f'Split bill share received from {user.name}: {bill.title}'
            ))

            share.status = 'paid'
            share.paid_at = datetime.utcnow()
        else:
            # reject
            share.status = 'rejected'

        # If all shares processed -> complete bill
        pending_left = SplitBillShare.query.filter_by(split_bill_id=bill.id, status='pending').count()
        if pending_left == 0:
            bill.status = 'completed'
            bill.completed_at = datetime.utcnow()

        db.session.commit()
        # notify current user to refresh parts of dashboard
        sse_push(user.id, 'dashboard-update', {'reason': f'split_share_{action}'})
        # also notify creator/destination in case balances/transactions affect their view
        sse_push(creator.id, 'dashboard-update', {'reason': f'split_share_{action}_other'})
        if destination.id != creator.id:
            sse_push(destination.id, 'dashboard-update', {'reason': f'split_share_{action}_dest'})
        msg = 'Share paid successfully' if action == 'pay' else 'Share rejected successfully'
        return jsonify({'success': True, 'message': msg})

    except Exception:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'An error occurred processing the share'}), 500



@app.route('/send_request', methods=['GET', 'POST'])
def send_request():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('login'))

    if request.method == 'POST':
        recipient_id = request.form.get('recipient_id')
        amount = request.form.get('amount')
        note = request.form.get('note', '').strip()

        # Validation
        if not recipient_id or not amount:
            flash('Please select a recipient and enter an amount.', 'error')
            return render_template('send_request.html', user=user)

        try:
            amount = Decimal(amount)
            if amount <= 0:
                flash('Amount must be greater than 0.', 'error')
                return render_template('send_request.html', user=user)
        except:
            flash('Please enter a valid amount.', 'error')
            return render_template('send_request.html', user=user)

        recipient = User.query.get(recipient_id)
        if not recipient:
            flash('Selected recipient not found.', 'error')
            return render_template('send_request.html', user=user)

        if recipient.id == user.id:
            flash('You cannot send a request to yourself.', 'error')
            return render_template('send_request.html', user=user)

        # Create money request
        money_request = MoneyRequest(
            sender_id=user.id,
            recipient_id=recipient.id,
            amount=amount,
            note=note
        )

        try:
            db.session.add(money_request)
            db.session.commit()
            # notify recipient for real-time update
            sse_push(recipient.id, 'dashboard-update', {'reason': 'money_request_received'})

            # Check if it's an AJAX request
            if request.headers.get('Content-Type') == 'application/x-www-form-urlencoded':
                return f'Money request sent to {recipient.name} successfully!'
            else:
                flash(f'Money request sent to {recipient.name} successfully!', 'success')
                return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()

            # Check if it's an AJAX request
            if request.headers.get('Content-Type') == 'application/x-www-form-urlencoded':
                return 'Failed to send money request. Please try again.'
            else:
                flash('Failed to send money request. Please try again.', 'error')

    return render_template('send_request.html', user=user)

@app.route('/search_users')
def search_users():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return jsonify({'users': []})

    include_self = str(request.args.get('include_self', '')).lower() in ('1', 'true', 'yes')

    base_q = User.query.filter(
        User.name.ilike(f"%{query}%")
    )
    if not include_self and 'user_id' in session:
        base_q = base_q.filter(User.id != session['user_id'])

    users = base_q.limit(10).all()

    user_list = [{
        'id': user.id,
        'name': user.name,
        'phone_number': user.phone_number,
        'user_type': user.user_type
    } for user in users]

    return jsonify({'users': user_list})

@app.route('/process_request', methods=['POST'])
def process_request():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    data = request.get_json()
    request_id = data.get('request_id')
    action = data.get('action')  # 'accept' or 'reject'

    if not request_id or action not in ['accept', 'reject']:
        return jsonify({'success': False, 'message': 'Invalid request'}), 400

    user = User.query.get(session['user_id'])
    money_request = MoneyRequest.query.get(request_id)

    if not money_request or money_request.recipient_id != user.id:
        return jsonify({'success': False, 'message': 'Request not found'}), 404

    if money_request.status != 'pending':
        return jsonify({'success': False, 'message': 'Request already processed'}), 400

    try:
        if action == 'accept':
            # Check if recipient has sufficient balance
            if user.balance < money_request.amount:
                return jsonify({'success': False, 'message': 'Insufficient balance'}), 400

            # Transfer money
            user.balance -= money_request.amount
            sender = User.query.get(money_request.sender_id)
            sender.balance += money_request.amount

            # Create transaction records
            recipient_transaction = Transaction(
                user_id=user.id,
                transaction_type='debit',
                amount=money_request.amount,
                description=f'Money sent to {sender.name}',
                request_id=money_request.id
            )

            sender_transaction = Transaction(
                user_id=sender.id,
                transaction_type='credit',
                amount=money_request.amount,
                description=f'Money received from {user.name}',
                request_id=money_request.id
            )

            db.session.add(recipient_transaction)
            db.session.add(sender_transaction)

        # Update request status
        money_request.status = action + 'ed'  # 'accepted' or 'rejected'
        money_request.processed_at = datetime.utcnow()

        db.session.commit()

        message = f'Request {action}ed successfully'
        if action == 'accept':
            message += f'. ৳{money_request.amount} transferred to {sender.name}.'

        return jsonify({'success': True, 'message': message})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'An error occurred while processing the request'}), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()

    app.run(port=5000, debug=True)
