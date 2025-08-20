from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
import uuid
from db import db
from models import User, Transaction, Payee, Notification

money_bp = Blueprint('money', __name__)

@money_bp.route('/add_money', methods=['GET', 'POST'])
def add_money():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        method = request.form['method']
        source_number = request.form['source_number']
        amount = float(request.form['amount'])
        trx_id = str(uuid.uuid4())[:8]

        user = User.query.get(session['user_id'])
        if not user:
            session.clear()
            return redirect(url_for('auth.login'))

        user.balance = (user.balance or 0) + amount

        trx = Transaction(
            user_id=user.id,
            trx_id=trx_id,
            type='add',
            amount=amount,
            method=method,
            source_dest=source_number
        )

        db.session.add(trx)
        db.session.commit()

        flash(f"Successfully added {amount} via {method}.")
        return redirect(url_for('dashboard.dashboard'))

    return render_template('add_money.html')


# Add Money via Bank Account
@money_bp.route('/bank', methods=['GET', 'POST'])
def add_money_bank():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        account_no = request.form.get('accountNo', '').strip()
        amount_raw = request.form.get('amount', '').strip()

        # Basic validation
        if not account_no:
            flash('Bank account number is required.')
            return render_template('bank.html', success=False)

        try:
            amount = float(amount_raw)
        except Exception:
            flash('Amount must be a valid number.')
            return render_template('bank.html', success=False)

        if amount <= 0:
            flash('Amount must be greater than 0.')
            return render_template('bank.html', success=False)

        user = User.query.get(session['user_id'])
        if not user:
            session.clear()
            return redirect(url_for('auth.login'))

        # Update balance and create transaction
        user.balance = (user.balance or 0) + amount
        trx_id = str(uuid.uuid4())[:8]
        masked_acc = account_no if len(account_no) < 4 else ("****" + account_no[-4:])
        trx = Transaction(
            user_id=user.id,
            trx_id=trx_id,
            type='add',
            amount=amount,
            method='bank',
            source_dest=masked_acc
        )

        db.session.add(trx)
        db.session.commit()

        # Show success popup on the same page per template logic
        return render_template('bank.html', success=True)

    # GET
    return render_template('bank.html', success=False)


# Add Money via Credit/Debit Card
@money_bp.route('/card', methods=['GET', 'POST'])
def add_money_card():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        card_no = request.form.get('cardNo', '').replace(' ', '').strip()
        amount_raw = request.form.get('amount', '').strip()
        expiry = request.form.get('expiry', '').strip()
        cvc = request.form.get('cvc', '').strip()

        # Basic validation
        if not card_no or len(card_no) < 12:
            flash('Enter a valid card number.')
            return redirect(url_for('money.add_money_card'))

        try:
            amount = float(amount_raw)
        except Exception:
            flash('Amount must be a valid number.')
            return redirect(url_for('money.add_money_card'))

        if amount <= 0:
            flash('Amount must be greater than 0.')
            return redirect(url_for('money.add_money_card'))

        if not expiry or not cvc:
            flash('Expiry and CVC are required.')
            return redirect(url_for('money.add_money_card'))

        user = User.query.get(session['user_id'])
        if not user:
            session.clear()
            return redirect(url_for('auth.login'))

        # Update balance and create transaction
        user.balance = (user.balance or 0) + amount
        trx_id = str(uuid.uuid4())[:8]
        masked_card = card_no if len(card_no) < 4 else ("**** **** **** " + card_no[-4:])
        trx = Transaction(
            user_id=user.id,
            trx_id=trx_id,
            type='add',
            amount=amount,
            method='card',
            source_dest=masked_card
        )

        db.session.add(trx)
        db.session.commit()

        flash(f"Successfully added {amount} via card.")
        return redirect(url_for('dashboard.dashboard'))

    # GET
    return render_template('card.html')



# Step 1: Show choice page for send money method
@money_bp.route('/send_money', methods=['GET'])
def send_money_choice():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    return render_template('send_money_choice.html')  # This template has buttons for local & international


