"""Destructive tests: isolated SQLite by default; only disposable PostgreSQL when explicitly enabled."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
TMP=tempfile.TemporaryDirectory()
if os.environ.get('DATABASE_URL') and os.environ.get('RUN_POSTGRES_TESTS')!='1':
    raise RuntimeError('Refusing to run against DATABASE_URL. Use only a disposable test database.')
os.environ['LOCAL_DATABASE_PATH']=str(Path(TMP.name)/'tests.sqlite3')
os.environ['SIGNING_KEY']='test-signing-key-never-production-'+secrets.token_hex(16)
os.environ['ORGANIZER_PASSWORD']='test-organizer-key-never-production-'+secrets.token_hex(16)
for level in range(1,5):
    os.environ[f'LEVEL_{level}_PASSWORD_SHA256']=hashlib.sha256(('LEVEL-'+str(level)).encode()).hexdigest()
from app import app, COOKIE, ADMIN_COOKIE
from storage import database, initialize
initialize()
app.config.update(TESTING=True)
PW='my-private-passphrase-123'

class EventTests(unittest.TestCase):
    def setUp(self):
        with database() as db:
            db.execute('DELETE FROM zs_entries')
            db.execute('DELETE FROM zs_limits')
            db.execute('DELETE FROM zs_audit')
            db.execute('UPDATE zs_event SET registration_open=1,generation=1 WHERE id=1')
        self.client=app.test_client()
    def member(self,admission='052'):
        return dict(admission=admission,name='Student '+admission,class_name='11',section='A')
    def register(self,client=None,kind='solo',admissions=None,**extra):
        payload=dict(kind=kind,members=[self.member(a) for a in (admissions or ['052'])],password=PW,team_name='Cipher Society')
        payload.update(extra)
        return (client or self.client).post('/api/register',json=payload)
    def team(self,size=2):
        result=self.register(kind='team',admissions=['052','053','054','055'][:size])
        self.assertEqual(result.status_code,201,result.json)
        return result.json
    def activate(self,token,client=None,password=PW):
        return (client or app.test_client()).post('/api/token/complete',json=dict(token=token,password=password))
    def organizer(self):
        client=app.test_client()
        result=client.post('/api/admin/login',json={'password':os.environ['ORGANIZER_PASSWORD']})
        self.assertEqual(result.status_code,200,result.json)
        return client
    def count(self,table):
        with database() as db:return db.execute('SELECT COUNT(*) AS n FROM '+table).fetchone()['n']
    def test_solo_registration_leading_zeros_hashed_password(self):
        result=self.register();self.assertEqual(result.status_code,201)
        self.assertEqual(result.json['student']['admission'],'052')
        self.assertEqual(result.json['entry']['kind'],'solo')
        self.assertEqual(result.json['levels_accomplished'],0)
        with database() as db:row=db.execute('SELECT password_hash FROM zs_members').fetchone()
        self.assertTrue(row['password_hash'].startswith('scrypt:'))
        self.assertNotIn(PW,row['password_hash'])
        self.assertNotIn('password_hash',json.dumps(result.json))
        self.assertIn('HttpOnly',result.headers['Set-Cookie']);self.assertIn('SameSite=Lax',result.headers['Set-Cookie'])
    def test_three_and_four_digits_remain_distinct(self):
        for admission in ['052','0052','123','1234']:
            self.assertEqual(self.register(app.test_client(),admissions=[admission]).status_code,201)
        self.assertEqual(self.count('zs_members'),4)
    def test_invalid_admissions(self):
        for admission in ['12','12345','１２３','abc','']:
            body=dict(kind='solo',members=[self.member(admission)],password=PW)
            self.assertEqual(self.client.post('/api/register',json=body).status_code,400)
        self.assertEqual(self.count('zs_entries'),0)
    def test_password_and_member_validation(self):
        self.assertEqual(self.register(password='short').status_code,400)
        bad=self.member();bad['section']='1'
        self.assertEqual(self.register(members=[bad]).status_code,400)
        bad=self.member();bad['class_name']='13'
        self.assertEqual(self.register(members=[bad]).status_code,400)
    def test_team_sizes_two_three_four(self):
        for size in [2,3,4]:
            with self.subTest(size=size):
                admissions=[str(200+size*10+i) for i in range(size)]
                result=self.register(app.test_client(),kind='team',admissions=admissions)
                self.assertEqual(result.status_code,201,result.json)
                self.assertEqual(len(result.json['invitations']),size-1)
                self.assertEqual(len(result.json['members']),size)
    def test_invalid_team_sizes_and_duplicate_member_are_atomic(self):
        for admissions in [['052'],['052','053','054','055','056'],['052','052']]:
            self.assertEqual(self.register(kind='team',admissions=admissions).status_code,400)
        self.assertEqual(self.count('zs_entries'),0);self.assertEqual(self.count('zs_members'),0)
    def test_invalid_member_causes_no_partial_team(self):
        members=[self.member('052'),self.member('053')];members[1]['name']='X'
        self.assertEqual(self.register(kind='team',members=members).status_code,400)
        self.assertEqual(self.count('zs_entries'),0);self.assertEqual(self.count('zs_tokens'),0)
    def test_solo_cannot_register_again_or_join_team(self):
        self.assertEqual(self.register().status_code,201)
        self.assertEqual(self.register(app.test_client()).status_code,409)
        self.assertEqual(self.register(app.test_client(),kind='team',admissions=['053','052']).status_code,409)
        self.assertEqual(self.count('zs_entries'),1);self.assertEqual(self.count('zs_members'),1)
    def test_team_member_cannot_register_solo_or_another_team(self):
        self.team()
        self.assertEqual(self.register(app.test_client(),admissions=['053']).status_code,409)
        self.assertEqual(self.register(app.test_client(),kind='team',admissions=['054','053']).status_code,409)
        self.assertEqual(self.count('zs_members'),2)
    def test_duplicate_parallel_registrations(self):
        def attempt(_):return self.register(app.test_client()).status_code
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:results=list(pool.map(attempt,range(5)))
        self.assertEqual(results.count(201),1);self.assertEqual(results.count(409),4)
    def test_conflicting_parallel_teams_leave_no_partial_members(self):
        def attempt(i):return self.register(app.test_client(),kind='team',admissions=[str(610+i),'699']).status_code
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(attempt,range(4)))
        self.assertEqual(results.count(201),1);self.assertEqual(self.count('zs_members'),2)
    def test_login_other_browser_preserves_timer_progress_and_notes(self):
        registration=self.register().json
        self.client.post('/api/levels/1/submit',json={'password':'LEVEL-1'})
        self.client.post('/api/notes',json={'body':'Saved observations','version':0})
        other=app.test_client();self.assertEqual(other.post('/api/login',json={'admission':'052','password':PW}).status_code,200)
        result=other.get('/api/me').json
        self.assertEqual(result['entry']['started'],registration['entry']['started'])
        self.assertEqual(result['completed_levels'],[1]);self.assertEqual(other.get('/api/notes').json['body'],'Saved observations')
        self.assertEqual(self.count('zs_entries'),1)
    def test_wrong_login_generic_and_account_rate_limit(self):
        self.register()
        unknown=app.test_client().post('/api/login',json={'admission':'999','password':'wrong'})
        wrong=app.test_client().post('/api/login',json={'admission':'052','password':'wrong'})
        self.assertEqual(unknown.status_code,401);self.assertEqual(unknown.json,wrong.json)
        for _ in range(9):self.client.post('/api/login',json={'admission':'052','password':'wrong'})
        self.assertEqual(self.client.post('/api/login',json={'admission':'052','password':PW}).status_code,429)
    def test_session_cookie_samesite_configurable_for_iframe_embedding(self):
        self.register();self.client.post('/api/logout',json={})
        old=os.environ.pop('SESSION_COOKIE_SAMESITE',None)
        try:
            default=self.client.post('/api/login',json={'admission':'052','password':PW})
            self.assertEqual(default.status_code,200)
            self.assertIn('SameSite=Lax',default.headers['Set-Cookie'])
            self.client.post('/api/logout',json={})
            os.environ['SESSION_COOKIE_SAMESITE']='None'
            embedded=self.client.post('/api/login',json={'admission':'052','password':PW})
            self.assertEqual(embedded.status_code,200)
            self.assertIn('SameSite=None',embedded.headers['Set-Cookie'])
            self.assertIn('Secure',embedded.headers['Set-Cookie'])
            self.assertEqual(self.client.get('/api/me').status_code,200)
        finally:
            if old is None:os.environ.pop('SESSION_COOKIE_SAMESITE',None)
            else:os.environ['SESSION_COOKIE_SAMESITE']=old
    def test_logout_and_session_expiry(self):
        self.register();self.assertEqual(self.client.post('/api/logout',json={}).status_code,200)
        self.assertEqual(self.client.get('/api/me').status_code,401)
        self.client.post('/api/login',json={'admission':'052','password':PW})
        with database() as db:db.execute('UPDATE zs_sessions SET expires=0')
        self.assertEqual(self.client.get('/api/me').status_code,401)
    def test_team_activation_single_use_and_private_passwords(self):
        team=self.team();other=app.test_client();token=team['invitations'][0]['token']
        self.assertEqual(other.post('/api/login',json={'admission':'053','password':PW}).status_code,401)
        self.assertEqual(self.activate(token,other,'different-private-password').status_code,200)
        self.assertEqual(other.get('/api/me').json['entry']['started'],team['entry']['started'])
        self.assertEqual(self.activate(token).status_code,400)
        self.assertEqual(app.test_client().post('/api/login',json={'admission':'053','password':PW}).status_code,401)
        self.assertEqual(app.test_client().post('/api/login',json={'admission':'053','password':'different-private-password'}).status_code,200)
    def test_expired_and_replaced_activation_links(self):
        team=self.team();old=team['invitations'][0]['token']
        new=self.client.post('/api/invitations',json={'admission':'053'}).json['token']
        self.assertEqual(self.activate(old).status_code,400)
        with database() as db:db.execute('UPDATE zs_tokens SET expires=0')
        self.assertEqual(self.activate(new).status_code,400)
    def test_invitation_access_control(self):
        team=self.team();other=app.test_client();self.activate(team['invitations'][0]['token'],other)
        self.assertEqual(other.post('/api/invitations',json={'admission':'053'}).status_code,403)
        outsider=app.test_client();self.register(outsider,admissions=['999'])
        self.assertEqual(outsider.post('/api/invitations',json={'admission':'053'}).status_code,403)
    def test_shared_completions_and_unrelated_solo_isolation(self):
        team=self.team();other=app.test_client();self.activate(team['invitations'][0]['token'],other)
        outsider=app.test_client();self.register(outsider,admissions=['999'])
        for level in range(1,5):
            password='LEVEL-'+str(level)
            response=self.client.post(f'/api/levels/{level}/submit',json={'password':password})
            self.assertEqual(response.status_code,200,response.json)
            self.assertFalse(response.json['already_completed'])
            self.assertTrue(other.post(f'/api/levels/{level}/submit',json={'password':password}).json['already_completed'])
        self.assertEqual(other.get('/api/progress').json['completed_levels'],[1,2,3,4])
        self.assertEqual(outsider.get('/api/progress').json['completed_levels'],[])
        self.assertEqual(self.count('zs_completions'),4)
    def test_bad_level_password_and_spoofed_identity(self):
        self.register()
        self.assertEqual(self.client.post('/api/levels/1/submit',json={'password':'wrong'}).status_code,400)
        self.assertEqual(self.client.post('/api/levels/1/submit',json={'password':'LEVEL-1','entry_id':'other'}).status_code,400)
        self.assertEqual(self.client.post('/api/levels/5/submit',json={'password':'LEVEL-5'}).status_code,404)
        self.assertEqual(self.count('zs_completions'),0)
    def test_simultaneous_completion_counted_once(self):
        self.register();cookie=self.client.get_cookie(COOKIE).value
        def attempt(_):
            c=app.test_client();c.set_cookie(COOKIE,cookie)
            return c.post('/api/levels/1/submit',json={'password':'LEVEL-1'}).json
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(attempt,range(6)))
        self.assertEqual(sum(not r['already_completed'] for r in results),1);self.assertEqual(self.count('zs_completions'),1)
    def test_shared_cloud_notes_conflicts_and_isolation(self):
        team=self.team();other=app.test_client();self.activate(team['invitations'][0]['token'],other)
        self.assertEqual(self.client.post('/api/notes',json={'body':'First text','version':0}).status_code,200)
        latest=other.get('/api/notes').json;self.assertEqual(latest['body'],'First text')
        conflict=other.post('/api/notes',json={'body':'Second local text','version':0})
        self.assertEqual(conflict.status_code,409);self.assertEqual(conflict.json['latest']['body'],'First text')
        self.assertEqual(other.post('/api/notes',json={'body':'Combined text','version':1}).status_code,200)
        self.assertEqual(self.client.get('/api/notes').json['body'],'Combined text')
        outsider=app.test_client();self.register(outsider,admissions=['999'])
        self.assertEqual(outsider.get('/api/notes').json['body'],'')
    def test_invalid_notes_length_and_version(self):
        self.register()
        for payload in [{'body':'x'*20001,'version':0},{'body':'text','version':True},{'body':'text','version':-1}]:
            self.assertEqual(self.client.post('/api/notes',json=payload).status_code,400)
    def test_notebook_parallel_compare_and_swap(self):
        self.register();cookie=self.client.get_cookie(COOKIE).value
        def attempt(i):
            c=app.test_client();c.set_cookie(COOKIE,cookie)
            return c.post('/api/notes',json={'body':'edit '+str(i),'version':0}).status_code
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:results=list(pool.map(attempt,range(5)))
        self.assertEqual(results.count(200),1);self.assertEqual(results.count(409),4)
    def test_leaderboard_one_row_per_entry_no_admissions(self):
        self.team();other=app.test_client();self.register(other,admissions=['999'])
        board=self.client.get('/api/leaderboard').json
        self.assertEqual(board['total'],2);self.assertNotIn('admission',json.dumps(board));self.assertNotIn('password',json.dumps(board))
        self.assertEqual(len(board['entries'][0]['members']),2)
    def test_unauthenticated_api_cannot_read_or_mutate(self):
        for route in ['/api/me','/api/notes','/api/progress','/api/leaderboard','/api/admin/state','/api/admin/export']:
            self.assertEqual(self.client.get(route).status_code,401,route)
        for route,payload in [('/api/notes',{'body':'x','version':0}),('/api/levels/1/submit',{'password':'LEVEL-1'}),('/api/admin/registration',{'open':True})]:
            self.assertEqual(self.client.post(route,json=payload).status_code,401,route)
    def test_csrf_json_origin_and_fetch_site(self):
        for headers in [{'Origin':'https://evil.example'},{'Sec-Fetch-Site':'cross-site'}]:
            self.assertEqual(self.client.post('/api/login',json={},headers=headers).status_code,403)
        self.assertEqual(self.client.post('/api/login',data='admission=052').status_code,415)
    def test_old_recovery_endpoint_and_device_header_do_not_authenticate(self):
        self.register()
        old=app.test_client()
        self.assertEqual(old.post('/api/restore',json={'admission':'052','started':1,'recovery_token':'anything'}).status_code,404)
        self.assertEqual(old.get('/api/me',headers={'X-Device-Key':'a'*64}).status_code,401)
    def test_organizer_login_and_recovery_preserve_everything(self):
        registration=self.register().json
        self.client.post('/api/levels/1/submit',json={'password':'LEVEL-1'})
        self.client.post('/api/notes',json={'body':'Keep me','version':0})
        admin=self.organizer();result=admin.post('/api/admin/reset-password',json={'admission':'052'})
        self.assertEqual(result.status_code,200)
        self.assertEqual(self.client.get('/api/me').status_code,401)
        other=app.test_client();self.assertEqual(self.activate(result.json['token'],other,'new-private-password').status_code,200)
        restored=other.get('/api/me').json;self.assertEqual(restored['entry']['started'],registration['entry']['started'])
        self.assertEqual(restored['completed_levels'],[1]);self.assertEqual(other.get('/api/notes').json['body'],'Keep me')
        self.assertEqual(app.test_client().post('/api/login',json={'admission':'052','password':PW}).status_code,401)
        self.assertEqual(self.activate(result.json['token']).status_code,400)
    def test_organizer_password_and_login_rate_limit(self):
        for _ in range(5):self.assertEqual(self.client.post('/api/admin/login',json={'password':'wrong'}).status_code,401)
        self.assertEqual(self.client.post('/api/admin/login',json={'password':os.environ['ORGANIZER_PASSWORD']}).status_code,429)
    def test_registration_gate_does_not_pause_existing_login(self):
        self.register();admin=self.organizer()
        self.assertEqual(admin.post('/api/admin/registration',json={'open':False}).status_code,200)
        self.assertEqual(self.register(app.test_client(),admissions=['999']).status_code,403)
        self.assertEqual(app.test_client().post('/api/login',json={'admission':'052','password':PW}).status_code,200)
        self.assertEqual(self.client.get('/api/me').status_code,200)
    def test_fresh_event_requires_confirmation_and_clears_all_account_data(self):
        team=self.team();self.client.post('/api/notes',json={'body':'Old notes','version':0})
        self.client.post('/api/levels/1/submit',json={'password':'LEVEL-1'})
        admin=self.organizer()
        self.assertEqual(admin.post('/api/admin/fresh-event',json={'confirm':'START FRESH','password':'wrong'}).status_code,403)
        result=admin.post('/api/admin/fresh-event',json={'confirm':'START FRESH','password':os.environ['ORGANIZER_PASSWORD']})
        self.assertEqual(result.status_code,200)
        for table in ['zs_entries','zs_members','zs_sessions','zs_tokens','zs_notes','zs_completions']:
            self.assertEqual(self.count(table),0,table)
        self.assertEqual(self.client.get('/api/me').status_code,401)
        with database() as db:
            audits=db.execute('SELECT action,subject FROM zs_audit').fetchall()
        self.assertEqual([(a['action'],a['subject']) for a in audits],[('fresh-event','')])
        self.assertEqual(self.activate(team['invitations'][0]['token']).status_code,400)
        self.assertFalse(self.client.get('/api/config').json['registration_open'])
        admin.post('/api/admin/registration',json={'open':True})
        self.assertEqual(self.register(app.test_client()).status_code,201)
    def test_export_excludes_authentication_secrets(self):
        self.team();result=self.organizer().get('/api/admin/export')
        self.assertEqual(result.status_code,200)
        text=json.dumps(result.json)
        self.assertNotIn('password_hash',text);self.assertNotIn('token',text);self.assertNotIn(PW,text)
        self.assertEqual(len(result.json['members']),2)
    def test_signing_key_rotation_invalidates_saved_sessions(self):
        self.register();old=os.environ['SIGNING_KEY'];os.environ['SIGNING_KEY']='rotated-'+secrets.token_hex(32)
        try:self.assertEqual(self.client.get('/api/me').status_code,401)
        finally:os.environ['SIGNING_KEY']=old
    def test_all_pages_and_clean_routes_and_private_files(self):
        for route in ['/','/organizer','/mission.css','/zodiac-seeker-brochure.pdf','/initial-evidence-reddit-post.png','/theme-fonts/cinzel-700-900.woff2','/fonts/barlow-condensed.ttf','/archive/document-detail.jpg']:
            response=self.client.get(route);self.assertEqual(response.status_code,200,route);response.close()
        for route in ['/app.py','/schema.sql','/.env.example','/data/local.sqlite3','/START-HERE.md']:
            self.assertEqual(self.client.get(route).status_code,404,route)
        for route in ['/attacks','/attacks.html','/investigate','/next','/later','/level-session.js']:
            self.assertEqual(self.client.get(route).status_code,404,route)
    def test_main_has_no_level_navigation_or_old_local_recovery(self):
        page=(ROOT/'public/play.html').read_text()
        for route in ['attacks.html','investigate.html','next.html','later.html']:
            self.assertNotIn(route,page)
        self.assertNotIn("localStorage.getItem('zodiac_registered')",page)
    def test_preservation_manifest(self):
        manifest=json.loads((ROOT/'preservation-sha256.json').read_text())
        for filename,expected in manifest.items():
            self.assertEqual(hashlib.sha256((ROOT/filename).read_bytes()).hexdigest(),expected,filename)

if __name__=='__main__':unittest.main(verbosity=2)
