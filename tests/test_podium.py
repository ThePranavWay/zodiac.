"""Four-level podium regressions. Uses the isolated database selected by test_app."""
import concurrent.futures
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import test_app as base
from app import app,COOKIE
from storage import database,initialize

class PodiumTests(unittest.TestCase):
    def setUp(self):
        base.EventTests.setUp(self)
    def register(self,admission='052',client=None,kind='solo',admissions=None):
        client=client or self.client
        result=base.EventTests.register(self,client=client,kind=kind,admissions=admissions or [admission])
        self.assertEqual(result.status_code,201,result.json)
        return result.json
    def member(self,*args,**kwargs):return base.EventTests.member(self,*args,**kwargs)
    def finish(self,client=None,levels=(1,2,3,4)):
        client=client or self.client
        for level in levels:
            result=client.post(f'/api/levels/{level}/submit',json={'password':f'LEVEL-{level}'})
            self.assertEqual(result.status_code,200,result.json)
        return result.json
    def organizer(self):return base.EventTests.organizer(self)
    def count(self,table):return base.EventTests.count(self,table)
    def test_four_only_version_and_no_advanced_routes(self):
        self.assertEqual(self.client.get('/api/config').json['version'],4)
        for path in ['/casework','/casework/5','/dispatch','/casework.html','/advanced.py']:
            self.assertEqual(self.client.get(path).status_code,404,path)
        self.register()
        self.assertEqual(self.client.post('/api/levels/5/submit',json={'password':'x'}).status_code,404)
    def test_partial_and_wrong_fourth_do_not_stop_clock(self):
        self.register();self.finish(levels=(1,2,3))
        self.assertIsNone(self.client.get('/api/me').json['finish'])
        self.assertEqual(self.client.post('/api/levels/4/submit',json={'password':'wrong'}).status_code,400)
        self.assertEqual(self.count('zs_finishes'),0)
    def test_fourth_stops_clock_and_repeat_is_idempotent(self):
        self.register();result=self.finish();first=result['finish']
        self.assertEqual(first['podium_place'],1)
        self.assertGreaterEqual(first['elapsed_seconds'],0)
        self.assertEqual(self.finish()['finish'],first)
        self.assertEqual(self.client.get('/api/progress').json['finish'],first)
        with patch('app.time.time',return_value=first['finished_at']+86400):
            self.assertEqual(self.client.get('/api/me').json['finish'],first)
            self.assertEqual(self.client.get('/api/leaderboard').json['entries'][0]['finish'],first)
        self.assertEqual(self.count('zs_finishes'),1)
    def test_only_first_three_of_five_have_podium_places(self):
        clients=[]
        for i in range(5):
            c=app.test_client();self.register(str(100+i),c);clients.append(c)
            result=self.finish(c)
            self.assertEqual(result['finish']['podium_place'],i+1 if i<3 else None)
        board=clients[0].get('/api/leaderboard').json
        self.assertEqual(len(board['podium']),3)
        self.assertEqual([r['podium_place'] for r in board['podium']],[1,2,3])
        self.assertEqual(self.count('zs_finishes'),5)
        self.assertTrue(all(r['finish'] is not None for r in board['entries']))
        self.assertNotIn('admission',json.dumps(board))
    def test_finish_order_is_not_registration_order_or_fastest_duration(self):
        old=self.register();newclient=app.test_client();new=self.register('053',newclient)
        with database() as db:db.execute('UPDATE zs_entries SET started=started-3600 WHERE id=?',(old['entry']['id'],))
        self.finish();self.finish(newclient)
        board=newclient.get('/api/leaderboard').json
        self.assertEqual([r['id'] for r in board['podium']],[old['entry']['id'],new['entry']['id']])
        self.assertGreater(board['podium'][0]['elapsed_seconds'],board['podium'][1]['elapsed_seconds'])
    def test_later_registered_can_finish_first_and_pending_stays_unranked(self):
        old=self.register();newc=app.test_client();new=self.register('053',newc);self.finish(newc)
        board=self.client.get('/api/leaderboard').json
        self.assertEqual(board['entries'][0]['id'],new['entry']['id'])
        self.assertIsNone(board['entries'][1]['finish']);self.assertEqual(len(board['podium']),1)
    def test_team_has_one_finish_shared_with_every_member(self):
        result=self.register(kind='team',admissions=['052','053'])
        other=app.test_client();token=result['invitations'][0]['token']
        self.assertEqual(other.post('/api/token/complete',json={'token':token,'password':base.PW}).status_code,200)
        self.finish(levels=(1,2));self.finish(other,levels=(3,4))
        self.assertEqual(self.count('zs_finishes'),1)
        self.assertEqual(self.client.get('/api/me').json['finish'],other.get('/api/me').json['finish'])
        self.assertEqual(len(other.get('/api/leaderboard').json['podium']),1)
    def test_parallel_duplicate_last_answer_creates_one_finish(self):
        self.register();self.finish(levels=(1,2,3));cookie=self.client.get_cookie(COOKIE).value
        def submit(_):
            c=app.test_client();c.set_cookie(COOKIE,cookie)
            return c.post('/api/levels/4/submit',json={'password':'LEVEL-4'}).json
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(submit,range(4)))
        self.assertEqual(self.count('zs_finishes'),1)
        self.assertTrue(all(r['finish']['podium_place']==1 for r in results))
        self.assertEqual(sum(not r['already_completed'] for r in results),1)
    def test_parallel_different_finishers_get_distinct_places_only_three(self):
        cookies=[]
        for i in range(4):
            c=app.test_client();self.register(str(100+i),c);self.finish(c,levels=(1,2,3));cookies.append(c.get_cookie(COOKIE).value)
        def submit(cookie):
            c=app.test_client();c.set_cookie(COOKIE,cookie)
            response=c.post('/api/levels/4/submit',json={'password':'LEVEL-4'})
            self.assertEqual(response.status_code,200,response.json);return response.json
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(submit,cookies))
        self.assertEqual(sorted(r['finish']['podium_place'] for r in results if r['finish']['podium_place'] is not None),[1,2,3])
        with database() as db:self.assertEqual([r['finish_order'] for r in db.execute('SELECT finish_order FROM zs_finishes ORDER BY finish_order').fetchall()],[1,2,3,4])
    def test_client_cannot_supply_time_or_place(self):
        self.register();self.finish(levels=(1,2,3))
        for field,value in [('finished_at',0),('podium_place',1),('elapsed_seconds',0)]:
            response=self.client.post('/api/levels/4/submit',json={'password':'LEVEL-4',field:value})
            self.assertEqual(response.status_code,400)
        self.assertEqual(self.count('zs_finishes'),0)
    def test_new_device_and_recovery_preserve_frozen_finish(self):
        self.register();first=self.finish()['finish'];other=app.test_client()
        self.assertEqual(other.post('/api/login',json={'admission':'052','password':base.PW}).status_code,200)
        self.assertEqual(other.get('/api/me').json['finish'],first)
        token=self.organizer().post('/api/admin/reset-password',json={'admission':'052'}).json['token']
        recovered=app.test_client();self.assertEqual(recovered.post('/api/token/complete',json={'token':token,'password':base.PW+'-new'}).status_code,200)
        self.assertEqual(recovered.get('/api/me').json['finish'],first)
    def test_fresh_reset_clears_podium_export_preserves_finish_records(self):
        self.register();self.finish();admin=self.organizer();export=admin.get('/api/admin/export').json
        self.assertEqual(len(export['finishes']),1);self.assertEqual(export['finishes'][0]['finish_order'],1)
        self.assertNotIn('password_hash',json.dumps(export))
        response=admin.post('/api/admin/fresh-event',json={'confirm':'START FRESH','password':os.environ['ORGANIZER_PASSWORD']})
        self.assertEqual(response.status_code,200);self.assertEqual(self.count('zs_finishes'),0)
        admin.post('/api/admin/registration',json={'open':True});self.register();self.assertEqual(self.finish()['finish']['podium_place'],1)
    def test_legacy_completed_entries_are_backfilled_once_in_finish_order(self):
        old=self.register();other=app.test_client();new=self.register('053',other)
        with database() as db:
            for eid,end in [(old['entry']['id'],200),(new['entry']['id'],100)]:
                for level in range(1,5):db.execute('INSERT INTO zs_completions VALUES(?,?,?)',(eid,level,end))
        initialize();initialize()
        board=self.client.get('/api/leaderboard').json
        self.assertEqual([r['id'] for r in board['podium']],[new['entry']['id'],old['entry']['id']])
        self.assertEqual(self.count('zs_finishes'),2)
    def test_repeated_migration_preserves_assigned_places(self):
        self.register();self.finish();before=self.client.get('/api/me').json['finish'];initialize();initialize()
        self.assertEqual(self.client.get('/api/me').json['finish'],before)
        third=app.test_client();self.register('054',third);self.assertEqual(self.finish(third)['finish']['podium_place'],2)
    def test_level_files_removed_and_main_has_no_advanced_links(self):
        root=Path(__file__).resolve().parents[1]
        # Level HTML files were removed per the organizer's Oct 2026 update.
        for name in ['attacks','investigate','next','later']:
            self.assertFalse((root/'public'/f'{name}.html').exists(),name)
        self.assertFalse((root/'public/level-session.js').exists())
        index=(root/'public/play.html').read_text();self.assertNotIn('/casework',index);self.assertNotIn('/dispatch',index)
        self.assertIn('podium-list',index)

    def test_organizer_can_see_only_three_podium_awards(self):
        for i in range(4):
            c=app.test_client();self.register(str(200+i),c);self.finish(c)
        result=self.organizer().get('/api/admin/state').json
        self.assertEqual([w['podium_place'] for w in result['podium']],[1,2,3])
        self.assertEqual(result['counts']['entries'],4)
