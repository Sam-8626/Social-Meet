import os
import sys
import random
import json
from flask import Flask, render_template, request, session, redirect, url_for
from flask_mail import Mail, Message
from flask_socketio import SocketIO, emit, join_room
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "obi_secret_key_default")

# --- 1. CONFIGURATION ---
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Email Setup via Environment Variables
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')

# --- 2. FIREBASE & SOCKETIO INITIALIZATION ---
if not firebase_admin._apps:
    firebase_json_env = os.environ.get("FIREBASE_CREDENTIALS")
    if firebase_json_env:
        cred_dict = json.loads(firebase_json_env)
        cred = credentials.Certificate(cred_dict)
    else:
        cred = credentials.Certificate("firebase-key.json")
        
    firebase_admin.initialize_app(cred)

# Firebase Firestore Initialization
db = firestore.client()

# Diagnostic Connection Check
try:
    test_docs = list(db.collection('users').limit(1).stream())
    print("✅ Firebase Firestore Connected Successfully!", flush=True)
except Exception as e:
    print(f"❌ Firebase Connection Failed: {str(e)}", file=sys.stderr, flush=True)

mail = Mail(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# --- 3. SOCKET.IO EVENTS ---
@socketio.on('join')
def on_join(data):
    room = data['room']
    join_room(room)

@socketio.on('send_message')
def handle_message(data):
    room = data['room']
    msg_data = {
        'sender_id': data['sender_id'],
        'receiver_id': data['receiver_id'],
        'message': data['message'],
        'timestamp': firestore.SERVER_TIMESTAMP
    }
    # Firestore Real-time Chat Save
    db.collection('messages').add(msg_data)
    
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
    except Exception as e:
        return f"Email Error! {str(e)}"

@app.route('/verify_otp', methods=['POST'])
def verify_otp():
    user_otp = request.form.get('otp')
    temp = session.get('temp_user')
    if temp and user_otp == temp['otp']:
        user_ref = db.collection('users').document()
        user_data = {
            'username': temp['name'],
            'email': temp['email'],
            'mobile': temp['phone'],
            'password': temp['pwd']
        }
        user_ref.set(user_data)
        session['user_id'] = user_ref.id
        session.pop('temp_user', None)
        return redirect(url_for('dashboard'))
    return render_template('verify.html', error="Wrong OTP!")

@app.route('/login', methods=['POST'])
def login():
    login_id = request.form.get('login_id')
    pwd = request.form.get('password')
    
    users_ref = db.collection('users')
    query = users_ref.where('password', '==', pwd).stream()
    
    for doc in query:
        u = doc.to_dict()
        if u.get('email') == login_id or u.get('mobile') == login_id:
            session['user_id'] = doc.id
            return redirect(url_for('dashboard'))
            
    return render_template('index.html', message="Invalid Credentials!")

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session: 
        return redirect(url_for('home'))
    user_doc = db.collection('users').document(session['user_id']).get()
    user = user_doc.to_dict() if user_doc.exists else {}
    return render_template('dashboard.html', user=user)

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('home'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False)