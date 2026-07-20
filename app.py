import os
import random
import warnings # Add this
from sqlalchemy.exc import LegacyAPIWarning # Add this
warnings.filterwarnings("ignore", category=LegacyAPIWarning) # Add this

from flask import Flask, render_template, request, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from werkzeug.utils import secure_filename
from sqlalchemy import or_
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)
app.secret_key = "obi_secret_key"

# --- 1. CONFIGURATION ---
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///C:\\sam\\Program Files\\VS code\\My First Pro\\instance\\users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USERNAME'] = 'tamilboy111223@gmail.com'
app.config['MAIL_PASSWORD'] = 'cdoh fbyk etnv iczs'

# --- 2. INITIALIZATION ---
db = SQLAlchemy(app)
mail = Mail(app)
# SocketIO initialize panniyaachu
socketio = SocketIO(app, cors_allowed_origins="*")

# User Model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    mobile = db.Column(db.String(15), unique=True, nullable=False)
    password = db.Column(db.String(80), nullable=False)
    instagram = db.Column(db.String(100))
    linkedin = db.Column(db.String(100))
    twitter = db.Column(db.String(100))
    profile_pic = db.Column(db.String(200))

# Message Table
class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())

with app.app_context():
    db.create_all()

# --- 3. SOCKET.IO EVENTS ---

@socketio.on('join')
def on_join(data):
    room = data['room']
    join_room(room)

@socketio.on('send_message')
def handle_message(data):
    room = data['room']
    # Database-la save panrom
    new_msg = ChatMessage(
        sender_id=data['sender_id'],
        receiver_id=data['receiver_id'],
        message=data['message']
    )
    db.session.add(new_msg)
    db.session.commit()
    
    # Message-ah andha specific room-ku broadcast panrom
    emit('receive_message', {
        'message': data['message'],
        'sender_id': data['sender_id']
    }, room=room)

# --- 4. ROUTES ---

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/signup', methods=['POST'])
def signup():
    name = request.form.get('username')
    email = request.form.get('email')
    phone = request.form.get('mobile')
    pwd = request.form.get('password')
    otp = str(random.randint(1000, 9999))
    session['temp_user'] = {'name': name, 'email': email, 'phone': phone, 'pwd': pwd, 'otp': otp}
    try:
        msg = Message('Obi Social Verification', sender=app.config['MAIL_USERNAME'], recipients=[email])
        msg.body = f"Hello {name}! Code: {otp}"
        mail.send(msg)
        return render_template('verify.html', email=email)
    except:
        return "Email Error! Check Internet."

@app.route('/verify_otp', methods=['POST'])
def verify_otp():
    user_otp = request.form.get('otp')
    temp = session.get('temp_user')
    if temp and user_otp == temp['otp']:
        new_user = User(username=temp['name'], email=temp['email'], mobile=temp['phone'], password=temp['pwd'])
        try:
            db.session.add(new_user)
            db.session.commit()
            session['user_id'] = new_user.id
            session.pop('temp_user', None)
            return redirect(url_for('dashboard'))
        except:
            return render_template('index.html', message="User already exists! ❌")
    return render_template('verify.html', error="Wrong OTP!")

@app.route('/login', methods=['POST'])
def login():
    login_id = request.form.get('login_id')
    pwd = request.form.get('password')
    user = User.query.filter((User.mobile == login_id) | (User.email == login_id)).filter_by(password=pwd).first()
    if user:
        session['user_id'] = user.id 
        return redirect(url_for('dashboard'))
    return render_template('index.html', message="Invalid Credentials!")

@app.route('/profile')
def profile():
    if 'user_id' not in session: return redirect(url_for('home'))
    user = User.query.get(session['user_id'])
    return render_template('profile.html', user=user)

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user_id' not in session: return redirect(url_for('home'))
    user = User.query.get(session['user_id'])
    search_result = None

    all_chats = ChatMessage.query.filter(
        or_(ChatMessage.sender_id == user.id, ChatMessage.receiver_id == user.id)
    ).order_by(ChatMessage.timestamp.desc()).all()
    
    recent_user_ids = []
    for chat in all_chats:
        other_id = chat.receiver_id if chat.sender_id == user.id else chat.sender_id
        if other_id not in recent_user_ids and other_id != user.id:
            recent_user_ids.append(other_id)
            
    recent_users = [User.query.get(uid) for uid in recent_user_ids]

    if request.method == 'POST':
        search_mobile = request.form.get('search_mobile')
        search_result = User.query.filter_by(mobile=search_mobile).first()
        
    return render_template('dashboard.html', user=user, search_result=search_result, recent_users=recent_users)

@app.route('/chat/<int:receiver_id>')
def chat(receiver_id):
    if 'user_id' not in session: return redirect(url_for('home'))
    sender_id = session['user_id']
    receiver = User.query.get(receiver_id)
    chats = ChatMessage.query.filter(
        ((ChatMessage.sender_id == sender_id) & (ChatMessage.receiver_id == receiver_id)) |
        ((ChatMessage.sender_id == receiver_id) & (ChatMessage.receiver_id == sender_id))
    ).order_by(ChatMessage.timestamp.asc()).all()
    return render_template('chat.html', receiver=receiver, chats=chats)

@app.route('/update_social', methods=['POST'])
def update_social():
    if 'user_id' not in session: return redirect(url_for('home'))
    user = User.query.get(session['user_id'])
    file = request.files.get('profile_pic')
    if file and file.filename != '':
        filename = secure_filename(f"user_{user.id}_{file.filename}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        user.profile_pic = filename 
    user.instagram = request.form.get('instagram')
    user.linkedin = request.form.get('linkedin')
    user.twitter = request.form.get('twitter') 
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/search_contact', methods=['POST'])
def search_contact():
    return redirect(url_for('dashboard'), code=307) 

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('home'))

if __name__ == '__main__':
    socketio.run(app, debug=True)