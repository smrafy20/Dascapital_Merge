from flask import Blueprint, render_template, session, redirect, url_for, jsonify, request
from models import Notification
from db import db
from datetime import datetime
from math import ceil

notification_bp = Blueprint('notifications', __name__)


@notification_bp.route('/notifications', methods=['GET'])
def notifications_page():
    """Render the notifications UI (now loaded dynamically).

    NOTE: We no longer automatically mark all notifications as read upon visiting
    this page. Users can explicitly mark items as read, preserving unread counts
    until they review them. Existing dashboard dropdown behaviour (marking all
    read when opened) remains unchanged.
    """
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    # Initial server render passes only a minimal subset; client fetches pages.
    return render_template('notifications.html', notifications=[])  # legacy var kept for template compatibility


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


def _serialize_notification(n: Notification):
    """Internal serializer for list endpoints."""
    # Determine an icon keyword for front-end based on type
    type_map = {
        'credit': '💰',
        'debit': '💸',
        'info': 'ℹ️',
        'split': '🧾',
        'request': '📨'
    }
    t = (n.type or '').lower()
    icon = type_map.get(t, '🔔')

    # Relative time (coarse)
    now = datetime.utcnow()
    delta = now - (n.created_at or now)
    seconds = int(delta.total_seconds())
    if seconds < 60:
        rel = f"{seconds}s ago"
    elif seconds < 3600:
        rel = f"{seconds // 60}m ago"
    elif seconds < 86400:
        rel = f"{seconds // 3600}h ago"
    else:
        rel = f"{seconds // 86400}d ago"

    return {
        'id': n.id,
        'type': n.type,
        'title': n.title,
        'message': n.message,
        'created_at': n.created_at.strftime('%Y-%m-%d %H:%M'),
        'created_ago': rel,
        'read': n.read_at is not None,
        'icon': icon
    }


@notification_bp.route('/notifications/api/list', methods=['GET'])
def notifications_list():
    """Paginated notifications list with optional filtering.

    Query parameters:
        page: 1-based page number (default 1)
        per_page: items per page (default 10, max 50)
        type: filter by notification type (case-insensitive) or 'all'
        unread: if '1', only unread
    """
    if 'user_id' not in session:
        return jsonify(success=False, message='Not logged in'), 401

    user_id = session['user_id']
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 10))
    except ValueError:
        return jsonify(success=False, message='Invalid pagination parameters'), 400

    per_page = max(1, min(per_page, 50))
    page = max(1, page)

    q = Notification.query.filter_by(user_id=user_id)
    notif_type = request.args.get('type')
    if notif_type and notif_type.lower() != 'all':
        q = q.filter(Notification.type.ilike(notif_type))
    if request.args.get('unread') == '1':
        q = q.filter(Notification.read_at.is_(None))

    q = q.order_by(Notification.created_at.desc())
    total = q.count()
    total_pages = ceil(total / per_page) if total else 1
    # Adjust page if out of bounds
    if page > total_pages:
        page = total_pages
    items = q.offset((page - 1) * per_page).limit(per_page).all()

    unread_count = Notification.query.filter_by(user_id=user_id).filter(Notification.read_at.is_(None)).count()

    return jsonify(success=True,
                   page=page,
                   per_page=per_page,
                   total=total,
                   total_pages=total_pages,
                   unread_count=unread_count,
                   notifications=[_serialize_notification(n) for n in items])


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


@notification_bp.route('/notifications/api/mark_unread', methods=['POST'])
def notifications_mark_unread():
    if 'user_id' not in session:
        return jsonify(success=False, message='Not logged in'), 401

    user_id = session['user_id']
    data = request.get_json(silent=True) or {}
    ids = data.get('ids', [])
    if not ids:
        return jsonify(success=False, message='No ids provided'), 400

    # Set read_at to NULL for given ids belonging to user
    q = Notification.query.filter(Notification.user_id == user_id, Notification.id.in_(ids))
    updated = 0
    now = datetime.utcnow()  # kept (unused) for parity; could remove
    for n in q.all():
        if n.read_at is not None:
            n.read_at = None
            updated += 1
    if updated:
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

