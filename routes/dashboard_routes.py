from flask import Blueprint, render_template, session, redirect, url_for
from models import User

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    user = User.query.filter_by(id=session['user_id']).first()
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))

    balance = user.balance or 0
    return render_template('dashboard.html', name=session.get('user_name'), balance=balance)
