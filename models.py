from db import db
from datetime import datetime

class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False, unique=True)
    phone = db.Column(db.String(20), nullable=False, unique=True)
    nid = db.Column(db.String(20), nullable=False, unique=True)
    pin = db.Column(db.String(100), nullable=False)
    dob = db.Column(db.Date, nullable=False)
    balance = db.Column(db.Float, default=0.0, nullable=False)

    transactions = db.relationship('Transaction', backref='user', lazy=True)

class Payee(db.Model):
    __tablename__ = 'payees'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    recipient_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    recipient_name = db.Column(db.String(100), nullable=False)
    recipient_phone = db.Column(db.String(20), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'recipient_user_id', name='uq_payee_user_recipient'),
    )


class Transaction(db.Model):
    __tablename__ = 'transactions'

    id = db.Column(db.Integer, primary_key=True)
    trx_id = db.Column(db.String(50), nullable=False, unique=True)
    type = db.Column(db.String(10), nullable=False)  # 'add' or 'send'
    amount = db.Column(db.Float, nullable=False)
    method = db.Column(db.String(50), nullable=False)
    source_dest = db.Column(db.String(100))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)


class Notification(db.Model):
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    type = db.Column(db.String(50), nullable=False)  # e.g., 'credit', 'debit', 'info'
    title = db.Column(db.String(120), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read_at = db.Column(db.DateTime, nullable=True)


class MoneyRequest(db.Model):
    __tablename__ = 'money_requests'

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # requester
    recipient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # payer
    amount = db.Column(db.Float, nullable=False)
    note = db.Column(db.String(255))
    status = db.Column(db.String(20), default='pending', nullable=False)  # pending/accepted/rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime)


# --- Split Bill Models (inspired by Sadman module) ---
class SplitBill(db.Model):
    __tablename__ = 'split_bills'

    id = db.Column(db.Integer, primary_key=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    destination_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # receiver of shares
    title = db.Column(db.String(120), nullable=False)
    note = db.Column(db.Text)
    total_amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='open', nullable=False)  # open/completed/cancelled
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)


class SplitBillShare(db.Model):
    __tablename__ = 'split_bill_shares'

    id = db.Column(db.Integer, primary_key=True)
    split_bill_id = db.Column(db.Integer, db.ForeignKey('split_bills.id'), nullable=False)
    participant_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending', nullable=False)  # pending/paid/rejected
    paid_at = db.Column(db.DateTime)