# Step 2: Send money locally (with PIN check and balance check)
@money_bp.route('/send_money/local', methods=['GET', 'POST'])
def send_money_local():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        recipient_phone = request.form.get('recipient_phone', '').strip()
        amount_raw = request.form.get('amount', '').strip()
        pin = request.form.get('pin', '').strip()
        save_info = request.form.get('save_info') == 'on'
        trx_id = str(uuid.uuid4())[:8]

        sender = User.query.get(session['user_id'])
        if not sender:
            session.clear()
            return redirect(url_for('auth.login'))

        # Validate amount
        try:
            amount = float(amount_raw)
            if amount <= 0:
                return redirect(url_for('money.send_money_local', status='invalid_amount'))
        except Exception:
            return redirect(url_for('money.send_money_local', status='invalid_amount'))

        # PIN check
        if pin != sender.pin:
            return redirect(url_for('money.send_money_local', status='incorrect_pin'))

        # Balance check
        if (sender.balance or 0) < amount:
            return redirect(url_for('money.send_money_local', status='insufficient_balance'))

        # Recipient must exist in-app
        recipient = User.query.filter_by(phone=recipient_phone).first()
        if not recipient:
            return redirect(url_for('money.send_money_local', status='recipient_not_found'))

        # Save payee
        if save_info:
            existing_payee = Payee.query.filter_by(user_id=sender.id, recipient_user_id=recipient.id).first()
            if not existing_payee:
                payee = Payee(
                    user_id=sender.id,
                    recipient_user_id=recipient.id,
                    recipient_name=recipient.full_name,
                    recipient_phone=recipient.phone
                )
                db.session.add(payee)

        # Perform transfer
        sender.balance -= amount
        recipient.balance = (recipient.balance or 0) + amount

        trx = Transaction(
            user_id=sender.id,
            trx_id=trx_id,
            type='send',
            amount=amount,
            method='wallet',
            source_dest=recipient_phone
        )

        # Notifications (use names/phones)
        db.session.add_all([
            trx,
            Notification(user_id=sender.id, type='debit', title='Money Sent', message=f'You sent {amount:.2f} to {recipient.full_name} ({recipient.phone})'),
            Notification(user_id=recipient.id, type='credit', title='Money Received', message=f'{sender.full_name} ({sender.phone}) sent you {amount:.2f}')
        ])
        db.session.commit()

        return redirect(url_for('money.send_money_local', status='success'))

    # GET: allow prefill via query params
    prefill_phone = request.args.get('phone', '')
    prefill_name = request.args.get('name', '')
    return render_template('send_money_local.html', prefill_phone=prefill_phone, prefill_name=prefill_name)


# Step 3: Send money internationally (BDT to USD conversion, PIN check)
@money_bp.route('/send_money/international', methods=['GET'])
def send_money_international():
    # For GET, just render the international send form
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    return render_template('send_money_international.html')


# New route: handle POST from fetch /submit_transaction (international send JSON)
@money_bp.route('/submit_transaction', methods=['POST'])
def submit_transaction():
    if 'user_id' not in session:
        return jsonify(success=False, message="User not logged in"), 401

    data = request.get_json()
    if not data:
        return jsonify(success=False, message="Invalid JSON data"), 400

    receivers_name = data.get('receivers_name')
    country = data.get('country')
    amount_bdt = data.get('amount')
    recipient_phone = data.get('recipient_phone')
    save_flag = bool(data.get('save'))

    # Basic validation (no PIN here; handled at confirmation)
    if not all([receivers_name, country, amount_bdt, recipient_phone]):
        return jsonify(success=False, message="Missing required fields"), 400

    try:
        amount_bdt = float(amount_bdt)
        if amount_bdt <= 0:
            return jsonify(success=False, message="Invalid amount"), 400
    except Exception:
        return jsonify(success=False, message="Amount must be a number"), 400

    EXCHANGE_RATE = 130  # BDT to USD conversion rate

    # Ensure session user exists
    sender = User.query.get(session['user_id'])
    if not sender:
        session.clear()
        return jsonify(success=False, message="Session expired, please log in again"), 401

    # Validate recipient exists early
    recipient = User.query.filter_by(phone=recipient_phone).first()
    if not recipient:
        return jsonify(success=False, message="Recipient not found"), 400

    # Prepare data for confirmation page (no balance changes yet)
    amount_usd = round(amount_bdt / EXCHANGE_RATE, 2)
    pending = {
        'receivers_name': receivers_name,
        'country': country,
        'amount_bdt': amount_bdt,
        'amount_usd': amount_usd,
        'recipient_phone': recipient_phone,
        'trx_id': str(uuid.uuid4())[:8],
        'save': save_flag
    }
    session['int_transfer'] = pending

    return jsonify(success=True)


