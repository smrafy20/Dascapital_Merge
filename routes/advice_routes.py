from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from datetime import datetime, timedelta
import os
import re
from db import db
from models import User, Transaction, FinancialGoal

advice_bp = Blueprint('advice', __name__)


def require_login():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    return None


@advice_bp.route('/financial_advice', methods=['GET'])
def financial_advice():
    need = require_login()
    if need: return need

    # Render placeholder template; to be filled with dynamic JS later
    return render_template('financial_advice.html')


@advice_bp.route('/api/financial_summary', methods=['POST'])
def api_financial_summary():
    """Compute a 90-day financial summary for the current user.
    Returns: { total_income, total_expenses, savings_rate, balance, since }
    """
    if 'user_id' not in session:
        return jsonify(success=False, message='Not authenticated'), 401

    user = User.query.get(session['user_id'])
    if not user:
        return jsonify(success=False, message='User not found'), 404

    since = datetime.utcnow() - timedelta(days=90)

    # Infer income/expenses based on Transaction.type in this project schema ('add' vs 'send')
    q = Transaction.query.filter(
        Transaction.user_id == user.id,
        Transaction.timestamp >= since
    )

    total_income = 0.0
    total_expenses = 0.0
    for t in q.all():
        t_type = (t.type or '').lower()
        amt = float(t.amount or 0)
        if t_type in ('add', 'credit'):
            total_income += amt
        elif t_type in ('send', 'debit'):
            total_expenses += amt

    balance = float(user.balance or 0)
    savings = max(0.0, total_income - total_expenses)
    savings_rate = (savings / total_income) * 100.0 if total_income > 0 else 0.0

    # Fetch goals for the user
    goals = FinancialGoal.query.filter_by(user_id=user.id).order_by(FinancialGoal.created_at.desc()).all()
    goals_payload = [
        {
            'id': g.id,
            'goal_name': g.goal_name,
            'target_amount': float(g.target_amount or 0),
            'current_amount': float(g.current_amount or 0),
            'created_at': (g.created_at.isoformat() if g.created_at else None),
            'due_date': (g.due_date.isoformat() if g.due_date else None),
            'progress_pct': (float(g.current_amount or 0) / float(g.target_amount) * 100.0) if g.target_amount else 0.0
        }
        for g in goals
    ]

    summary = {
        'total_income': round(total_income, 2),
        'total_expenses': round(total_expenses, 2),
        'savings_rate': round(savings_rate, 2),
        'balance': round(balance, 2),
        'since': since.date().isoformat()
    }

    # Generate AI advice with safe fallback if not configured
    advice_text, advice_source = get_gemini_advice({
        'total_income': total_income,
        'total_expenses': total_expenses,
        'savings_rate': savings_rate,
        'current_balance': balance,
        'goals': goals_payload,
    })

    return jsonify(success=True, data=summary, goals=goals_payload, ai_advice=advice_text, ai_source=advice_source)


