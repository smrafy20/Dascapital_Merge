from flask import Blueprint, render_template, session, redirect, url_for, request
from models import Payee, User

payee_bp = Blueprint('payees', __name__)

@payee_bp.route('/favourite_accounts', methods=['GET', 'POST'])
def favourite_accounts():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    user_id = session['user_id']

    if request.method == 'POST':
        # Handle delete
        payee_id = request.form.get('delete_id')
        if payee_id:
            payee = Payee.query.filter_by(id=payee_id, user_id=user_id).first()
            if payee:
                from db import db
                db.session.delete(payee)
                db.session.commit()
        return redirect(url_for('payees.favourite_accounts'))

    # GET: list payees
    payees = (
        Payee.query.filter_by(user_id=user_id)
        .order_by(Payee.timestamp.desc())
        .all()
    )

    # Join to get recipient names/phones (already stored) and also ensure user still exists
    enriched = []
    for p in payees:
        recip = User.query.get(p.recipient_user_id)
        enriched.append({
            'id': p.id,
            'recipient_name': p.recipient_name,
            'recipient_phone': p.recipient_phone,
            'exists': recip is not None
        })

    return render_template('favourite_accounts.html', payees=enriched)