# International confirm page (GET)
@money_bp.route('/int_money_confirm_transaction', methods=['GET'])
def int_money_confirm_transaction():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    pending = session.get('int_transfer')
    if not pending:
        return redirect(url_for('money.send_money_international'))
    return render_template(
        'int_money_confirm.html',
        receivers_name=pending['receivers_name'],
        country=pending['country'],
        amount_in_bdt=pending['amount_bdt'],
        amount_in_selected_country=pending['amount_usd'],
        trx_id=pending['trx_id'],
        recipient_phone=pending['recipient_phone']
    )

# Finalize international transfer (POST)
@money_bp.route('/confirm_send_money', methods=['POST'])
def confirm_send_money():
    if 'user_id' not in session:
        return jsonify(status='error', message='Not logged in'), 401

    pending = session.get('int_transfer')
    if not pending:
        return jsonify(status='error', message='No pending transfer'), 400

    pin = request.form.get('pin', '').strip()
    if not pin:
        return jsonify(status='error', message='PIN is required'), 400

    sender = User.query.get(session['user_id'])
    if not sender:
        session.clear()
        return jsonify(status='error', message='Session expired'), 401

    if pin != sender.pin:
        return jsonify(status='error', message='Incorrect PIN'), 400

    # Validate recipient
    recipient = User.query.filter_by(phone=pending['recipient_phone']).first()
    if not recipient:
        return jsonify(status='error', message='Recipient not found'), 400

    amount_bdt = float(pending['amount_bdt'])
    if (sender.balance or 0) < amount_bdt:
        return jsonify(status='error', message='Insufficient balance'), 400

    # Optional: Save payee on confirmation if requested
    if pending.get('save'):
        existing_payee = Payee.query.filter_by(user_id=sender.id, recipient_user_id=recipient.id).first()
        if not existing_payee:
            payee = Payee(
                user_id=sender.id,
                recipient_user_id=recipient.id,
                recipient_name=recipient.full_name,
                recipient_phone=recipient.phone
            )
            db.session.add(payee)

    # Perform balance updates
    sender.balance -= amount_bdt
    recipient.balance = (recipient.balance or 0) + amount_bdt

    trx = Transaction(
        user_id=sender.id,
        trx_id=pending['trx_id'],
        type='send_international',
        amount=pending['amount_usd'],
        method='international',
        source_dest=f"{pending['receivers_name']} ({pending['country']}) -> {pending['recipient_phone']}"
    )

    # Add notifications and commit
    db.session.add_all([
        trx,
        Notification(user_id=sender.id, type='debit', title='International Transfer', message=f'You sent {amount_bdt:.2f} BDT to {recipient.full_name} ({recipient.phone})')
    ])
    # For the recipient, we also add a credit notification
    db.session.add(Notification(user_id=recipient.id, type='credit', title='Money Received', message=f'{sender.full_name} ({sender.phone}) sent you {amount_bdt:.2f} BDT'))
    db.session.commit()

    # Clear pending
    session.pop('int_transfer', None)

    return jsonify(status='success', message='International transfer completed successfully.')

# Search users by name or phone for autocomplete (exclude current user)
@money_bp.route('/search_users', methods=['GET'])
def search_users():
    if 'user_id' not in session:
        return jsonify(success=False, message='Not logged in'), 401

    q = (request.args.get('q') or '').strip()
    if len(q) < 1:
        return jsonify(success=True, users=[])

    from sqlalchemy import or_
    current_id = session['user_id']
    results = (User.query
               .filter(User.id != current_id)
               .filter(or_(User.full_name.ilike(f"%{q}%"), User.phone.ilike(f"%{q}%")))
               .order_by(User.full_name.asc())
               .limit(10)
               .all())

    users = [{
        'id': u.id,
        'name': u.full_name,
        'phone': u.phone
    } for u in results]

    return jsonify(success=True, users=users)

