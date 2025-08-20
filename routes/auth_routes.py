from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from models import User
from db import db
from sqlalchemy.exc import IntegrityError
from datetime import datetime

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('dashboard.dashboard'))
    return redirect(url_for('auth.login'))

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        phone = request.form['phone']
        pin = request.form['pin']

        user = User.query.filter_by(phone=phone, pin=pin).first()

        if user:
            session['user_id'] = user.id
            session['user_name'] = f"{user.first_name} {user.last_name}"
            flash(f"Welcome back, {session['user_name']}!")
            return redirect(url_for('dashboard.dashboard'))
        else:
            flash("Invalid credentials")
            return redirect(url_for('auth.login'))

    return render_template('login.html')

@auth_bp.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for('auth.login'))

@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        first_name = request.form['firstName']
        last_name = request.form['lastName']
        email = request.form['email']
        phone = request.form['phone']
        nid = request.form['nid']
        password = request.form['password']
        dob_str = request.form['dob']

        # Convert date string to date object
        try:
            dob = datetime.strptime(dob_str, '%Y-%m-%d').date()
        except ValueError:
            flash("Invalid date format.")
            return redirect(url_for('auth.signup'))

        # Check basic uniqueness up front for a nicer message
        existing_user = User.query.filter(
            (User.phone == phone) | (User.email == email) | (User.nid == nid)
        ).first()
        if existing_user:
            flash("User with this phone, email, or NID already exists.")
            return redirect(url_for('auth.signup'))

        new_user = User(
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            nid=nid,
            pin=password,
            dob=dob,
            balance=0,
            full_name=f"{first_name} {last_name}"
        )

        try:
            db.session.add(new_user)
            db.session.commit()
            flash("Account created successfully! Please login.")
            return redirect(url_for('auth.login'))
        except IntegrityError as e:
            db.session.rollback()
            # Handle race or any other unique constraint violation from DB layer
            flash("User with this phone, email, or NID already exists.")
            return redirect(url_for('auth.signup'))
        except Exception as e:
            db.session.rollback()
            flash(f"An error occurred while creating your account: {str(e)}")
            return redirect(url_for('auth.signup'))

    return render_template('signup.html')

# --- Forgot PIN (password) flow ---
@auth_bp.route('/forgot_pin/verify', methods=['POST'])
def forgot_pin_verify():
    data = request.get_json(silent=True) or {}
    phone = (data.get('phone') or '').strip()
    nid = (data.get('nid') or '').strip()
    if not phone or not nid:
        return jsonify(success=False, message='Phone and NID are required.'), 400

    user = User.query.filter_by(phone=phone, nid=nid).first()
    if not user:
        return jsonify(success=False, message='No user found with that Phone + NID.'), 404

    # mark session for reset
    session['reset_user_id'] = user.id
    return jsonify(success=True)

@auth_bp.route('/forgot_pin/reset', methods=['POST'])
def forgot_pin_reset():
    data = request.get_json(silent=True) or {}
    new_pin = (data.get('new_pin') or '').strip()
    confirm_pin = (data.get('confirm_pin') or '').strip()

    user_id = session.get('reset_user_id')
    if not user_id:
        return jsonify(success=False, message='Reset session expired. Verify again.'), 400
    if not new_pin or len(new_pin) < 4:
        return jsonify(success=False, message='PIN must be at least 4 characters.'), 400
    if new_pin != confirm_pin:
        return jsonify(success=False, message='PINs do not match.'), 400

    user = User.query.get(user_id)
    if not user:
        return jsonify(success=False, message='User not found.'), 404

    try:
        user.pin = new_pin
        db.session.commit()
        session.pop('reset_user_id', None)
        return jsonify(success=True)
    except Exception:
        db.session.rollback()
        return jsonify(success=False, message='Could not update PIN.'), 500
