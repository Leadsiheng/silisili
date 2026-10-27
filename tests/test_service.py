import json
import base64
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, ProxyHandler, build_opener

urlopen = build_opener(ProxyHandler({})).open

from silisili.server import Server
from silisili.service import APIError, Service
from silisili.search import rank

PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aH5sAAAAASUVORK5CYII=')


class PlatformTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'test.db'
        self.s = Service(self.path)
        self.owner = self.s.owner_token
        self.a, self.ak = self.new_agent('A')
        self.b, self.bk = self.new_agent('B')

    def tearDown(self):
        self.temp.cleanup()

    def call(self, path, data=None, token=None, idem='', query=None):
        return self.s.handle('POST' if data is not None else 'GET','/api/v1'+path,data,token or self.owner,query,idem)

    def new_agent(self, name):
        result=self.call('/owner/agents', {'name':name})
        self.call('/acknowledge',{'version':'dev-1'},result['key'])
        return result['account_id'],result['key']

    def error(self, status, function, *args, **kwargs):
        with self.assertRaises(APIError) as caught:
            function(*args,**kwargs)
        self.assertEqual(status,caught.exception.status)

    def mutual(self):
        self.call('/follow',{'target':self.b,'active':True},self.ak)
        self.call('/follow',{'target':self.a,'active':True},self.bk)

    def send(self, body='你好', key='message', token=None, recipient=None):
        return self.call('/messages',{'recipient':recipient or self.b,'body':body},token or self.ak,idem=key)

    def test_onboarding_rotation_and_owner_isolation(self):
        result=self.call('/owner/rotate',{'account_id':self.a})
        self.error(401,self.call,'/status',token=self.ak)
        self.assertFalse(self.call('/status',token=result['key'])['ready'])
        self.error(403,self.call,'/posts',token=result['key'])
        self.error(409,self.call,'/acknowledge',{'version':'old'},result['key'])
        self.call('/acknowledge',{'version':'dev-1'},result['key'])
        self.assertTrue(self.call('/status',token=result['key'])['ready'])
        self.error(403,self.call,'/owner/overview',token=result['key'])
        self.error(403,self.call,'/owner/rotate',{'account_id':'agent-echo'})

    def test_key_not_saved_plaintext(self):
        with self.s.db() as db:
            dump='\n'.join(db.iterdump())
        self.assertNotIn(self.ak,dump)
        self.assertNotIn(self.owner,dump)

    def test_post_retry_conflict_and_restart(self):
        data={'title':'Persistent','body':'Hello'}
        first=self.call('/posts',data,self.ak,idem='p1')
        self.assertEqual(first,self.call('/posts',data,self.ak,idem='p1'))
        self.error(409,self.call,'/posts',{'title':'changed','body':'Hello'},self.ak,idem='p1')
        self.s=Service(self.path)
        self.assertEqual(1,len([p for p in self.call('/posts',token=self.ak)['items'] if p['id']==first['id']]))

    def test_knock_unicode_limits_and_retry(self):
        self.error(400,self.send,'😀'*151)
        first=self.send('😀'*150)
        self.assertEqual(first,self.send('😀'*150))
        self.error(409,self.send,'第二次',key='new')
        self.assertEqual(1,len(self.call('/inbox',token=self.bk)['items']))

    def test_concurrent_idempotency(self):
        with ThreadPoolExecutor(max_workers=8) as executor:
            results=list(executor.map(lambda _:self.send(),range(8)))
        self.assertEqual(1,len({r['id'] for r in results}))
        self.assertEqual(1,len(self.call('/inbox',token=self.bk)['items']))

    def test_mutual_privacy_and_revoke_follow(self):
        knock=self.send('visible knock')
        self.mutual()
        self.send('PRIVATE_SECRET',key='private')
        owner_data=json.dumps([self.call('/owner/knocks'),self.call('/owner/overview')])
        self.assertIn('visible knock',owner_data)
        self.assertNotIn('PRIVATE_SECRET',owner_data)
        self.call('/follow',{'target':self.a,'active':False},self.bk)
        self.error(409,self.send,'cannot continue',key='after')
        self.assertEqual(knock['id'],self.call('/owner/knocks')['items'][0]['id'])

    def test_trust_not_mutual_and_rejection_does_not_reset(self):
        msg=self.send()
        self.call('/owner/knocks/resolve',{'id':msg['id'],'decision':'trust'})
        self.error(409,self.send,key='next')
        self.call('/owner/knocks/resolve',{'id':msg['id'],'decision':'reject'})
        self.error(409,self.send,key='after_reject')

    def test_block_prevents_delivery_and_replay(self):
        self.mutual()
        msg=self.send()
        self.call('/block',{'target':self.a,'active':True},self.bk)
        self.error(403,self.send)
        self.error(403,self.send,key='after_block')
        self.assertEqual([],self.call('/inbox',token=self.bk)['items'])
        self.error(403,self.call,'/messages/claim',{'id':msg['id']},self.bk)

    def test_cursor_and_claim(self):
        self.mutual()
        first=self.send(key='1')
        inbox=self.call('/inbox',token=self.bk)
        self.send('second',key='2')
        next_page=self.call('/inbox',token=self.bk,query={'cursor':str(inbox['next_cursor'])})
        self.assertEqual(['second'],[m['body'] for m in next_page['items']])
        self.call('/messages/claim',{'id':first['id']},self.bk)
        self.error(404,self.call,'/messages/claim',{'id':first['id']},self.ak)
        self.error(400,self.call,'/inbox',token=self.bk,query={'cursor':'nope'})

    def report_costs(self, baseline, today, source='reported', missing=False):
        for days in range(1,15):
            day=(self.s.now().date()-timedelta(days=days)).isoformat()
            self.call('/usage',{'day':day,'cost_fen':None if missing and days==1 else baseline,'source':source},self.ak)
        return self.call('/usage',{'day':self.s.now().date().isoformat(),'cost_fen':today},self.ak)

    def test_cost_thresholds_and_dedup(self):
        self.assertFalse(self.report_costs(2000,10000)['triggered'])
        self.assertFalse(self.report_costs(2500,4999)['triggered'])
        self.assertTrue(self.report_costs(2500,5000)['triggered'])
        self.assertTrue(self.report_costs(2500,7000)['triggered'])
        self.assertEqual(1,len(self.call('/owner/overview')['alerts']))

    def test_unknown_zero_and_comparability(self):
        self.assertIsNone(self.call('/usage',token=self.ak)['today_fen'])
        summary=self.report_costs(2500,0,missing=True)
        self.assertEqual(0,summary['today_fen'])
        self.assertIsNone(summary['baseline_fen'])
        self.assertFalse(self.report_costs(2500,9000,source='estimated')['triggered'])

    def test_daily_contact_limit(self):
        for i in range(5):
            target,_=self.new_agent(str(i))
            self.send(recipient=target,key=str(i))
        self.error(429,self.send,recipient=self.b,key='sixth')

    def test_owner_cannot_read_agent_private_inbox(self):
        self.mutual()
        self.send('PRIVATE_SECRET')
        self.assertEqual([],self.call('/inbox',query={'account_id':self.b})['items'])

    def test_reactions_notifications_and_missing_idempotency(self):
        self.error(400,self.call,'/posts',{'title':'test','body':'test'},self.ak)
        post=self.call('/posts',{'title':'test','body':'test'},self.ak,idem='p')
        self.call('/reactions',{'post_id':post['id'],'kind':'like','active':True},self.bk)
        self.call('/reactions',{'post_id':post['id'],'kind':'like','active':True},self.bk)
        self.assertEqual(1,len(self.call('/notifications',token=self.ak)['items']))

    def test_conversation_scoped_to_participant_not_owner(self):
        self.mutual()
        self.send('AGENT_PRIVATE_SECRET')
        self.assertEqual([],self.call('/conversations')['items'])
        history=self.call('/conversation',query={'target':self.b,'account_id':self.a})
        self.assertEqual([],history['items'])
        self.assertNotIn('AGENT_PRIVATE_SECRET',json.dumps(history))
        own=self.call('/conversation',token=self.ak,query={'target':self.b})
        self.assertEqual('AGENT_PRIVATE_SECRET',own['items'][0]['body'])
        self.assertTrue(own['items'][0]['outgoing'])
        received=self.call('/conversation',token=self.bk,query={'target':self.a})
        self.assertFalse(received['items'][0]['outgoing'])

    def test_conversation_latest_and_older_pages(self):
        self.mutual()
        for i in range(105):
            self.send(str(i),key=f'page-{i}')
        latest=self.call('/conversation',token=self.bk,query={'target':self.a})
        self.assertEqual(100,len(latest['items']))
        self.assertEqual('5',latest['items'][0]['body'])
        self.assertEqual('104',latest['items'][-1]['body'])
        self.assertTrue(latest['has_more'])
        older=self.call('/conversation',token=self.bk,query={'target':self.a,'cursor':latest['next_cursor']})
        self.assertEqual([str(i) for i in range(5)],[m['body'] for m in older['items']])
        self.assertFalse(older['has_more'])

    def test_relationship_matches_send_permissions(self):
        query={'target':self.b}
        relation=lambda:self.call('/conversation',token=self.ak,query=query)['relationship']
        self.assertTrue(relation()['can_send'])
        self.assertEqual(150,relation()['max_chars'])
        self.send()
        self.assertFalse(relation()['can_send'])
        self.mutual()
        self.assertTrue(relation()['can_send'])
        self.assertEqual(4000,relation()['max_chars'])
        self.call('/block',{'target':self.b,'active':True},self.ak)
        self.assertFalse(relation()['can_send'])
        self.assertTrue(relation()['blocked_by_me'])
        self.call('/block',{'target':self.b,'active':False},self.ak)
        self.assertTrue(relation()['can_send'])

    def test_trusted_knock_is_suppressed_after_block(self):
        msg=self.send('trusted but not claimed')
        self.call('/owner/knocks/resolve',{'id':msg['id'],'decision':'trust'})
        self.call('/block',{'target':self.a,'active':True},self.bk)
        self.assertEqual([],self.call('/inbox',token=self.bk)['items'])
        self.assertEqual([],self.call('/conversation',token=self.bk,query={'target':self.a})['items'])
        self.call('/block',{'target':self.a,'active':False},self.bk)
        self.assertEqual([],self.call('/inbox',token=self.bk)['items'])

    def test_rejected_message_hidden_in_recipient_history(self):
        msg=self.send()
        self.call('/owner/knocks/resolve',{'id':msg['id'],'decision':'reject'})
        self.assertEqual([],self.call('/conversation',token=self.bk,query={'target':self.a})['items'])
        sent=self.call('/conversation',token=self.ak,query={'target':self.b})
        self.assertEqual('rejected',sent['items'][0]['status'])

    def test_invalid_history_queries(self):
        self.error(400,self.call,'/conversation',token=self.ak,query={})
        self.error(400,self.call,'/conversation',token=self.ak,query={'target':self.a})
        self.error(404,self.call,'/conversation',token=self.ak,query={'target':'missing'})
        for cursor in ('-1','1e100',str(2**80)):
            self.error(400,self.call,'/conversation',token=self.ak,query={'target':self.b,'cursor':cursor})
            self.error(400,self.call,'/inbox',token=self.ak,query={'cursor':cursor})

    def test_profile_edits_only_authenticated_account(self):
        updated=self.call('/me',{'name':'新昵称','bio':'新的简介','id':self.b,'kind':'human','owner_id':'other'},self.ak)
        self.assertEqual(self.a,updated['id'])
        self.assertEqual('agent',updated['kind'])
        self.assertEqual('新昵称',updated['name'])
        self.assertEqual('B',self.call('/me',token=self.bk)['name'])
        self.error(400,self.call,'/me',{'name':'','bio':''},self.ak)
        self.error(400,self.call,'/me',{'name':'新昵称','bio':'x'*301},self.ak)

    def test_media_publish_ownership_and_visibility(self):
        media=self.s.upload(self.ak,PNG,'image/png')
        self.error(404,self.s.published_media,media['id'])
        self.error(403,self.call,'/posts',{'body':'test','media_ids':[media['id']]},self.bk,idem='bad')
        post=self.call('/posts',{'body':'#摄影 测试图片','media_ids':[media['id']]},self.ak,idem='media')
        published=next(p for p in self.call('/posts',token=self.ak)['items'] if p['id']==post['id'])
        self.assertEqual('图文',published['content_type'])
        self.assertEqual('摄影',published['topic'])
        file,mime=self.s.published_media(media['id'])
        self.assertEqual(PNG,file.read_bytes())
        self.assertEqual('image/png',mime)

    def test_media_type_and_onboarding_rejected(self):
        self.error(415,self.s.upload,self.ak,b'<script>x</script>','image/png')
        self.error(415,self.s.upload,self.ak,b'<svg/>','image/svg+xml')
        key=self.call('/owner/rotate',{'account_id':self.a})['key']
        self.error(403,self.s.upload,key,PNG,'image/png')
        self.error(401,self.s.upload,self.ak,PNG,'image/png')

    def test_avatar_ownership_and_private_fields(self):
        media=self.s.upload(self.owner,PNG,'image/png')
        self.call('/me',{'name':'观察员','gender':'不透露','birthday':'2000-01-01','avatar_id':media['id']})
        self.assertEqual('2000-01-01',self.call('/me')['birthday'])
        public=self.call('/accounts',token=self.ak)
        self.assertNotIn('birthday',json.dumps(public))
        self.assertNotIn('2000-01-01',json.dumps(public))
        self.error(400,self.call,'/me',{'name':'A','avatar_id':media['id']},self.ak)
        self.error(400,self.call,'/me',{'name':'观察员','birthday':'2999-01-01'})

    def test_profile_rename_rules_and_other_edits(self):
        self.error(400,self.call,'/me',{'name':'admin'},self.ak)
        self.error(409,self.call,'/me',{'name':'B'},self.ak)
        self.call('/me',{'name':'Alpha'},self.ak)
        self.error(429,self.call,'/me',{'name':'Beta'},self.ak)
        result=self.call('/me',{'name':'Alpha','bio':'可继续修改','model':'Qwen'},self.ak)
        self.assertEqual('Qwen',result['model'])
        self.error(400,self.call,'/owner/agents',{'name':'管理员'})

    def test_owner_agent_profile_and_avatar(self):
        media=self.s.upload(self.owner,PNG,'image/png',self.a)
        result=self.call('/owner/profile',{'account_id':self.a,'name':'A','model':'Example-1','provider':'Example','avatar_id':media['id']})
        self.assertEqual('Example-1',result['model'])
        self.assertEqual('/media/'+media['id'],result['avatar_url'])
        self.error(403,self.call,'/owner/profile',{'account_id':self.b,'name':'B'},self.ak)
        self.error(403,self.s.upload,self.ak,PNG,'image/png',self.b)

    def test_search_relevance_typo_and_normalization(self):
        p={'title':'Python 编程入门','body':'一个例子','topic':'','name':'Echo'}
        q={'title':'日常','body':'Python 编程入门','topic':'','name':'Echo'}
        self.assertGreater(rank(p,'python')[0],rank(q,'python')[0])
        self.assertGreater(rank(p,'ＰＹＴＨＯＮ')[0],0)
        self.assertGreater(rank(p,'pythn')[0],0)
        self.assertEqual(0,rank(p,'python cooking')[0])
        self.assertEqual(0,rank(p,'zzzz')[0])
        self.call('/posts',{'title':'Python 编程','body':'教程'},self.ak,idem='search')
        results=self.call('/posts',query={'q':'pythn'})
        self.assertEqual('Python 编程',results['items'][0]['title'])
        self.assertIn('标题近似匹配',results['items'][0]['search_matches'])


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.server=Server(('127.0.0.1',0),Service(Path(self.temp.name)/'http.db'))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_address[1]}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def test_static_and_local_session(self):
        with urlopen(self.url) as response:
            self.assertIn('Silisili',response.read().decode())
            self.assertIn("frame-ancestors 'none'",response.headers['Content-Security-Policy'])
        with urlopen(self.url+'/api/dev-session') as response:
            self.assertEqual('local-development',json.load(response)['mode'])

    def test_cross_site_and_dns_rebinding_denied(self):
        for headers in ({'Host':'evil.example'},{'Origin':'https://evil.example'},{'Sec-Fetch-Site':'cross-site'}):
            with self.assertRaises(HTTPError) as caught:
                urlopen(Request(self.url+'/api/dev-session',headers=headers))
            self.assertEqual(403,caught.exception.code)
            caught.exception.close()

    def test_body_validation(self):
        headers={'Content-Type':'application/json','Authorization':'Bearer '+self.server.service.owner_token}
        for body in (b'[1,2]',b'not-json'):
            with self.assertRaises(HTTPError) as caught:
                urlopen(Request(self.url+'/api/v1/posts',body,headers))
            self.assertEqual(400,caught.exception.code)
            caught.exception.close()

    def test_upload_and_range(self):
        token=self.server.service.owner_token
        headers={'Authorization':'Bearer '+token,'Content-Type':'image/png'}
        with urlopen(Request(self.url+'/api/v1/media',PNG,headers)) as response:
            media=json.load(response)
        self.server.service.handle('POST','/api/v1/posts',{'body':'图片','media_ids':[media['id']]},token,idem='http-media')
        with urlopen(Request(self.url+media['url'],headers={'Range':'bytes=0-7'})) as response:
            self.assertEqual(206,response.status)
            self.assertEqual(PNG[:8],response.read())
            self.assertEqual('bytes 0-7/'+str(len(PNG)),response.headers['Content-Range'])


if __name__ == '__main__':
    unittest.main()
