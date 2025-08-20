from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from sqlalchemy.exc import IntegrityError
from db import db
from models import User, Transaction

profile_bp = Blueprint('profile', __name__)


def require_login():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    return None


@profile_bp.route('/profile', methods=['GET'])
def profile():
    need_login = require_login()
    if need_login:
        return need_login

    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))

    recent_transactions = (
        Transaction.query
        .filter_by(user_id=user.id)
        .order_by(Transaction.timestamp.desc())
        .limit(10)
        .all()
    )

    return render_template('profile.html', user=user, transactions=recent_transactions)


@profile_bp.route('/profile/update', methods=['POST'])
def update_profile():
    need_login = require_login()
    if need_login:
        return need_login

    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))

    first_name = request.form.get('first_name', '').strip()
    last_name = request.form.get('last_name', '').strip()
    email = request.form.get('email', '').strip()
    phone = request.form.get('phone', '').strip()
    nid = request.form.get('nid', '').strip()
    dob = request.form.get('dob', '').strip()

    # Basic validation
    if not all([first_name, last_name, email, phone, nid, dob]):
        flash('All fields are required.')
        return redirect(url_for('profile.profile'))

    # Uniqueness checks excluding current user
    conflict = User.query.filter(
        ((User.email == email) | (User.phone == phone) | (User.nid == nid)) & (User.id != user.id)
    ).first()
    if conflict:
        flash('Another account already uses that email, phone, or NID.')
        return redirect(url_for('profile.profile'))

    # Apply updates
    user.first_name = first_name
    user.last_name = last_name
    user.full_name = f"{first_name} {last_name}"
    user.email = email
    user.phone = phone
    user.nid = nid
    try:
        # Handle date input (YYYY-MM-DD)
        from datetime import datetime
        user.dob = datetime.strptime(dob, '%Y-%m-%d').date()
    except Exception:
        flash('Invalid date format for Date of Birth.')
        return redirect(url_for('profile.profile'))

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash('Update failed due to conflicting unique values.')
        return redirect(url_for('profile.profile'))

    # Keep session display name in sync
    session['user_name'] = user.full_name

    flash('Profile updated successfully.')
    return redirect(url_for('profile.profile'))


@profile_bp.route('/profile/change_pin', methods=['POST'])
def change_pin():
    need_login = require_login()
    if need_login:
        return need_login

    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))

    current_pin = request.form.get('current_pin', '').strip()
    new_pin = request.form.get('new_pin', '').strip()
    confirm_pin = request.form.get('confirm_pin', '').strip()

    if not all([current_pin, new_pin, confirm_pin]):
        flash('Please fill in all PIN fields.')
        return redirect(url_for('profile.profile'))

    if current_pin != user.pin:
        flash('Current PIN is incorrect.')
        return redirect(url_for('profile.profile'))

    if new_pin != confirm_pin:
        flash('New PIN and confirmation do not match.')
        return redirect(url_for('profile.profile'))

    if len(new_pin) < 4:
        flash('PIN must be at least 4 characters.')
        return redirect(url_for('profile.profile'))

    user.pin = new_pin
    db.session.commit()

    flash('PIN updated successfully.')
    return redirect(url_for('profile.profile'))

