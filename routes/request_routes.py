from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from db import db
from models import User, MoneyRequest, Notification, Transaction
from datetime import datetime

requests_bp = Blueprint('requests', __name__)


def require_login():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    return None


@requests_bp.route('/request_money', methods=['GET'])
def request_money_page():
    need = require_login()
    if need: return need
    return render_template('request_money.html')


@requests_bp.route('/request_money', methods=['POST'])
def request_money_submit():
    need = require_login()
    if need: return need

    sender_id = session['user_id']
    recipient_phone = request.form.get('recipient_phone', '').strip()
    amount_raw = request.form.get('amount', '').strip()
    note = request.form.get('note', '').strip()

    if not recipient_phone or not amount_raw:
        flash('Please select a recipient and enter an amount.')
        return redirect(url_for('requests.request_money_page'))

    try:
        amount = float(amount_raw)
        if amount <= 0:
            raise ValueError('Amount must be > 0')
    except Exception:
        flash('Enter a valid amount greater than 0.')
        return redirect(url_for('requests.request_money_page'))

    recipient = User.query.filter_by(phone=recipient_phone).first()
    if not recipient:
        flash('Recipient phone not found.')
        return redirect(url_for('requests.request_money_page'))

    if recipient.id == sender_id:
        flash('You cannot request money from yourself.')
        return redirect(url_for('requests.request_money_page'))

    req = MoneyRequest(sender_id=sender_id, recipient_id=recipient.id, amount=amount, note=note)
    db.session.add(req)
    db.session.flush()  # assign req.id
    # Notify recipient with actionable type and embedded request id token
    sender = User.query.get(sender_id)
    db.session.add(Notification(
        user_id=recipient.id,
        type='request',
        title='Money Request',
        message=f"{sender.full_name} ({sender.phone}) requested {amount:.2f} from you [REQ_ID:{req.id}]"
    ))
    db.session.commit()

    flash('Request sent successfully.')
    return redirect(url_for('requests.request_money_page'))


@requests_bp.route('/requests', methods=['GET'])
def requests_overview():
    need = require_login()
    if need: return need

    user_id = session['user_id']
    incoming = (MoneyRequest.query.filter_by(recipient_id=user_id)
               .order_by(MoneyRequest.created_at.desc()).all())
    outgoing = (MoneyRequest.query.filter_by(sender_id=user_id)
               .order_by(MoneyRequest.created_at.desc()).all())

    # Build user map for display (names/phones)
    ids = set()
    for r in incoming:
        ids.add(r.sender_id); ids.add(r.recipient_id)
    for r in outgoing:
        ids.add(r.sender_id); ids.add(r.recipient_id)
    users = User.query.filter(User.id.in_(ids)).all() if ids else []
    users_by_id = {u.id: u for u in users}

    return render_template('requests.html', incoming=incoming, outgoing=outgoing, users_by_id=users_by_id)


@requests_bp.route('/requests/api/process', methods=['POST'])
def process_request_api():
    if 'user_id' not in session:
        return jsonify(success=False, message='Not logged in'), 401

    data = request.get_json(silent=True) or {}
    req_id = data.get('id')
    action = data.get('action')  # 'accept' or 'reject'

    if action not in ('accept', 'reject'):
        return jsonify(success=False, message='Invalid action'), 400

    req = MoneyRequest.query.get(req_id)
    if not req or req.recipient_id != session['user_id']:
        return jsonify(success=False, message='Request not found'), 404

    if req.status != 'pending':
        return jsonify(success=False, message='Request already processed'), 400

    try:
        if action == 'accept':
            payer = User.query.get(req.recipient_id)  # current user
            receiver = User.query.get(req.sender_id)  # requester
            if (payer.balance or 0) < req.amount:
                return jsonify(success=False, message='Insufficient balance'), 400
            payer.balance -= req.amount
            receiver.balance = (receiver.balance or 0) + req.amount
            # Log transactions
            db.session.add(Transaction(user_id=payer.id, trx_id=f'RQ{req.id}D', type='send', amount=req.amount, method='request', source_dest=str(receiver.phone)))
            db.session.add(Transaction(user_id=receiver.id, trx_id=f'RQ{req.id}C', type='add', amount=req.amount, method='request', source_dest=str(payer.phone)))
            # Notifications
            db.session.add(Notification(user_id=receiver.id, type='credit', title='Request Paid', message=f'{payer.full_name} ({payer.phone}) paid your request of {req.amount:.2f}'))
            db.session.add(Notification(user_id=payer.id, type='debit', title='Request Accepted', message=f'You sent {req.amount:.2f} to {receiver.full_name} ({receiver.phone})'))
            req.status = 'accepted'
            req.processed_at = datetime.utcnow()
        else:
            req.status = 'rejected'
            req.processed_at = datetime.utcnow()
            db.session.add(Notification(user_id=req.sender_id, type='info', title='Request Rejected', message=f'{User.query.get(req.recipient_id).full_name} ({User.query.get(req.recipient_id).phone}) declined your request of {req.amount:.2f}'))
        db.session.commit()
        return jsonify(success=True)
    except Exception:
        db.session.rollback()
        return jsonify(success=False, message='Processing failed'), 500

@requests_bp.route('/requests/<int:req_id>', methods=['GET'])
def request_detail(req_id: int):
    need = require_login()
    if need: return need

    req = MoneyRequest.query.get(req_id)
    if not req:
        return render_template('request_detail.html', req=None)

    sender = User.query.get(req.sender_id)
    recipient = User.query.get(req.recipient_id)
    return render_template('request_detail.html', req=req, sender=sender, recipient=recipient, current_user_id=session['user_id'])