def get_gemini_advice(financial_summary: dict):
    """Call Gemini to generate 3 actionable tips with disclaimer.
    Falls back to a local template if GEMINI_API_KEY isn't set or library missing.
    Incorporates simple market data if available.
    """
    try:
        # Collect optional fresh market data for context
        market_data = fetch_market_data()

        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise RuntimeError('GEMINI_API_KEY not set')

        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model_name = os.getenv('GEMINI_MODEL', 'gemini-1.5-flash')
        model = genai.GenerativeModel(model_name)

        ti = financial_summary.get('total_income', 0.0)
        te = financial_summary.get('total_expenses', 0.0)
        sr = financial_summary.get('savings_rate', 0.0)
        bal = financial_summary.get('current_balance', 0.0)
        goals = financial_summary.get('goals') or []

        goals_lines = []
        for g in goals[:5]:  # cap for prompt length
            goals_lines.append(f"- {g.get('goal_name')}: target ৳{g.get('target_amount')}, current ৳{g.get('current_amount')} (due {g.get('due_date') or 'N/A'})")
        goals_section = "\n".join(goals_lines) if goals_lines else "- No goals set"

        market_lines = [f"- {k}: {v['price']} ({v['source']})" for k, v in (market_data or {}).items()]
        market_section = "\n".join(market_lines) if market_lines else "- No live market data available"

        prompt = f"""
You are an assistant embedded in a mobile banking app. Provide concise, practical, and personalized financial guidance.

User financial summary (last 90 days):
- Total income: ৳{ti:.2f}
- Total expenses: ৳{te:.2f}
- Savings rate: {sr:.2f}%
- Current balance: ৳{bal:.2f}

User goals:
{goals_section}

Recent market context (for any investing tip you provide):
{market_section}

Requirements:
1) Provide exactly three actionable, numbered tips tailored to the user's data. Keep each to 1-2 short sentences.
2) At least one tip must be investing-related and may reference the market context above (do not invent tickers beyond those listed).
3) Be realistic given the user's income/expenses/balance and goals.
4) End with this line verbatim: "Disclaimer: This is for informational purposes only and not professional financial advice."
"""

        # Try primary model
        try:
            resp = model.generate_content(prompt)
            used_model = model_name
        except Exception as model_err:
            # Attempt fallback to widely-available model
            fallback_model = 'gemini-1.5-flash'
            try:
                model = genai.GenerativeModel(fallback_model)
                resp = model.generate_content(prompt)
                used_model = fallback_model
                try:
                    print('Gemini primary model failed:', str(model_err))
                except Exception:
                    pass
            except Exception as second_err:
                # Re-raise original; outer except will craft local fallback
                raise RuntimeError(f'Both models failed: primary={model_name}, fallback={fallback_model}; cause={second_err}')

        text = (getattr(resp, 'text', None) or "").strip()
        if not text:
            # Some SDK versions return candidates
            candidates = getattr(resp, 'candidates', None) or []
            if candidates and getattr(candidates[0], 'content', None):
                parts = getattr(candidates[0].content, 'parts', None) or []
                text = "".join(getattr(p, 'text', '') for p in parts).strip()
        if not text:
            raise RuntimeError('Empty response from Gemini')
        # Ensure disclaimer present
        if 'informational purposes' not in text.lower():
            text += "\n\nDisclaimer: This is for informational purposes only and not professional financial advice."
        # Explicit source flag
        # Include which model we used for easier diagnostics
        try:
            print('Gemini advice generated via model:', used_model)
        except Exception:
            pass
        return text, f'gemini:{used_model}'
    except Exception as e:
        # Fallback simple, local advice template
        ti = financial_summary.get('total_income', 0.0)
        te = financial_summary.get('total_expenses', 0.0)
        sr = financial_summary.get('savings_rate', 0.0)
        bal = financial_summary.get('current_balance', 0.0)
        # Log a concise reason to the console to aid debugging
        try:
            print('Gemini fallback:', str(e))
        except Exception:
            pass
        generic = [
            f"1) Aim to keep expenses below income. Your current monthly savings rate is approx. {sr:.1f}%. Try automating a fixed transfer to savings right after income arrives.",
            f"2) Build a 3–6 month emergency fund. With a balance of ৳{bal:.0f}, consider dedicating part of new savings until you reach your target.",
            "3) Consider a diversified, low-cost index fund or a small crypto allocation only if your emergency fund is covered. Rebalance quarterly."
        ]
        return "\n".join(generic) + "\n\nDisclaimer: This is for informational purposes only and not professional financial advice.", 'fallback'


