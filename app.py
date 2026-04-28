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

@@ -48,16 +49,18 @@
    return User.query.get(int(user_id))

def log_event(action):
    new_log = ActivityLog(username=current_user.username if current_user.is_authenticated else "Guest", action=action)
    # Only log if user is authenticated, otherwise use 'System' or 'Guest'
    uname = current_user.username if current_user.is_authenticated else "System"
    new_log = ActivityLog(username=uname, action=action)
    db.session.add(new_log)
    db.session.commit()

# --- Auto-Initialize Cloud Database ---
# --- Auto-Initialize Database ---
with app.app_context():
    db.create_all()
    # Create the initial admin if it doesn't exist
    admin_exists = User.query.filter_by(username='admin').first()
    if not admin_exists:
    # Check for initial admin
    admin_user = User.query.filter_by(username='admin').first()
    if not admin_user:
        admin_user = User(
            username='admin', 
            email='admin@diocese.org', 
@@ -80,126 +83,103 @@
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password, request.form['password']):
            if user.status == 'pending':
                flash('Account pending approval.')
                flash('Account pending approval. Please wait for an administrator.')
                return redirect(url_for('login'))

            # Adding remember=True keeps the user logged in across sessions
            login_user(user, remember=True) 
            
            log_event("Logged In")
            return redirect(url_for('dashboard'))
        flash('Invalid credentials.')
        
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
        new_user = User(username=request.form['username'], email=request.form['email'], 
                        password=hashed_pw, role='basic', status='pending')
        new_user = User(
            username=request.form['username'], 
            email=request.form['email'], 
            password=hashed_pw, 
            role='basic', 
            status='pending'
        )
        db.session.add(new_user)
        db.session.commit()
        flash('Request submitted for admin review.')
        flash('Registration successful! Request submitted for admin review.')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/create_admin', methods=['POST'])
@login_required
def create_admin():
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    
    hashed_pw = generate_password_hash(request.form['password'])
    new_admin = User(
        username=request.form['username'],
        email=request.form['email'],
        password=hashed_pw,
        role='admin', # Directly assigning admin role
        status='active'
    )
    db.session.add(new_admin)
    db.session.commit()
    flash("New Admin account created successfully.")
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'admin':
        # Search functionality (PCDC-23)
        search = request.args.get('search')
        if search:
            users = User.query.filter(User.username.contains(search) | User.id.contains(search)).all()
            users = User.query.filter(User.username.contains(search) | User.email.contains(search)).all()
        else:
            users = User.query.all()

        pending = User.query.filter_by(status='pending').all()
        logs = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).limit(10).all()
        # Use your specific dashboard_admin.html
        return render_template('dashboard_admin.html', pending=pending, users=users, logs=logs)
    
    return render_template('dashboard_basic.html')

@app.route('/profile', methods=['GET', 'POST'])
# Generic route to handle Approve, Promote, and Delete actions
@app.route('/admin_action/<action>/<int:user_id>')
@login_required
def profile():
    if request.method == 'POST':
        current_user.email = request.form['email']
        if request.form['password']:
            current_user.password = generate_password_hash(request.form['password'])
        db.session.commit()
        log_event("Updated Profile")
        flash("Profile updated successfully.")
    return render_template('profile.html')
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
        filename = secure_filename(f.filename)
        f.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        db.session.add(Document(filename=filename, uploaded_by=current_user.username))
        db.session.commit()
        log_event(f"Uploaded {filename}")
        if f.filename != '':
            filename = secure_filename(f.filename)
            f.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            db.session.add(Document(filename=filename, uploaded_by=current_user.username))
            db.session.commit()
            log_event(f"Uploaded file: {filename}")
            flash(f"File {filename} uploaded successfully.")

    docs = Document.query.all()
    return render_template('documents.html', docs=docs)

@app.route('/delete_doc/<int:id>')
@login_required
def delete_doc(id):
    doc = Document.query.get(id)
    if doc and current_user.role == 'admin':
        db.session.delete(doc)
        db.session.commit()
        log_event(f"Deleted Document ID {id}")
    return redirect(url_for('documents'))

@app.route('/admin_action/<action>/<int:user_id>')
@login_required
def admin_action(action, user_id):
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    
    target_user = User.query.get(user_id)
    if target_user:
        if action == 'approve':
            target_user.status = 'active'
            flash(f"User {target_user.username} approved.")
        elif action == 'promote':
            target_user.role = 'admin'
            flash(f"User {target_user.username} is now an Admin.")
        elif action == 'delete':
            if target_user.username == 'admin':
                flash("Cannot delete the primary admin.")
            else:
                db.session.delete(target_user)
                flash(f"User {target_user.username} removed from system.")
        
        db.session.commit()
        log_event(f"Admin performed {action} on user {target_user.username}")
        
    return redirect(url_for('dashboard'))

@app.route('/logout')
@login_required
def logout():
@@ -208,11 +188,4 @@
    return redirect(url_for('login'))

if __name__ == '__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']): os.makedirs(app.config['UPLOAD_FOLDER'])
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            db.session.add(User(username='admin', email='admin@diocese.org', 
                               password=generate_password_hash('admin123'), role='admin'))
            db.session.commit()
    app.run(debug=True)
    app.run(debug=True)