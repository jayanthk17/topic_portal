import os, sqlite3, secrets, time
from cryptography.fernet import Fernet, InvalidToken
from datetime import datetime, timezone
from functools import wraps
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash


BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get('DATABASE_PATH', os.path.join(BASE, 'topics.db'))
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')


STUDENT_LOGIN_SECONDS = 5 * 60
ADMIN_LOGIN_SECONDS = 15 * 60


@app.before_request
def enforce_fixed_login_expiry():
    expiry = session.get('login_expires_at')

    if expiry is None:
        if session.get('student') or session.get('admin'):
            session.clear()
        return

    if time.time() >= expiry:
        was_admin = bool(session.get('admin'))
        session.clear()

        if request.path.startswith('/api/'):
            return jsonify(
                error='Your login time has expired. Please log in again.',
                session_expired=True
            ), 401

        return redirect(
            '/admin' if was_admin else '/student/login'
        )


# Persist the encryption key separately from the database. Keep both backed up
# securely; losing this key makes saved credentials unrecoverable.
def credential_cipher():
    configured = os.environ.get('CREDENTIAL_ENCRYPTION_KEY')
    if configured:
        return Fernet(configured.encode('ascii'))
    key_path = os.path.join(BASE, '.student_credentials.key')
    try:
        with open(key_path, 'rb') as f:
            key = f.read().strip()
    except FileNotFoundError:
        key = Fernet.generate_key()
        try:
            fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            with open(key_path, 'rb') as f:
                key = f.read().strip()
        else:
            with os.fdopen(fd, 'wb') as f:
                f.write(key + b'\n')
    return Fernet(key)


def encrypt_credential(password):
    return credential_cipher().encrypt(password.encode('utf-8')).decode('ascii')