def fetch_market_data():
    """Try to fetch a small set of live market prices.
    Order of attempts:
      1) yfinance (no key) for ['AAPL','MSFT','BTC-USD','ETH-USD']
      2) Google Custom Search (if GOOGLE_API_KEY and GOOGLE_CSE_ID) parse snippet price
    Returns dict like {'AAPL': {'price': '192.34 USD', 'source': 'Yahoo Finance'}}
    """
    data = {}
    # Attempt yfinance
    try:
        import yfinance as yf
        tickers = ['AAPL', 'MSFT', 'BTC-USD', 'ETH-USD']
        t = yf.Tickers(" ".join(tickers))
        for sym in tickers:
            info = t.tickers[sym].fast_info  # fast path
            last = getattr(info, 'last_price', None) or info.get('lastPrice') if isinstance(info, dict) else None
            if not last:
                # fallback to history
                hist = t.tickers[sym].history(period='1d')
                if not hist.empty:
                    last = float(hist['Close'].iloc[-1])
            if last:
                unit = 'USD'
                data[sym] = {'price': f"{float(last):.2f} {unit}", 'source': 'Yahoo Finance'}
    except Exception:
        pass

    # If still empty, try Google Custom Search snippets
    if not data:
        api_key = os.getenv('GOOGLE_API_KEY')
        cse_id = os.getenv('GOOGLE_CSE_ID')
        if api_key and cse_id:
            try:
                from googleapiclient.discovery import build
                service = build("customsearch", "v1", developerKey=api_key)
                queries = {
                    'AAPL': 'AAPL stock price',
                    'MSFT': 'MSFT stock price',
                    'BTC-USD': 'BTC price',
                    'ETH-USD': 'ETH price'
                }
                price_re = re.compile(r"\b(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)\b")
                for sym, q in queries.items():
                    res = service.cse().list(q=q, cx=cse_id, num=1).execute()
                    items = res.get('items') or []
                    if not items:
                        continue
                    snippet = items[0].get('snippet') or ''
                    m = price_re.search(snippet)
                    if m:
                        data[sym] = {'price': f"{m.group(1)}", 'source': 'Google Search snippet'}
            except Exception:
                pass

    return data or None


@advice_bp.route('/api/goals/add', methods=['POST'])
def add_financial_goal():
    """Create a new financial goal for the logged-in user.
    Expects form fields: goal_name, target_amount, due_date (YYYY-MM-DD optional)
    Returns JSON with the created goal or an error.
    """
    if 'user_id' not in session:
        return jsonify(success=False, message='Not authenticated'), 401

    # Support both form-encoded and JSON bodies
    goal_name = (request.form.get('goal_name')
                 or (request.get_json(silent=True) or {}).get('goal_name')
                 or '').strip()
    target_amount_raw = (request.form.get('target_amount')
                         or (request.get_json(silent=True) or {}).get('target_amount')
                         or '').strip()
    due_date_raw = (request.form.get('due_date')
                    or (request.get_json(silent=True) or {}).get('due_date')
                    or '').strip()

    if not goal_name or not target_amount_raw:
        return jsonify(success=False, message='goal_name and target_amount are required'), 400

    try:
        target_amount = float(target_amount_raw)
        if target_amount <= 0:
            raise ValueError('Target must be > 0')
    except Exception:
        return jsonify(success=False, message='Invalid target_amount'), 400

    due_date = None
    if due_date_raw:
        try:
            from datetime import datetime as _dt
            due_date = _dt.strptime(due_date_raw, '%Y-%m-%d').date()
        except Exception:
            return jsonify(success=False, message='Invalid due_date format (YYYY-MM-DD)'), 400

    try:
        g = FinancialGoal(
            user_id=session['user_id'],
            goal_name=goal_name,
            target_amount=target_amount,
            current_amount=0.0,
            due_date=due_date
        )
        db.session.add(g)
        db.session.commit()
        payload = {
            'id': g.id,
            'goal_name': g.goal_name,
            'target_amount': float(g.target_amount or 0),
            'current_amount': float(g.current_amount or 0),
            'created_at': (g.created_at.isoformat() if g.created_at else None),
            'due_date': (g.due_date.isoformat() if g.due_date else None),
            'progress_pct': (float(g.current_amount or 0) / float(g.target_amount) * 100.0) if g.target_amount else 0.0
        }
        return jsonify(success=True, goal=payload)
    except Exception:
        db.session.rollback()
        return jsonify(success=False, message='Could not save goal'), 500
