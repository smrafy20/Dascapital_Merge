from flask import Blueprint, render_template, session, redirect, url_for, jsonify, request
from models import Notification
from db import db
from datetime import datetime

notification_bp = Blueprint('notifications', __name__)


@notification_bp.route('/notifications', methods=['GET'])
def notifications_page():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    user_id = session['user_id']
    items = Notification.query.filter_by(user_id=user_id).order_by(Notification.created_at.desc()).all()

    # Mark all as read when visiting the notifications page
    unread = [n for n in items if n.read_at is None]
    if unread:
        now = datetime.utcnow()
        for n in unread:
            n.read_at = now
        db.session.commit()

    return render_template('notifications.html', notifications=items)


@notification_bp.route('/notifications/api/unread_count', methods=['GET'])
def notifications_unread_count():
    if 'user_id' not in session:
        return jsonify(success=False, message='Not logged in'), 401
    user_id = session['user_id']
    count = Notification.query.filter_by(user_id=user_id).filter(Notification.read_at.is_(None)).count()
    return jsonify(success=True, count=count)


@notification_bp.route('/notifications/api/latest', methods=['GET'])
def notifications_latest():
    if 'user_id' not in session:
        return jsonify(success=False, message='Not logged in'), 401

    user_id = session['user_id']
    items = (Notification.query
             .filter_by(user_id=user_id)
             .order_by(Notification.created_at.desc())
             .limit(3)
             .all())

    def serialize(n: Notification):
        # Provide a URL for actionable notifications (money requests)
        url = None
        if (n.type or '').lower() == 'request' or (n.title or '').lower().startswith('money request'):
            # Try to extract request id token from message: [REQ_ID:123]
            import re
            m = re.search(r"\[REQ_ID:(\d+)\]", n.message or '')
            if m:
                url = url_for('requests.request_detail', req_id=int(m.group(1)))
            else:
                url = url_for('requests.requests_overview')
        return {
            'id': n.id,
            'type': n.type,
            'title': n.title,
            'message': n.message,
            'created_at': n.created_at.strftime('%Y-%m-%d %H:%M'),
            'read': n.read_at is not None,
            'url': url,
        }

    return jsonify(success=True, notifications=[serialize(n) for n in items])


@notification_bp.route('/notifications/api/mark_read', methods=['POST'])
def notifications_mark_read():
    if 'user_id' not in session:
        return jsonify(success=False, message='Not logged in'), 401

    user_id = session['user_id']
    data = request.get_json(silent=True) or {}
    ids = data.get('ids', [])
    mark_all = data.get('mark_all', False)

    now = datetime.utcnow()
    if mark_all:
        q = Notification.query.filter_by(user_id=user_id).filter(Notification.read_at.is_(None))
        updated = q.update({Notification.read_at: now})
        db.session.commit()
        return jsonify(success=True, updated=updated)

    if not ids:
        return jsonify(success=False, message='No ids provided'), 400

    q = Notification.query.filter(Notification.user_id == user_id, Notification.id.in_(ids))
    updated = q.update({Notification.read_at: now}, synchronize_session=False)
    db.session.commit()
    return jsonify(success=True, updated=updated)


@notification_bp.route('/notifications/api/clear_all', methods=['POST'])
def notifications_clear_all():
    if 'user_id' not in session:
        return jsonify(success=False, message='Not logged in'), 401

    user_id = session['user_id']
    deleted = Notification.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    db.session.commit()
    return jsonify(success=True, deleted=deleted)