def connect():
    c = sqlite3.connect(DB, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA busy_timeout=15000')
    return c

def init_db():
    with connect() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS admins(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS students(id INTEGER PRIMARY KEY, name TEXT NOT NULL, usn TEXT NOT NULL UNIQUE COLLATE NOCASE, password_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS topics(id INTEGER PRIMARY KEY, title TEXT NOT NULL UNIQUE, max_members INTEGER NOT NULL CHECK(max_members BETWEEN 1 AND 30), active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS registrations(id INTEGER PRIMARY KEY, topic_id INTEGER NOT NULL UNIQUE REFERENCES topics(id), created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS members(id INTEGER PRIMARY KEY, registration_id INTEGER NOT NULL REFERENCES registrations(id) ON DELETE CASCADE, name TEXT NOT NULL, usn TEXT NOT NULL UNIQUE COLLATE NOCASE);''')
        # Upgrade existing databases without deleting topics or student registrations.
        student_columns = {row['name'] for row in c.execute('PRAGMA table_info(students)')}
        if 'credential_ciphertext' not in student_columns:
            c.execute('ALTER TABLE students ADD COLUMN credential_ciphertext TEXT')
        columns = {row['name'] for row in c.execute('PRAGMA table_info(registrations)')}
        if 'group_name' in columns:
            c.execute('ALTER TABLE registrations DROP COLUMN group_name')
        if not c.execute('SELECT 1 FROM admins LIMIT 1').fetchone():
            username = os.environ.get('ADMIN_USERNAME', 'admin')
            password = os.environ.get('ADMIN_PASSWORD')
            if not password:
                raise RuntimeError('Set ADMIN_PASSWORD environment variable before starting the application.')
            c.execute('INSERT INTO admins(username,password_hash) VALUES (?,?)',(username,generate_password_hash(password)))

def admin_only(fn):
    @wraps(fn)
    def inner(*a, **kw):
        if not session.get('admin'): return jsonify(error='Admin login required'),401
        return fn(*a, **kw)
    return inner

@app.get('/')
def home(): return render_template('student.html')
@app.get('/student/login')
def student_login_page(): return render_template('student_login.html')
@app.get('/admin')
def admin(): return render_template('admin.html')
@app.get('/registered-groups')
def registered_groups_page():
    return render_template('registered_groups.html')

@app.get('/api/registered-groups')
def public_registered_groups():
    # Public listing deliberately omits USNs, passwords and student account IDs.
    with connect() as c:
        rows = c.execute("""SELECT r.id, r.created_at, t.title
                            FROM registrations r JOIN topics t ON t.id = r.topic_id
                            ORDER BY r.created_at DESC, r.id DESC""").fetchall()
        return jsonify([{
            'topic': r['title'],
            'created_at': r['created_at'],
            'members': [m['name'] for m in c.execute(
                'SELECT name FROM members WHERE registration_id=? ORDER BY id',
                (r['id'],)).fetchall()]
        } for r in rows])

@app.get('/api/topics')
def topics():
    with connect() as c:
        rows=c.execute('''SELECT t.id,t.title,t.max_members,t.active, r.id IS NOT NULL AS booked,
        (SELECT COUNT(*) FROM members m WHERE m.registration_id=r.id) AS member_count
        FROM topics t LEFT JOIN registrations r ON r.topic_id=t.id ORDER BY t.title''').fetchall()
        return jsonify([dict(r) for r in rows if r['active'] or session.get('admin')])

@app.post('/api/student/login')
def student_login():
    d=request.get_json(silent=True) or {}
    with connect() as c:
        row=c.execute('SELECT * FROM students WHERE usn=?',(str(d.get('usn','')).strip().upper(),)).fetchone()
    if not row or not check_password_hash(row['password_hash'],str(d.get('password',''))):
        return jsonify(error='Invalid USN or password.'),401
    session.clear();session['student']=row['id'];session['student_csrf']=secrets.token_urlsafe(32);session['student_hash']=row['password_hash']
    session['login_expires_at'] = time.time() + STUDENT_LOGIN_SECONDS
    return jsonify(
    ok=True,
    csrf=session['student_csrf'],
    expires_at=session['login_expires_at']
)

@app.get('/api/student/session')
def student_session():
    if not session.get('student'): return jsonify(logged_in=False)
    with connect() as c:
        row=c.execute('SELECT name,usn,password_hash FROM students WHERE id=?',(session['student'],)).fetchone()
    if not row or row['password_hash']!=session.get('student_hash'): session.clear();return jsonify(logged_in=False)
    return jsonify(
    logged_in=True,
    name=row['name'],
    usn=row['usn'],
    csrf=session.get('student_csrf'),
    expires_at=session['login_expires_at']
)

@app.post('/api/student/logout')
def student_logout():
    if request.headers.get('X-CSRF-Token')!=session.get('student_csrf') or not session.get('student'):
        return jsonify(error='Invalid security token.'),403
    session.clear()
    return jsonify(ok=True)

@app.post('/api/register')
def register():
    if not session.get('student'): return jsonify(error='Student login required.'),401
    if request.headers.get('X-CSRF-Token')!=session.get('student_csrf'): return jsonify(error='Invalid security token.'),403
    with connect() as c:
        student=c.execute('SELECT name,usn,password_hash FROM students WHERE id=?',(session['student'],)).fetchone()
    if not student or student['password_hash']!=session.get('student_hash'): session.clear();return jsonify(error='Please sign in again.'),401
    data=request.get_json(silent=True) or {}
    try: topic_id=int(data.get('topic_id'))
    except (ValueError,TypeError): return jsonify(error='Choose a valid topic.'),400
    members=data.get('members',[])
    if not isinstance(members,list) or not members or len(members)>30: return jsonify(error='Enter valid group members.'),400
    cleaned=[]
    for m in members:
        if not isinstance(m,dict): return jsonify(error='Invalid member details.'),400
        name=str(m.get('name','')).strip(); usn=str(m.get('usn','')).strip().upper()
        if not name or not usn or len(name)>100 or len(usn)>30: return jsonify(error='Every member needs a valid name and USN.'),400
        cleaned.append((name,usn))
    if (student['name'],student['usn']) not in cleaned: return jsonify(error='Your registered name and USN must be included in the group.'),400
    if len({usn for _,usn in cleaned})!=len(cleaned): return jsonify(error='Duplicate USNs in this group.'),400
    c=connect()
    try:
        c.execute('BEGIN IMMEDIATE')
        topic=c.execute('SELECT * FROM topics WHERE id=? AND active=1',(topic_id,)).fetchone()
        if not topic: return jsonify(error='Topic unavailable.'),409
        if len(cleaned)>topic['max_members']: return jsonify(error=f'Maximum {topic["max_members"]} students allowed for this topic.'),400
        if c.execute('SELECT 1 FROM registrations WHERE topic_id=?',(topic_id,)).fetchone(): return jsonify(error='This topic has already been booked.'),409
        existing=c.execute('SELECT usn FROM members WHERE usn IN ('+','.join('?'*len(cleaned))+')',[u for _,u in cleaned]).fetchall()
        if existing: return jsonify(error='Already registered USN(s): '+', '.join(r['usn'] for r in existing)),409
        cur=c.execute('INSERT INTO registrations(topic_id,created_at) VALUES (?,?)',(topic_id,datetime.now(timezone.utc).isoformat()))
        c.executemany('INSERT INTO members(registration_id,name,usn) VALUES (?,?,?)',[(cur.lastrowid,n,u) for n,u in cleaned])
        c.commit()
        return jsonify(message='Group registered successfully!',registration_id=cur.lastrowid),201
    except sqlite3.IntegrityError:
        c.rollback(); return jsonify(error='Topic or USN already registered. Refresh and try again.'),409
    finally: c.close()

@app.post('/api/admin/login')
def login():
    d=request.get_json(silent=True) or {}
    with connect() as c: row=c.execute('SELECT * FROM admins WHERE username=?',(str(d.get('username','')),)).fetchone()
    if not row or not check_password_hash(row['password_hash'],str(d.get('password',''))): return jsonify(error='Invalid credentials.'),401
    session.clear();session['admin']=row['id'];session['csrf']=secrets.token_urlsafe(32)
    session['login_expires_at'] = time.time() + ADMIN_LOGIN_SECONDS
    return jsonify(
    ok=True,
    csrf=session['csrf'],
    expires_at=session['login_expires_at']
)

@app.get('/api/admin/session')
def status():
    return jsonify(
        logged_in=bool(session.get('admin')),
        csrf=session.get('csrf'),
        expires_at=session.get('login_expires_at')
    )

@app.post('/api/admin/logout')
@admin_only
def logout(): session.clear();return jsonify(ok=True)
@app.before_request
def csrf_check():
    if request.path.startswith('/api/admin/') and request.method in ('POST','PUT','DELETE') and request.endpoint not in ('login',):
        if session.get('admin') and request.headers.get('X-CSRF-Token')!=session.get('csrf'):
            return jsonify(error='Invalid security token.'),403
@app.get('/api/admin/students')
@admin_only
def admin_students():
    with connect() as c:
        rows=c.execute('SELECT id,name,usn,credential_ciphertext IS NOT NULL AS password_available FROM students ORDER BY usn').fetchall()
    return jsonify([dict(r) for r in rows])

@app.get('/api/admin/students/<int:student_id>/credential')
@admin_only
def admin_view_student_credential(student_id):
    # Never include decrypted credentials in the ordinary student listing.
    with connect() as c:
        row=c.execute('SELECT credential_ciphertext FROM students WHERE id=?',(student_id,)).fetchone()
    if not row:
        return jsonify(error='Student not found.'),404
    if not row['credential_ciphertext']:
        return jsonify(error='Existing password cannot be recovered. Reset it once to enable viewing.'),404
    try:
        password=credential_cipher().decrypt(row['credential_ciphertext'].encode('ascii')).decode('utf-8')
    except (InvalidToken, ValueError):
        return jsonify(error='Credential encryption key is missing or incorrect.'),500
    response=jsonify(password=password)
    response.headers['Cache-Control']='no-store'
    return response

@app.post('/api/admin/students')
@admin_only
def admin_create_student():
    d=request.get_json(silent=True) or {}
    name=str(d.get('name','')).strip()
    usn=str(d.get('usn','')).strip().upper()
    password=str(d.get('password',''))
    if not name or not usn or len(name)>100 or len(usn)>30 or not 8<=len(password)<=128:
        return jsonify(error='Enter name, USN and a password of 8–128 characters.'),400
    try:
        with connect() as c:
            c.execute('INSERT INTO students(name,usn,password_hash,credential_ciphertext) VALUES (?,?,?,?)',
                      (name,usn,generate_password_hash(password),encrypt_credential(password)))
    except sqlite3.IntegrityError:
        return jsonify(error='This USN already has an account.'),409
    return jsonify(ok=True),201

@app.put('/api/admin/students/<int:student_id>/password')
@admin_only
def admin_reset_student_password(student_id):
    d=request.get_json(silent=True) or {}
    password=str(d.get('password',''))
    if not 8<=len(password)<=128:
        return jsonify(error='Password must be 8–128 characters.'),400
    with connect() as c:
        cur=c.execute('UPDATE students SET password_hash=?, credential_ciphertext=? WHERE id=?',
                      (generate_password_hash(password),encrypt_credential(password),student_id))
        if not cur.rowcount:
            return jsonify(error='Student not found.'),404
    return jsonify(ok=True)

@app.post('/api/admin/topics')
@admin_only
def create_topic():
    d=request.get_json(silent=True) or {};title=str(d.get('title','')).strip()
    try: size=int(d.get('max_members'))
    except (ValueError,TypeError): return jsonify(error='Invalid group size.'),400
    if not title or len(title)>200 or not 1<=size<=30: return jsonify(error='Enter a topic and group size between 1 and 30.'),400
    try:
        with connect() as c: c.execute('INSERT INTO topics(title,max_members) VALUES (?,?)',(title,size))
    except sqlite3.IntegrityError: return jsonify(error='Topic already exists.'),409
    return jsonify(ok=True),201
@app.put('/api/admin/topics/<int:tid>')
@admin_only
def edit_topic(tid):
    d=request.get_json(silent=True) or {};title=str(d.get('title','')).strip()
    try: size=int(d.get('max_members'))
    except (ValueError,TypeError): return jsonify(error='Invalid group size.'),400
    if not title or len(title)>200 or not 1<=size<=30: return jsonify(error='Invalid topic or group size.'),400
    active=1 if d.get('active',True) else 0
    try:
        with connect() as c:
            existing=c.execute('SELECT COUNT(*) AS n FROM members m JOIN registrations r ON r.id=m.registration_id WHERE r.topic_id=?',(tid,)).fetchone()['n']
            if size<existing: return jsonify(error=f'This topic already has {existing} members.'),409
            cur=c.execute('UPDATE topics SET title=?,max_members=?,active=? WHERE id=?',(title,size,active,tid))
            if not cur.rowcount: return jsonify(error='Topic not found.'),404
    except sqlite3.IntegrityError: return jsonify(error='Topic name already exists.'),409
    return jsonify(ok=True)



def verify_admin_password(password):
    if not isinstance(password, str) or not password:
        return False

    with connect() as c:
        row = c.execute(
            'SELECT password_hash FROM admins WHERE id=?',
            (session.get('admin'),)
        ).fetchone()

    return bool(
        row and check_password_hash(
            row['password_hash'], password
        )
    )


@app.delete('/api/admin/topics/<int:tid>')
@admin_only
def delete_topic(tid):
    data = request.get_json(silent=True) or {}

    if not verify_admin_password(data.get('admin_password')):
        return jsonify(
            error='Correct admin password required.'
        ), 403

    with connect() as c:
        c.execute('BEGIN IMMEDIATE')

        topic = c.execute(
            'SELECT id FROM topics WHERE id=?',
            (tid,)
        ).fetchone()

        if not topic:
            return jsonify(error='Topic not found.'), 404

        c.execute(
            'DELETE FROM members WHERE registration_id IN '
            '(SELECT id FROM registrations WHERE topic_id=?)',
            (tid,)
        )

        c.execute(
            'DELETE FROM registrations WHERE topic_id=?',
            (tid,)
        )

        c.execute(
            'DELETE FROM topics WHERE id=?',
            (tid,)
        )

    return jsonify(ok=True)


@app.post('/api/admin/registrations/clear')
@admin_only
def clear_all_registrations():
    data = request.get_json(silent=True) or {}

    if not verify_admin_password(data.get('admin_password')):
        return jsonify(
            error='Correct admin password required.'
        ), 403

    with connect() as c:
        c.execute('BEGIN IMMEDIATE')

        count = c.execute(
            'SELECT COUNT(*) FROM registrations'
        ).fetchone()[0]

        c.execute('DELETE FROM members')
        c.execute('DELETE FROM registrations')

    return jsonify(ok=True, cleared=count)




@app.get('/api/admin/registrations')
@admin_only
def registrations():
    with connect() as c:
        rows=c.execute('''SELECT r.id,r.created_at,t.title FROM registrations r JOIN topics t ON t.id=r.topic_id ORDER BY r.created_at DESC''').fetchall()
        return jsonify([{**dict(r),'members':[dict(m) for m in c.execute('SELECT name,usn FROM members WHERE registration_id=? ORDER BY id',(r['id'],)).fetchall()]} for r in rows])

if __name__=='__main__':
    init_db()
    app.run(debug=False,host='127.0.0.1',port=int(os.environ.get('PORT','5000')))
