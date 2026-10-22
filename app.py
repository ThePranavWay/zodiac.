"""Zodiac Seeker v4: four-level finish podium; authenticated solo/team entries, shared notes, organizer recovery."""
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, g, jsonify, request, send_from_directory
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from werkzeug.security import generate_password_hash, check_password_hash
from storage import database, initialize, ConfigurationError

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / 'public'
app = Flask(__name__, static_folder=None)
app.config['MAX_CONTENT_LENGTH'] = 131072
COOKIE = 'zodiac_v2_session'
ADMIN_COOKIE = 'zodiac_v2_organizer'
DEFAULT_DIGEST = '5bfe1b474d3746a8d7b6fb8870087dbe7e0de09421ab40e7338741b38ae738e9'
DUMMY_HASH = generate_password_hash('not-a-real-participant-password', method='scrypt:32768:8:3')

if not os.environ.get('VERCEL') and not os.environ.get('DATABASE_URL'):
    initialize()

class Problem(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status

@app.errorhandler(Problem)
def problem(error):
    return jsonify(error=error.message), error.status

@app.errorhandler(ConfigurationError)
def config_error(error):
    return jsonify(error=str(error)), 503

@app.errorhandler(413)
def too_large(error):
    return jsonify(error='Request too large.'), 413

@app.errorhandler(500)
def internal_error(error):
    cause = getattr(error, 'original_exception', None)
    if cause and (cause.__class__.__name__ == 'UndefinedTable' or isinstance(cause, sqlite3.OperationalError) and 'no such table' in str(cause)):
        return jsonify(error='Database setup incomplete. Run the latest schema.sql in the database used by DATABASE_URL.'), 503
    app.logger.error('Request failed: %s', error)
    return jsonify(error='The archive is temporarily unavailable. Please retry.'), 500


def signing_key():
    key = os.environ.get('SIGNING_KEY', '')
    if not key and not os.environ.get('VERCEL') and not os.environ.get('DATABASE_URL'):
        path = ROOT / 'data' / 'v2-signing.key'
        path.parent.mkdir(exist_ok=True)
        try:
            with path.open('x') as f:
                f.write(secrets.token_hex(32))
            path.chmod(0o600)
        except FileExistsError:
            pass
        key = path.read_text()
    if len(key) < 32:
        raise ConfigurationError('Set SIGNING_KEY to a stable random value of at least 32 characters.')
    return key


def digest(token):
    return hmac.new(signing_key().encode(), token.encode(), hashlib.sha256).hexdigest()


def data():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise Problem('A JSON object is required.')
    return body


def safe_text(value, label, minimum=1, maximum=70):
    if not isinstance(value, str):
        raise Problem(f'Enter a valid {label}.')
    value = value.strip()
    if not minimum <= len(value) <= maximum or any(ord(c) < 32 for c in value):
        raise Problem(f'{label.capitalize()} must contain {minimum}–{maximum} characters.')
    return value


def admission_number(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{3,4}', value):
        raise Problem('Admission number must contain 3 or 4 digits, including any leading zeros.')
    return value


def password_hash(value):
    if not isinstance(value, str) or not 10 <= len(value) <= 128:
        raise Problem('Choose a password of 10–128 characters.')
    return generate_password_hash(value, method='scrypt:32768:8:3')


def limited(bucket, limit, seconds=60, by_ip=True):
    ip = request.remote_addr or 'unknown'
    if os.environ.get('VERCEL'):
        ip = request.headers.get('X-Vercel-Forwarded-For', ip).split(',')[0].strip()
    key = hashlib.sha256((bucket + (':' + ip if by_ip else '')).encode()).hexdigest()
    now = time.time()
    with database() as db:
        row = db.execute('''INSERT INTO zs_limits(bucket_key,window_started,attempts) VALUES(?,?,1)
            ON CONFLICT(bucket_key) DO UPDATE SET
            attempts=CASE WHEN zs_limits.window_started<? THEN 1 ELSE zs_limits.attempts+1 END,
            window_started=CASE WHEN zs_limits.window_started<? THEN excluded.window_started ELSE zs_limits.window_started END
            RETURNING attempts''', (key, now, now-seconds, now-seconds)).fetchone()
    if row['attempts'] > limit:
        raise Problem('Too many attempts. Please wait a few minutes and try again.', 429)


def event_lock(db):
    # All member/entry mutations take this short lock, including fresh-event resets.
    if not db.postgres:
        db.execute('BEGIN IMMEDIATE')
    return db.execute('SELECT * FROM zs_event WHERE id=1' + (' FOR UPDATE' if db.postgres else '')).fetchone()


def current(db):
    token = request.cookies.get(COOKIE, '')
    if not token or len(token) > 256:
        raise Problem('Please log in to your investigator account.', 401)
    row = db.execute('''SELECT m.*,e.kind,e.name AS entry_name,e.started,e.last_seen AS entry_seen
        FROM zs_sessions s JOIN zs_members m ON m.admission=s.admission
        JOIN zs_entries e ON e.id=m.entry_id WHERE s.token_hash=? AND s.expires>?''',
        (digest(token), time.time())).fetchone()
    if not row:
        raise Problem('Your session has expired. Please log in again.', 401)
    return row


def require_user():
    with database() as db:
        return current(db)


def public_member(row):
    return {k: row[k] for k in ('admission','name','class_name','section')}


def finish_data(record, started):
    if not record:
        return None
    return dict(finished_at=record['finished_at'], elapsed_seconds=max(0,record['finished_at']-started),
                podium_place=record['finish_order'] if record['finish_order']<=3 else None)


def progress_data(db, entry_id):
    rows = db.execute('SELECT level_id,completed_at FROM zs_completions WHERE entry_id=? ORDER BY level_id', (entry_id,)).fetchall()
    finish = db.execute('SELECT f.*,e.started FROM zs_finishes f JOIN zs_entries e ON e.id=f.entry_id WHERE f.entry_id=?',(entry_id,)).fetchone()
    return dict(finish=finish_data(finish,finish['started']) if finish else None, completed_levels=[r['level_id'] for r in rows], levels_accomplished=len(rows), total_levels=4,
                completions=[dict(level=r['level_id'],completed_at=r['completed_at']) for r in rows])


def identity_data(db, row):
    members = db.execute('SELECT * FROM zs_members WHERE entry_id=? ORDER BY is_creator DESC,admission', (row['entry_id'],)).fetchall()
    entry = dict(id=row['entry_id'],kind=row['kind'],name=row['entry_name'],started=row['started'])
    student = public_member(row)
    student['started'] = row['started']
    return dict(student=student,entry=entry,members=[dict(**public_member(m),activated=bool(m['password_hash'])) for m in members],
                is_creator=bool(row['is_creator']),server_time=time.time(),**progress_data(db,row['entry_id']))


def issue_session(db, admission):
    token = secrets.token_urlsafe(32)
    db.execute('DELETE FROM zs_sessions WHERE expires<?', (time.time(),))
    db.execute('INSERT INTO zs_sessions(token_hash,admission,expires) VALUES(?,?,?)',
               (digest(token), admission, time.time()+30*86400))
    # A browser may switch account without deleting sessions belonging to its other devices.
    old = request.cookies.get(COOKIE)
    if old:
        db.execute('DELETE FROM zs_sessions WHERE token_hash=?', (digest(old),))
    return token


def set_cookie(response, name, token, seconds):
    # Default Lax for normal top-level browsing. SESSION_COOKIE_SAMESITE=None
    # (always paired with Secure) exists only for trusted cross-site iframe
    # embedding such as a hosted preview frame, where browsers reject Lax
    # session cookies and login would appear to fail right after succeeding.
    samesite = {'lax':'Lax','strict':'Strict','none':'None'}.get(
        os.environ.get('SESSION_COOKIE_SAMESITE','Lax').strip().lower(),'Lax')
    secure = (bool(os.environ.get('VERCEL')) or request.is_secure or samesite == 'None'
              or request.headers.get('X-Forwarded-Proto','').split(',')[0].strip() == 'https')
    response.set_cookie(name, token, max_age=seconds, httponly=True, secure=secure,
                        samesite=samesite, path='/')
    return response


def new_link(db, admission, kind):
    token = secrets.token_urlsafe(32)
    lifetime = 7*86400 if kind == 'activate' else 1800
    db.execute('DELETE FROM zs_tokens WHERE admission=? AND kind=?', (admission, kind))
    db.execute('INSERT INTO zs_tokens(token_hash,admission,kind,expires) VALUES(?,?,?,?)',
               (digest(token), admission, kind, time.time()+lifetime))
    return dict(admission=admission,kind=kind,token=token,expires=time.time()+lifetime)


def audit(db, action, subject=''):
    db.execute('INSERT INTO zs_audit(id,action,subject,at) VALUES(?,?,?,?)',
               (secrets.token_hex(16),action,subject,time.time()))

@app.before_request
def guard():
    if not request.path.startswith('/api/'):
        return
    signing_key()
    if request.method in ('POST','PUT','DELETE'):
        # JSON-only mutation + same-origin checks prevent cross-site form requests.
        if not request.is_json:
            raise Problem('Use application/json.',415)
        origin = request.headers.get('Origin')
        if origin and urlparse(origin).netloc != request.host:
            raise Problem('Request origin not allowed.',403)
        if request.headers.get('Sec-Fetch-Site') == 'cross-site':
            raise Problem('Cross-site requests are not allowed.',403)

@app.after_request
def response_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    if os.environ.get('VERCEL'):
        response.headers['X-Frame-Options'] = 'DENY'
    if request.path.startswith('/api/') or request.path in ('/organizer','/organizer.html'):
        response.headers['Cache-Control'] = 'no-store'
    return response

@app.get('/api/config')
def config():
    with database() as db:
        event = db.execute('SELECT * FROM zs_event WHERE id=1').fetchone()
    return jsonify(registration_open=bool(event['registration_open']),generation=event['generation'],version=4,total_levels=4,podium_enabled=True)

@app.post('/api/register')
def register():
    limited('register',30)
    body = data()
    kind = body.get('kind')
    members = body.get('members')
    if kind not in ('solo','team') or not isinstance(members,list):
        raise Problem('Select Solo or Team and provide member details.')
    if (kind == 'solo' and len(members) != 1) or (kind == 'team' and not 2 <= len(members) <= 4):
        raise Problem('Solo requires one student. Teams require 2–4 students.')
    clean = []
    for member in members:
        if not isinstance(member,dict):
            raise Problem('Every investigator needs complete details.')
        adm = admission_number(member.get('admission'))
        name = safe_text(member.get('name'),'full name',2)
        cls = str(member.get('class_name',''))
        section = safe_text(member.get('section'),'section',1,3).upper()
        if cls not in [str(i) for i in range(1,13)] or not re.fullmatch('[A-Z]{1,3}',section):
            raise Problem('Select a valid class and alphabetic section for every member.')
        clean.append(dict(admission=adm,name=name,class_name=cls,section=section))
    if len({m['admission'] for m in clean}) != len(clean):
        raise Problem('Each team member must have a different admission number.')
    name = clean[0]['name'] if kind == 'solo' else safe_text(body.get('team_name'),'team name',2)
    hashed = password_hash(body.get('password'))
    entry_id = secrets.token_hex(16)
    invitations = []
    try:
        with database() as db:
            event = event_lock(db)
            if not event['registration_open']:
                raise Problem('Registration is currently closed. Please contact the organizers.',403)
            for member in clean:
                if db.execute('SELECT admission FROM zs_members WHERE admission=?',(member['admission'],)).fetchone():
                    raise Problem('One or more admission numbers are already registered. Log in instead, or contact the organizer.',409)
            now = time.time()
            db.execute('INSERT INTO zs_entries(id,kind,name,started,last_seen) VALUES(?,?,?,?,?)',(entry_id,kind,name,now,now))
            for i,m in enumerate(clean):
                db.execute('''INSERT INTO zs_members(admission,entry_id,name,class_name,section,password_hash,is_creator,last_seen)
                    VALUES(?,?,?,?,?,?,?,?)''',(m['admission'],entry_id,m['name'],m['class_name'],m['section'],hashed if i==0 else None,int(i==0),now))
                if i:
                    invitations.append(new_link(db,m['admission'],'activate'))
            db.execute('INSERT INTO zs_notes(entry_id,body,version,updated_at,updated_by) VALUES(?,?,0,?,?)',
                       (entry_id,'',now,clean[0]['admission']))
            token = issue_session(db, clean[0]['admission'])
            row = db.execute('''SELECT m.*,e.kind,e.name AS entry_name,e.started FROM zs_members m
                JOIN zs_entries e ON e.id=m.entry_id WHERE admission=?''',(clean[0]['admission'],)).fetchone()
            result = identity_data(db,row)
            audit(db,'register',entry_id)
    except sqlite3.IntegrityError:
        raise Problem('An admission number was registered simultaneously. No partial team was saved.',409)
    except Exception as error:
        if error.__class__.__name__ == 'UniqueViolation':
            raise Problem('An admission number was registered simultaneously. No partial team was saved.',409)
        raise
    return set_cookie(jsonify(**result,invitations=invitations),COOKIE,token,30*86400),201

@app.post('/api/login')
def login():
    limited('login-ip',120,300)
    body = data()
    admission = body.get('admission','')
    if not isinstance(admission,str) or len(admission)>20:
        admission = 'invalid'
    limited('login-account:'+admission,10,300,False)
    password = body.get('password')
    if not isinstance(password,str) or len(password)>128:
        raise Problem('Invalid admission number or password.',401)
    with database() as db:
        row = db.execute('SELECT password_hash FROM zs_members WHERE admission=?',(admission,)).fetchone()
    valid = check_password_hash(row['password_hash'] if row and row['password_hash'] else DUMMY_HASH,password)
    if not row or not row['password_hash'] or not valid:
        raise Problem('Invalid admission number or password.',401)
    with database() as db:
        event_lock(db)
        # Recheck after obtaining the reset/activation lock.
        row2 = db.execute('SELECT password_hash FROM zs_members WHERE admission=?',(admission,)).fetchone()
        if not row2 or row2['password_hash'] != row['password_hash']:
            raise Problem('Account changed. Please log in again.',401)
        token = issue_session(db,admission)
    return set_cookie(jsonify(ok=True),COOKIE,token,30*86400)

@app.post('/api/logout')
def logout():
    with database() as db:
        token = request.cookies.get(COOKIE,'')
        db.execute('DELETE FROM zs_sessions WHERE token_hash=?',(digest(token),))
    response = jsonify(ok=True)
    response.delete_cookie(COOKIE,path='/')
    return response

@app.get('/api/me')
def me():
    with database() as db:
        row = current(db)
        now = time.time()
        db.execute('UPDATE zs_entries SET last_seen=? WHERE id=?',(now,row['entry_id']))
        db.execute('UPDATE zs_members SET last_seen=? WHERE admission=?',(now,row['admission']))
        result = identity_data(db,row)
    return jsonify(**result)

@app.post('/api/token/complete')
def complete_token():
    limited('token-complete',30,300)
    body = data()
    token = body.get('token')
    if not isinstance(token,str) or not 20 <= len(token) <= 128:
        raise Problem('This link is invalid or expired.',400)
    hashed = password_hash(body.get('password'))
    with database() as db:
        event_lock(db)
        link = db.execute('DELETE FROM zs_tokens WHERE token_hash=? AND expires>? RETURNING admission,kind',
                          (digest(token),time.time())).fetchone()
        if not link:
            raise Problem('This link is invalid, expired, or already used. Ask for a new link.',400)
        member = db.execute('SELECT password_hash FROM zs_members WHERE admission=?',(link['admission'],)).fetchone()
        if not member or (link['kind']=='activate' and member['password_hash']):
            raise Problem('This account is already activated. Log in or contact the organizer.',409)
        db.execute('UPDATE zs_members SET password_hash=? WHERE admission=?',(hashed,link['admission']))
        db.execute('DELETE FROM zs_sessions WHERE admission=?',(link['admission'],))
        db.execute('DELETE FROM zs_tokens WHERE admission=?',(link['admission'],))
        session = issue_session(db,link['admission'])
        audit(db,link['kind']+'-completed',link['admission'])
    return set_cookie(jsonify(ok=True),COOKIE,session,30*86400)

@app.post('/api/invitations')
def invitations():
    limited('invite',30,300)
    body = data()
    admission = admission_number(body.get('admission'))
    with database() as db:
        event_lock(db)
        row = current(db)
        if not row['is_creator'] or row['kind'] != 'team':
            raise Problem('Only the team creator can issue activation invitations.',403)
        target = db.execute('SELECT * FROM zs_members WHERE admission=? AND entry_id=?',(admission,row['entry_id'])).fetchone()
        if not target or target['password_hash']:
            raise Problem('Choose an unactivated member of your own team.',400)
        link = new_link(db,admission,'activate')
        audit(db,'activation-issued',admission)
    return jsonify(**link)

@app.get('/api/progress')
def progress():
    with database() as db:
        row = current(db)
        result = progress_data(db,row['entry_id'])
    return jsonify(**result,server_time=time.time())

@app.post('/api/levels/<int:level>/submit')
def submit_level(level):
    if level not in (1,2,3,4):
        raise Problem('Unknown level.',404)
    row = require_user()
    limited('level:'+row['entry_id']+':'+str(level),30)
    body = data()
    if set(body) != {'password'} or not isinstance(body['password'],str) or len(body['password'])>512:
        raise Problem('Only the level password is accepted.')
    password = body['password']
    if level == 1:
        password = password.strip()
    elif level in (2,4):
        password = password.strip().upper()
    expected = os.environ.get(f'LEVEL_{level}_PASSWORD_SHA256',DEFAULT_DIGEST).lower()
    if not re.fullmatch('[a-f0-9]{64}',expected):
        raise ConfigurationError(f'LEVEL_{level}_PASSWORD_SHA256 must be a SHA-256 hex digest.')
    if not hmac.compare_digest(hashlib.sha256(password.encode()).hexdigest(),expected):
        raise Problem('Incorrect password. Please try again.')
    with database() as db:
        event_lock(db)
        row = current(db)
        inserted = db.execute('''INSERT INTO zs_completions(entry_id,level_id,completed_at) VALUES(?,?,?)
            ON CONFLICT(entry_id,level_id) DO NOTHING RETURNING level_id''',(row['entry_id'],level,time.time())).fetchone()
        count = db.execute('SELECT COUNT(*) AS n,MAX(completed_at) AS latest FROM zs_completions WHERE entry_id=?',(row['entry_id'],)).fetchone()
        if count['n']==4:
            # The global event lock serializes distinct final submissions and reset.
            # Never trust a client finish time, duration, rank or claimed place.
            next_place = db.execute('SELECT COALESCE(MAX(finish_order),0)+1 AS n FROM zs_finishes').fetchone()['n']
            db.execute('''INSERT INTO zs_finishes(entry_id,finished_at,finish_order) VALUES(?,?,?)
                ON CONFLICT(entry_id) DO NOTHING''',(row['entry_id'],count['latest'],next_place))
        result = progress_data(db,row['entry_id'])
    return jsonify(success=True,level=level,already_completed=inserted is None,**result,server_time=time.time())

@app.get('/api/leaderboard')
def leaderboard():
    with database() as db:
        current(db)
        entries = db.execute('SELECT * FROM zs_entries ORDER BY started,id').fetchall()
        members = db.execute('SELECT entry_id,name,class_name,section FROM zs_members ORDER BY is_creator DESC,admission').fetchall()
        completions = db.execute('SELECT entry_id,level_id FROM zs_completions ORDER BY level_id').fetchall()
        finishes = {f['entry_id']:f for f in db.execute('SELECT * FROM zs_finishes').fetchall()}
    now = time.time()
    rows = []
    for entry in entries:
        member_list = [dict(name=m['name'],class_name=m['class_name'],section=m['section']) for m in members if m['entry_id']==entry['id']]
        levels = [c['level_id'] for c in completions if c['entry_id']==entry['id']]
        rows.append(dict(id=entry['id'],kind=entry['kind'],name=entry['name'],started=entry['started'],last_seen=entry['last_seen'],
                         members=member_list,completed_levels=levels,levels_accomplished=len(levels),
                         finish=finish_data(finishes.get(entry['id']),entry['started'])))
    # Finished entries first in immutable finish order. Other entries keep registration order.
    rows.sort(key=lambda row: (0,finishes[row['id']]['finish_order']) if row['id'] in finishes else (1,row['started'],row['id']))
    podium = [dict(id=row['id'],kind=row['kind'],name=row['name'],members=row['members'],**row['finish'])
              for row in rows if row['finish'] and row['finish']['podium_place'] is not None]
    return jsonify(entries=rows,podium=podium,total=len(rows),active=sum(r['last_seen']>now-60 for r in rows),server_time=now,
                   scoring_enabled=False,podium_enabled=True,rules='Only the first three solo/team entries to verify all four levels receive podium places, in server-recorded finish order. Every completed entry has its timer stopped. This is not a fastest-elapsed-time contest.')

@app.get('/api/notes')
def get_notes():
    with database() as db:
        row = current(db)
        notes = db.execute('SELECT body,version,updated_at,updated_by FROM zs_notes WHERE entry_id=?',(row['entry_id'],)).fetchone()
    return jsonify(**dict(notes),server_time=time.time())

@app.post('/api/notes')
def save_notes():
    row = require_user()
    limited('notes:'+row['admission'],90)
    body = data()
    text, version = body.get('body'),body.get('version')
    if not isinstance(text,str) or len(text)>20000 or type(version) is not int or version<0:
        raise Problem('Notes must be at most 20,000 characters and include a valid version.')
    with database() as db:
        event_lock(db)
        row = current(db)
        updated = db.execute('''UPDATE zs_notes SET body=?,version=version+1,updated_at=?,updated_by=?
            WHERE entry_id=? AND version=? RETURNING body,version,updated_at,updated_by''',
            (text,time.time(),row['admission'],row['entry_id'],version)).fetchone()
        if not updated:
            latest = db.execute('SELECT body,version,updated_at,updated_by FROM zs_notes WHERE entry_id=?',(row['entry_id'],)).fetchone()
            return jsonify(error='Another member updated the notebook. Review both versions before saving.',latest=dict(latest)),409
    return jsonify(**dict(updated))

# Organizer credentials are never included in the ZIP or browser JS.
def organizer_password():
    value = os.environ.get('ORGANIZER_PASSWORD','')
    if len(value)<32:
        raise ConfigurationError('Set ORGANIZER_PASSWORD to a private random value of at least 32 characters.')
    return value


def admin_serializer():
    return URLSafeTimedSerializer(signing_key(),salt='organizer-v2')


def admin_required(fn):
    @wraps(fn)
    def wrapped(*args,**kwargs):
        try:
            record = admin_serializer().loads(request.cookies.get(ADMIN_COOKIE,''),max_age=3600)
            expected = hashlib.sha256(organizer_password().encode()).hexdigest()
            if not isinstance(record,dict) or not hmac.compare_digest(record.get('key',''),expected):
                raise BadSignature('invalid')
        except (BadSignature,SignatureExpired):
            raise Problem('Organizer sign-in required.',401)
        return fn(*args,**kwargs)
    return wrapped

@app.post('/api/admin/login')
def admin_login():
    limited('organizer-login',5,900)
    supplied = data().get('password','')
    if not isinstance(supplied,str) or not hmac.compare_digest(supplied.encode(),organizer_password().encode()):
        raise Problem('Invalid organizer credentials.',401)
    token = admin_serializer().dumps({'key':hashlib.sha256(organizer_password().encode()).hexdigest()})
    return set_cookie(jsonify(ok=True),ADMIN_COOKIE,token,3600)

@app.post('/api/admin/logout')
def admin_logout():
    response = jsonify(ok=True)
    response.delete_cookie(ADMIN_COOKIE,path='/')
    return response

@app.get('/api/admin/state')
@admin_required
def admin_state():
    with database() as db:
        event = dict(db.execute('SELECT * FROM zs_event WHERE id=1').fetchone())
        members = db.execute('''SELECT m.admission,m.name,m.class_name,m.section,m.password_hash,e.name AS entry_name,e.kind
            FROM zs_members m JOIN zs_entries e ON e.id=m.entry_id ORDER BY e.started,m.admission''').fetchall()
        counts = {name:db.execute('SELECT COUNT(*) AS n FROM '+table).fetchone()['n'] for name,table in
                  [('entries','zs_entries'),('members','zs_members'),('completions','zs_completions')]}
    with database() as db:
        winners = db.execute('SELECT f.*,e.name,e.kind,e.started FROM zs_finishes f JOIN zs_entries e ON e.id=f.entry_id WHERE f.finish_order<=3 ORDER BY f.finish_order').fetchall()
    return jsonify(event=event,counts=counts,podium=[dict(name=w['name'],kind=w['kind'],**finish_data(w,w['started'])) for w in winners],members=[dict(admission=m['admission'],name=m['name'],class_name=m['class_name'],section=m['section'],
                   entry_name=m['entry_name'],kind=m['kind'],activated=bool(m['password_hash'])) for m in members])

@app.post('/api/admin/registration')
@admin_required
def registration_switch():
    value = data().get('open')
    if type(value) is not bool:
        raise Problem('Specify open as true or false.')
    with database() as db:
        event_lock(db)
        db.execute('UPDATE zs_event SET registration_open=? WHERE id=1',(int(value),))
        audit(db,'registration-open' if value else 'registration-closed')
    return jsonify(ok=True)

@app.post('/api/admin/reset-password')
@admin_required
def admin_reset_password():
    limited('organizer-reset',30,300)
    admission = admission_number(data().get('admission'))
    with database() as db:
        event_lock(db)
        member = db.execute('SELECT * FROM zs_members WHERE admission=?',(admission,)).fetchone()
        if not member:
            raise Problem('Admission number not found.',404)
        # Immediately revoke old sign-ins once an identity-verified organizer starts recovery.
        db.execute('DELETE FROM zs_sessions WHERE admission=?',(admission,))
        link = new_link(db,admission,'reset' if member['password_hash'] else 'activate')
        audit(db,'organizer-recovery-issued',admission)
    return jsonify(**link)

@app.get('/api/admin/export')
@admin_required
def export_results():
    with database() as db:
        event_lock(db)
        event = dict(db.execute('SELECT * FROM zs_event WHERE id=1').fetchone())
        entries = [dict(r) for r in db.execute('SELECT * FROM zs_entries ORDER BY started').fetchall()]
        members = [dict(r) for r in db.execute('SELECT admission,entry_id,name,class_name,section,is_creator FROM zs_members').fetchall()]
        completions = [dict(r) for r in db.execute('SELECT * FROM zs_completions').fetchall()]
        notes = [dict(r) for r in db.execute('SELECT * FROM zs_notes').fetchall()]
        finishes = [dict(r) for r in db.execute('SELECT * FROM zs_finishes ORDER BY finish_order').fetchall()]
        audit(db,'export-results')
    return jsonify(format='zodiac-results-v4',exported_at=time.time(),event=event,entries=entries,members=members,completions=completions,notes=notes,finishes=finishes)

@app.post('/api/admin/fresh-event')
@admin_required
def fresh_event():
    body = data()
    supplied = body.get('password','')
    if body.get('confirm') != 'START FRESH' or not isinstance(supplied,str) or not hmac.compare_digest(supplied.encode(),organizer_password().encode()):
        raise Problem('Re-enter the organizer password and type START FRESH to confirm.',403)
    with database() as db:
        event_lock(db)
        # Cascading foreign keys remove members, sessions, tokens, completions and notes.
        db.execute('DELETE FROM zs_entries')
        db.execute('DELETE FROM zs_limits')
        db.execute('DELETE FROM zs_audit')
        db.execute('UPDATE zs_event SET registration_open=0,generation=generation+1 WHERE id=1')
        audit(db,'fresh-event')
    return jsonify(ok=True,message='Event reset. Registration is closed until you reopen it.')

@app.get('/organizer')
@app.get('/organizer.html')
def organizer_page():
    return send_from_directory(PUBLIC,'organizer.html')

@app.route('/api/<path:unknown>',methods=['GET','POST','PUT','DELETE'])
def unknown_api(unknown):
    raise Problem('Not found.',404)

@app.get('/')
def home():
    return send_from_directory(PUBLIC,'index.html')

@app.get('/<path:filename>')
def static_file(filename):
    return send_from_directory(PUBLIC,filename)

@app.get('/play')
@app.get('/play.html')
def play_page():
    if (PUBLIC / 'play.html').is_file():
        return send_from_directory(PUBLIC, 'play.html')
    # Compatibility with a deployment whose old game is still index.html.
    # Never fall back to a launch page, which would create a redirect loop.
    old_index = PUBLIC / 'index.html'
    if old_index.is_file() and 'id="login-form"' in old_index.read_text(encoding='utf-8'):
        return send_from_directory(PUBLIC, 'index.html')
    return ('The game page is missing. Preserve your existing game index.html '
            'as public/play.html before replacing the homepage with a launch page.'), 503


# Zodiac Seeker: scheduled event closure, 13 November 2026 at NOON IST.
from datetime import datetime
from flask import redirect

ZODIAC_EVENT_END_AT = datetime.fromisoformat(
    '2026-11-13T12:00:00+05:30'
).timestamp()

@app.get('/api/event-clock')
def zodiac_event_clock():
    now = time.time()
    response = jsonify(
        server_time=now,
        ends_at=ZODIAC_EVENT_END_AT,
        ended=now >= ZODIAC_EVENT_END_AT,
        timezone='Asia/Kolkata'
    )
    response.headers['Cache-Control'] = 'no-store'
    return response

@app.get('/event-ended')
@app.get('/event-ended.html')
def zodiac_event_ended_page():
    response = send_from_directory(PUBLIC, 'event-ended.html')
    response.headers['Cache-Control'] = 'no-store'
    return response

@app.before_request
def zodiac_event_closing_guard():
    if time.time() < ZODIAC_EVENT_END_AT:
        return None

    path = request.path.rstrip('/') or '/'
    # Direct requests to Flask game entry routes also redirect after the end.
    if request.method in ('GET', 'HEAD') and path in (
        '/', '/index.html', '/play', '/play.html'
    ):
        response = redirect('/event-ended', code=302)
        response.headers['Cache-Control'] = 'no-store'
        return response

    # Reject NEW registrations and answer/hint requests received after closure.
    # Notes, login, results and organizer functions remain accessible.
    if request.method == 'POST' and (
        path == '/api/register'
        or path.startswith('/api/levels/')
        or path.startswith('/api/casework/')
    ):
        response = jsonify(
            error='This event has ended. Thank you for participating in Zodiac Seeker.',
            event_ended=True,
            redirect='/event-ended'
        )
        response.headers['Cache-Control'] = 'no-store'
        return response, 410

if __name__ == '__main__':
    app.run(host='0.0.0.0',port=int(os.environ.get('PORT','3000')),debug=False)
