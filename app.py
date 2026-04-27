import os
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, request, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'diocese-secure-key'
# Use environment variable for Render/Cloud, default to SQLite for local dev
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///diocese_final.db')
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- Database Models ---

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='basic')  # 'admin' or 'basic'
    status = db.Column(db.String(20), default='active') # 'active' or 'pending'

class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(150))
    uploaded_by = db.Column(db.String(150))
    date_uploaded = db.Column(db.DateTime, default=datetime.utcnow)

class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150))
    action = db.Column(db.String(255))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# --- Helpers ---

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def log_event(action):
    # Only log if user is authenticated, otherwise use 'System' or 'Guest'
    uname = current_user.username if current_user.is_authenticated else "System"
    new_log = ActivityLog(username=uname, action=action)
    db.session.add(new_log)
    db.session.commit()

# --- Auto-Initialize Database ---
with app.app_context():
    db.create_all()
    # Check for initial admin
    admin_user = User.query.filter_by(username='admin').first()
    if not admin_user:
        admin_user = User(
            username='admin', 
            email='admin@diocese.org', 
            password=generate_password_hash('admin123'), 
            role='admin', 
            status='active'
        )
        db.session.add(admin_user)
        db.session.commit()
        
# --- Routes ---

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password, request.form['password']):
            if user.status == 'pending':
                flash('Account pending approval. Please wait for an administrator.')
                return redirect(url_for('login'))
            
            login_user(user, remember=True) 
            log_event("Logged In")
            return redirect(url_for('dashboard'))
        
        flash('Invalid username or password.')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Check if user already exists
        if User.query.filter_by(username=request.form['username']).first():
            flash('Username already exists.')
            return redirect(url_for('register'))
            
        hashed_pw = generate_password_hash(request.form['password'])
        new_user = User(
            username=request.form['username'], 
            email=request.form['email'], 
            password=hashed_pw, 
            role='basic', 
            status='pending'
        )
        db.session.add(new_user)
        db.session.commit()
        flash('Registration successful! Request submitted for admin review.')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'admin':
        search = request.args.get('search')
        if search:
            users = User.query.filter(User.username.contains(search) | User.email.contains(search)).all()
        else:
            users = User.query.all()
        
        pending = User.query.filter_by(status='pending').all()
        logs = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).limit(10).all()
        # Use your specific dashboard_admin.html
        return render_template('dashboard_admin.html', pending=pending, users=users, logs=logs)
    
    return render_template('dashboard_basic.html')

# Generic route to handle Approve, Promote, and Delete actions
@app.route('/admin_action/<action>/<int:user_id>')
@login_required
def admin_action(action, user_id):
    if current_user.role != 'admin':
        flash("Unauthorized access.")
        return redirect(url_for('dashboard'))
    
    target_user = User.query.get_or_404(user_id)
    
    if action == 'approve':
        target_user.status = 'active'
        flash(f"User {target_user.username} approved.")
        log_event(f"Approved user: {target_user.username}")
        
    elif action == 'promote':
        target_user.role = 'admin'
        flash(f"User {target_user.username} is now an Admin.")
        log_event(f"Promoted user to Admin: {target_user.username}")
        
    elif action == 'delete':
        if target_user.username == 'admin':
            flash("Cannot delete the primary system administrator.")
        else:
            username = target_user.username
            db.session.delete(target_user)
            flash(f"User {username} removed from system.")
            log_event(f"Deleted user: {username}")
    
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/documents', methods=['GET', 'POST'])
@login_required
def documents():
    if request.method == 'POST' and 'file' in request.files:
        f = request.files['file']
        if f.filename != '':
            filename = secure_filename(f.filename)
            f.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            db.session.add(Document(filename=filename, uploaded_by=current_user.username))
            db.session.commit()
            log_event(f"Uploaded file: {filename}")
            flash(f"File {filename} uploaded successfully.")
    
    docs = Document.query.all()
    return render_template('documents.html', docs=docs)

@app.route('/logout')
@login_required
def logout():
    log_event("Logged Out")
    logout_user()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
