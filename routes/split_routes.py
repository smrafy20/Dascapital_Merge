from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from datetime import datetime
from db import db
from models import User, Transaction, Notification

split_bp = Blueprint('split', __name__)

# --- Models ---
from models import SplitBill, SplitBillShare  # type: ignore


def require_login():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    return None


@split_bp.route('/split_bill', methods=['GET', 'POST'])
def split_bill_page():
    need = require_login()
    if need: return need

    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()
        note = (request.form.get('note') or '').strip()
        total_raw = (request.form.get('total_amount') or '').strip()
        split_mode = (request.form.get('split_mode') or 'equal').strip()
        destination_phone = (request.form.get('destination_phone') or '').strip()
        participants_raw = (request.form.get('participants') or '').strip()
        shares_raw = (request.form.get('shares') or '').strip()

        if not title or not total_raw or not destination_phone or not participants_raw:
            flash('Please fill in title, total amount, destination phone, and at least one participant.')
            return redirect(url_for('split.split_bill_page'))

        try:
            total = float(total_raw)
            if total <= 0:
                raise ValueError
        except Exception:
            flash('Total amount is invalid.')
            return redirect(url_for('split.split_bill_page'))

        creator = User.query.get(session['user_id'])
        destination = User.query.filter_by(phone=destination_phone).first()
        if not destination:
            flash('Destination phone not found.')
            return redirect(url_for('split.split_bill_page'))

        try:
            participant_ids = [int(pid) for pid in participants_raw.split(',') if pid]
        except Exception:
            flash('Invalid participants list.')
            return redirect(url_for('split.split_bill_page'))
        participant_ids = list(dict.fromkeys(pid for pid in participant_ids if pid != creator.id))
        if not participant_ids:
            flash('Please select at least one participant (other than yourself).')
            return redirect(url_for('split.split_bill_page'))

        # Verify participants exist
        participants = User.query.filter(User.id.in_(participant_ids)).all()
        if len(participants) != len(participant_ids):
            flash('One or more selected participants were not found.')
            return redirect(url_for('split.split_bill_page'))

        # Build shares
        shares = []  # list of (participant_id, amount)
        if split_mode == 'equal':
            share_amount = round(total / len(participant_ids), 2)
            running = 0.0
            for i, pid in enumerate(participant_ids):
                amt = share_amount if i < len(participant_ids) - 1 else round(total - running, 2)
                shares.append((pid, amt))
                running += share_amount
        else:
            if not shares_raw:
                flash('Please enter custom shares for each participant.')
                return redirect(url_for('split.split_bill_page'))
            try:
                tmp = {}
                for part in shares_raw.split(';'):
                    if not part: continue
                    pid_s, amt_s = part.split(':', 1)
                    pid = int(pid_s); amt = round(float(amt_s), 2)
                    if amt < 0: raise ValueError
                    tmp[pid] = tmp.get(pid, 0.0) + amt
                # Validate all participants included
                for pid in participant_ids:
                    if pid not in tmp:
                        flash('Please provide share for each participant.')
                        return redirect(url_for('split.split_bill_page'))
                total_sum = round(sum(tmp.values()), 2)
                if abs(total_sum - round(total, 2)) > 0.01:
                    flash('Sum of shares must equal the total amount.')
                    return redirect(url_for('split.split_bill_page'))
                for pid in participant_ids:
                    shares.append((pid, tmp[pid]))
            except Exception:
                flash('Invalid custom shares format.')
                return redirect(url_for('split.split_bill_page'))

        bill = SplitBill(
            creator_id=creator.id,
            destination_id=destination.id,
            title=title,
            note=note,
            total_amount=total,
            status='open',
            created_at=datetime.utcnow(),
        )
        try:
            db.session.add(bill)
            db.session.flush()
            for pid, amt in shares:
                db.session.add(SplitBillShare(split_bill_id=bill.id, participant_id=pid, amount=amt, status='pending'))
            for pid, amt in shares:
                u = User.query.get(pid)
                if not u: continue
                db.session.add(Notification(user_id=u.id, type='split', title='Split Bill', message=f'{creator.full_name} created a split bill "{title}". Your share: {amt:.2f}.'))
            db.session.commit()
            flash('Split bill created successfully!')
            return redirect(url_for('dashboard.dashboard'))
        except Exception:
            db.session.rollback()
            flash('Failed to create split bill. Please try again.')
            return redirect(url_for('split.split_bill_page'))

    return render_template('split_bill.html')


