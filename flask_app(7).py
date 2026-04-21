import random
import requests
from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'ultra_secret_casino_777_key'

# --- НАСТРОЙКА БАЗЫ ДАННЫХ ---
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///casino.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- НАСТРОЙКИ TELEGRAM БОТА ---
# Вставь свой токен и логин бота
TELEGRAM_BOT_TOKEN = 'api'
BOT_USERNAME = 'bot_username'

# --- МОДЕЛИ БАЗЫ ДАННЫХ ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    balance = db.Column(db.Integer, default=0)
    history = db.relationship('GameHistory', backref='player', lazy=True, order_by="desc(GameHistory.id)")

class GameHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    choice = db.Column(db.String(20), nullable=False)
    bet = db.Column(db.Integer, nullable=False)
    result = db.Column(db.String(50), nullable=False)
    profit = db.Column(db.Integer, nullable=False)

with app.app_context():
    db.create_all()

# --- КОНСТАНТЫ И ФУНКЦИИ ---
RED = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
BLACK = {2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35}

def get_color(number: int) -> str:
    if number in RED: return "RED"
    if number in BLACK: return "BLACK"
    return "GREEN"

def send_telegram_code(chat_id, code):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    text = f"🎰 <b>ELBERT_AHMET CASINO</b>\n\nТвой код подтверждения: <code>{code}</code>"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        response = requests.post(url, json=payload, timeout=5)
        return response.status_code == 200, response.text
    except Exception as e:
        return False, str(e)

# --- МАРШРУТЫ ---
@app.route('/', methods=['GET', 'POST'])
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('login'))

    if request.method == 'POST':
        action = request.form.get('action')

        # Обработка пополнения баланса
        if action == 'add_funds':
            try:
                amount = int(request.form.get('fund_amount', 0))
                if amount >= 10:
                    user.balance += amount
                    db.session.commit()
                    return jsonify({"status": "ok", "new_balance": user.balance})
                return jsonify({"status": "error", "msg": "Минимум 10 ₽"})
            except ValueError:
                return jsonify({"status": "error", "msg": "Некорректная сумма!"})

        # Обработка игры
        elif action == 'play':
            try:
                bet_amount = int(request.form.get('bet_amount', 0))
            except ValueError:
                return jsonify({"status": "error", "msg": "Некорректная сумма ставки!"})

            bet_choice = request.form.get('bet_choice')

            if not bet_choice:
                return jsonify({"status": "error", "msg": "Ошибка: Ставка не выбрана!"})

            if 0 < bet_amount <= user.balance:
                # 1. Сразу списываем ставку
                user.balance -= bet_amount

                res_n = random.randint(0, 36)
                res_c = get_color(res_n)
                win = 0

                # 2. Логика расчета общей выплаты
                if bet_choice == res_c:
                    win = bet_amount * 2
                elif bet_choice == 'EVEN' and res_n != 0 and res_n % 2 == 0:
                    win = bet_amount * 2
                elif bet_choice == 'ODD' and res_n % 2 != 0:
                    win = bet_amount * 2
                elif bet_choice.isdigit() and int(bet_choice) == res_n:
                    win = bet_amount * 36

                # 3. Начисляем выигрыш на баланс
                user.balance += win

                # ИСПРАВЛЕНИЕ: Вычисляем чистую прибыль (pure profit)
                pure_profit = win - bet_amount

                # 4. Сохраняем в историю ТОЛЬКО если есть чистая прибыль
                if pure_profit > 0:
                    new_h = GameHistory(user_id=user.id, choice=bet_choice, bet=bet_amount, result=f"{res_n} ({res_c})", profit=pure_profit)
                    db.session.add(new_h)

                # Фиксируем изменения баланса в БД
                db.session.commit()

                recent = GameHistory.query.filter(GameHistory.user_id == user.id, GameHistory.profit > 0).order_by(GameHistory.id.desc()).limit(15).all()
                return jsonify({
                    "status": "ok",
                    "result_num": res_n,
                    "win": win > 0,
                    "new_balance": user.balance,
                    "history_html": render_template('history_snippet.html', games=recent)
                })
            else:
                return jsonify({"status": "error", "msg": "Недостаточно средств или неверная ставка!"})

        # Обработка сброса
        elif action == 'reset':
            user.balance = 0
            GameHistory.query.filter_by(user_id=user.id).delete()
            db.session.commit()
            return jsonify({"status": "ok"})

    recent = GameHistory.query.filter(GameHistory.user_id == user.id, GameHistory.profit > 0).order_by(GameHistory.id.desc()).limit(15).all()
    return render_template('index.html', balance=user.balance, games=recent, username=user.username)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'register':
            u, e, p = request.form.get('username'), request.form.get('email'), request.form.get('password')

            if User.query.filter((User.username == u) | (User.email == e)).first():
                return "Ошибка: Ник или этот ID уже зарегистрированы!"

            code = str(random.randint(1000, 9999))
            ok, err = send_telegram_code(e, code)

            if ok:
                session['temp_reg'] = {
                    'username': u, 'email': e,
                    'password_hash': generate_password_hash(p), 'code': code
                }
                return redirect(url_for('verify'))
            else:
                return f"<b>Ошибка:</b> Не удалось отправить код.<br>1. Проверьте, что ID {e} верный.<br>2. Запустите бота!<br><small>Тех. инфо: {err}</small>"

        elif action == 'login':
            user = User.query.filter_by(username=request.form.get('username')).first()
            if user and check_password_hash(user.password_hash, request.form.get('password')):
                session['user_id'] = user.id
                return redirect(url_for('index'))
            return "Неверный логин или пароль!"

    return render_template('login.html', bot_username=BOT_USERNAME)

@app.route('/verify', methods=['GET', 'POST'])
def verify():
    temp = session.get('temp_reg')
    if not temp: return redirect(url_for('login'))

    if request.method == 'POST':
        if request.form.get('code') == temp['code']:
            new_u = User(username=temp['username'], email=temp['email'], password_hash=temp['password_hash'], balance=0)
            db.session.add(new_u)
            db.session.commit()
            session['user_id'] = new_u.id
            session.pop('temp_reg', None)
            return redirect(url_for('index'))
        else:
            return "Неверный код!"

    return render_template('verify.html', email=temp['email'])

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)