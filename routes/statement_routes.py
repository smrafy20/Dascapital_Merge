from flask import Blueprint, render_template, session, redirect, url_for, send_file
from models import Transaction, User
import os
import csv

statement_bp = Blueprint('statements', __name__)

@statement_bp.route('/statements')
def statements():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    user_id = session['user_id']
    transactions = (Transaction.query
                    .filter_by(user_id=user_id)
                    .order_by(Transaction.timestamp.desc())
                    .all())

    # Build a map of counterparty phones -> user (for friendly names)
    phones = {str(t.source_dest).strip() for t in transactions if t.source_dest}
    users = User.query.filter(User.phone.in_(phones)).all() if phones else []
    users_by_phone = {u.phone: u for u in users}

    return render_template('statements.html', transactions=transactions, users_by_phone=users_by_phone)

@statement_bp.route('/statements/download')
def download_statements():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    user_id = session['user_id']
    transactions = Transaction.query.filter_by(user_id=user_id).all()

    filename = f"statements_{user_id}.csv"
    filepath = os.path.join("temp", filename)
    os.makedirs("temp", exist_ok=True)

    with open(filepath, 'w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['Transaction ID', 'Type', 'Amount', 'Method', 'Source/Destination', 'Timestamp'])

        for trx in transactions:
            writer.writerow([trx.trx_id, trx.type, trx.amount, trx.method, trx.source_dest, trx.timestamp])

    return send_file(filepath, as_attachment=True)