@split_bp.route('/split_shares', methods=['GET'])
def split_shares_page():
    need = require_login()
    if need: return need

    user_id = session['user_id']
    shares = (SplitBillShare.query
              .filter_by(participant_id=user_id)
              .order_by(SplitBillShare.id.desc())
              .all())
    # Build context maps
    bill_ids = {s.split_bill_id for s in shares}
    bills = {b.id: b for b in SplitBill.query.filter(SplitBill.id.in_(bill_ids)).all()} if bill_ids else {}
    user_ids = set()
    for b in bills.values():
        user_ids.add(b.creator_id)
        if b.destination_id:
            user_ids.add(b.destination_id)
    users = {u.id: u for u in User.query.filter(User.id.in_(user_ids)).all()} if user_ids else {}

    rows = []
    for s in shares:
        b = bills.get(s.split_bill_id)
        if not b: continue
        rows.append({
            'id': s.id,
            'amount': s.amount,
            'status': s.status,
            'title': b.title,
            'creator': users.get(b.creator_id).full_name if users.get(b.creator_id) else 'Unknown',
            'destination': users.get(b.destination_id).full_name if b.destination_id and users.get(b.destination_id) else users.get(b.creator_id).full_name if users.get(b.creator_id) else 'Unknown',
            'created_at': b.created_at.strftime('%Y-%m-%d %H:%M') if b.created_at else '',
            'paid_at': s.paid_at.strftime('%Y-%m-%d %H:%M') if s.paid_at else '',
        })

    return render_template('split_shares.html', shares=rows)


@split_bp.route('/split_share/api/process', methods=['POST'])
def split_share_process():
    if 'user_id' not in session:
        return jsonify(success=False, message='Not logged in'), 401

    data = request.get_json(silent=True) or {}
    share_id = data.get('share_id')
    action = data.get('action')  # 'pay' or 'reject'
    if action not in ('pay', 'reject'):
        return jsonify(success=False, message='Invalid action'), 400

    share = SplitBillShare.query.get(share_id)
    if not share or share.participant_id != session['user_id']:
        return jsonify(success=False, message='Share not found'), 404

    if share.status != 'pending':
        return jsonify(success=False, message='Share already processed'), 400

    bill = SplitBill.query.get(share.split_bill_id)
    if not bill:
        return jsonify(success=False, message='Bill not found'), 404

    payer = User.query.get(share.participant_id)
    destination = User.query.get(bill.destination_id) or User.query.get(bill.creator_id)

    try:
        if action == 'pay':
            if (payer.balance or 0) < share.amount:
                return jsonify(success=False, message='Insufficient balance'), 400
            payer.balance -= share.amount
            destination.balance = (destination.balance or 0) + share.amount
            trx_id_base = f'SB{bill.id}-{share.id}-{int(datetime.utcnow().timestamp())}'
            db.session.add(Transaction(user_id=payer.id, trx_id=trx_id_base+'D', type='send', amount=share.amount, method='split', source_dest=str(destination.phone)))
            db.session.add(Transaction(user_id=destination.id, trx_id=trx_id_base+'C', type='add', amount=share.amount, method='split', source_dest=str(payer.phone)))
            db.session.add(Notification(user_id=destination.id, type='credit', title='Split Bill Paid', message=f'{payer.full_name} paid {share.amount:.2f} for "{bill.title}"'))
            db.session.add(Notification(user_id=payer.id, type='debit', title='Split Share Paid', message=f'You paid {share.amount:.2f} to {destination.full_name} for "{bill.title}"'))
            share.status = 'paid'
            share.paid_at = datetime.utcnow()
        else:
            share.status = 'rejected'
            share.paid_at = None
            db.session.add(Notification(user_id=bill.creator_id, type='info', title='Split Share Rejected', message=f'{payer.full_name} rejected their share for "{bill.title}"'))

        db.session.flush()
        others = SplitBillShare.query.filter_by(split_bill_id=bill.id).all()
        if all(s.status != 'pending' for s in others):
            if all(s.status == 'paid' for s in others):
                bill.status = 'completed'
                bill.completed_at = datetime.utcnow()
            else:
                bill.status = 'open'
        db.session.commit()
        return jsonify(success=True)
    except Exception:
        db.session.rollback()
        return jsonify(success=False, message='Processing failed'), 500

