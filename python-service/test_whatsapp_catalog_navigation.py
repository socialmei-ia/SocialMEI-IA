"""Synthetic navigation fixtures and disposable PostgreSQL; never provider calls."""
import json,os,time,unittest
from dataclasses import replace
from unittest.mock import patch
from uuid import uuid4
from psycopg.rows import dict_row
import whatsapp_catalog_navigation as nav
import test_whatsapp_bot as bot_fixtures
BOT_ACCOUNT=bot_fixtures.BOT_ACCOUNT
PATH=bot_fixtures.PATH
from test_waha_ingress import gows_list_payload,raw,sign
from waha_ingress import WahaIngressService


class NavigationContracts(unittest.TestCase):
    def test_rollout_configuration_is_explicit_bounded_and_closed(self):
        self.assertEqual(nav.configured_contacts({}),frozenset())
        self.assertEqual(nav.configured_contacts({'SOCIALMEI_MENU_GOWS_LIST_CONTACTS_JSON':'["waha:222@c.us","waha:333@c.us"]'}),
            frozenset({'waha:222@c.us','waha:333@c.us'}))
        for value in ['[]','{}','["*"]','["waha:222@c.us","waha:222@c.us"]','invalid']:
            self.assertEqual(nav.configured_contacts({'SOCIALMEI_MENU_GOWS_LIST_CONTACTS_JSON':value}),frozenset())

    def test_wire_tokens_are_strict_and_titles_fit_lists(self):
        for token in ['sm:'+uuid4().hex+':0','sm:'+uuid4().hex+':9']:
            self.assertTrue(nav.valid_token(token))
        for token in ['sm:1:0','sm:'+uuid4().hex+':10','https://example.test','sm:'+uuid4().hex+':-1']:
            self.assertFalse(nav.valid_token(token))
        state,result=nav.main()
        self.assertEqual(state,'menu');self.assertEqual(len(result['choices']),5)
        self.assertTrue(all(len(c['title'])<=24 and len(c['description'] or '')<=72 for c in result['choices']))
        self.assertNotIn('digite',result['text'].lower())
        rendered=nav.history_text(result)
        self.assertNotIn('sm:',rendered)
        self.assertNotIn('nav -',rendered)


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'),'Disposable PostgreSQL required')
class NavigationDatabaseTests(unittest.TestCase):
    setUpClass=classmethod(bot_fixtures.BotDatabaseTests.setUpClass.__func__)
    setUp=bot_fixtures.BotDatabaseTests.setUp
    register=bot_fixtures.BotDatabaseTests.register
    invited=bot_fixtures.BotDatabaseTests.invited
    login=bot_fixtures.BotDatabaseTests.login
    db=bot_fixtures.BotDatabaseTests.db
    decide=bot_fixtures.BotDatabaseTests.decide
    incoming=bot_fixtures.BotDatabaseTests.incoming

    def add(self,name='Fixture product',category='',kind='Produto',stock=3):
        with self.db() as c:
            return c.execute("INSERT INTO socialmei.crm_produtos(workspace_id,nome,tipo,preco,estoque,minimo,categoria,descricao) "
                "VALUES(%s,%s,%s,12.5,%s,%s,%s,'Descrição de demonstração somente no teste') RETURNING id",
                (self.workspace,name,kind,stock if kind=='Produto' else None,0 if kind=='Produto' else None,category)).fetchone()[0]

    def response(self,target):
        with self.db() as c:
            c.row_factory=dict_row
            return nav.respond(c,self.workspace,target)

    def test_product_details_stock_and_all_handoff_actions_use_real_fixture_values(self):
        pid=self.add()
        state,browse=self.response({'route':'browse','kind':'Produto'})
        product=browse['choices'][0]['target']
        self.assertEqual(product['id'],pid)
        self.assertIn('R$ 12,50',browse['choices'][0]['description'])
        state,detail=self.response(product)
        self.assertIn('Fixture product',detail['text']);self.assertIn('3 un.',detail['text'])
        for choice in detail['choices']:
            state,result=self.response(choice['target'])
            self.assertTrue(result['choices']);self.assertLessEqual(len(result['choices']),10)
            self.assertNotIn('digite',result['text'].lower())
            if choice['target']['route'] in {'human','quote','info'}:
                self.assertEqual(state,'human');self.assertTrue(result['handoff'])
                state,resumed=self.response(result['choices'][0]['target']);self.assertEqual(state,'menu')
        with self.db() as c:c.execute('UPDATE socialmei.crm_produtos SET estoque=0 WHERE id=%s',(pid,))
        self.assertIn('confirme com a equipe',self.response({'route':'stock','id':pid})[1]['text'])

    def test_categories_pagination_new_products_and_inactive_foreign_item(self):
        for i in range(15):self.add('Fixture '+str(i).zfill(2),'Grupo A')
        self.add('Other fixture','Grupo B')
        categories=self.response({'route':'browse','kind':'Produto'})[1]
        self.assertEqual(categories['action'],'categories')
        page=self.response(categories['choices'][0]['target'])[1]
        self.assertEqual(sum(c['target']['route']=='item' for c in page['choices']),6)
        next_choice=next(c for c in page['choices'] if c['title']=='Próxima página')
        second=self.response(next_choice['target'])[1]
        self.assertEqual(sum(c['target']['route']=='item' for c in second['choices']),6)
        self.assertLessEqual(len(second['choices']),10)
        for item in second['choices']:
            self.assertLessEqual(len(item['title']),24);self.assertLessEqual(len(item['description'] or ''),72)
        pid=self.add('AAA new live fixture','Grupo A')
        refreshed=self.response(categories['choices'][0]['target'])[1]
        self.assertEqual(refreshed['choices'][0]['target']['id'],pid)
        with self.db() as c:c.execute("UPDATE socialmei.crm_produtos SET status='Inativo' WHERE id=%s",(pid,))
        self.assertEqual(self.response({'route':'item','id':pid})[1]['action'],'item_unavailable')
        self.assertEqual(self.response({'route':'item','id':999999999})[1]['action'],'item_unavailable')
        scoped=self.add('Scoped active fixture','Grupo A')
        with self.db() as c:
            c.row_factory=dict_row
            self.assertEqual(nav.respond(c,999999,{'route':'item','id':scoped})[1]['action'],'item_unavailable')
        for i in range(8):self.add('Category fixture '+str(i),'Categoria '+str(i))
        categories=self.response({'route':'browse','kind':'Produto'})[1]
        next_category=next(c for c in categories['choices'] if c['title']=='Próxima página')
        following=self.response(next_category['target'])[1]
        self.assertEqual(following['action'],'categories')
        self.assertLessEqual(len(following['choices']),10)

    def test_services_empty_catalog_and_unavailable_data_are_honest(self):
        empty=self.response({'route':'browse','kind':'Serviço'})[1]
        self.assertEqual(empty['action'],'catalog_empty')
        pid=self.add('Fixture service',kind='Serviço')
        service=self.response({'route':'browse','kind':'Serviço'})[1]
        self.assertEqual(service['action'],'services')
        detail=self.response({'route':'item','id':pid})[1]
        self.assertIn('agenda: confirme',detail['text']);self.assertNotIn('Estoque',detail['text'])

    def test_native_snapshot_selection_resolves_once_and_keeps_inbox_label(self):
        pid=self.add();b=replace(self.service.registry['trusted-a'],engine='GOWS')
        self.service=WahaIngressService({'trusted-a':b})
        def incoming(choice,label):
            event=gows_list_payload(choice,mid='false_222@c.us_'+uuid4().hex,me={'id':BOT_ACCOUNT})
            event['payload']['body']=label;event['payload']['timestamp']=int(time.time());event['timestamp']=event['payload']['timestamp']*1000
            data=raw(event);self.assertEqual(self.service.receive('trusted-a',data,sign(data),'sha512')['processed'],1)
            self.assertEqual(self.service.receive('trusted-a',data,sign(data),'sha512')['duplicates'],1)
            return event['payload']['id']
        with patch('whatsapp_bot.native_list_canary',return_value=True):
            menu=self.decide(incoming('1','Ver produtos')).json()
            self.assertEqual(menu['action'],'products')
            def confirm(result,receipt):
                url=PATH+'/decisions/'+result['operation_id']
                claim=self.tech.post(url+'/claim',headers=self.headers,json={}).json()
                self.assertTrue(claim['dispatch_allowed'])
                self.assertEqual(self.tech.post(url+'/receipt',headers=self.headers,json={'status':'confirmed','provider_message_id':receipt}).status_code,200)
                return claim
            claim=confirm(menu,'synthetic-catalog-list')
            token=claim['delivery']['body']['message']['sections'][0]['rows'][0]['rowId']
            self.assertTrue(nav.valid_token(token))
            mid=incoming(token,'Fixture product')
            detail=self.decide(mid).json();self.assertEqual(detail['action'],'product_detail')
            self.assertIn('R$ 12,50',detail['text'])
            self.assertEqual(self.decide(mid).json()['operation_id'],detail['operation_id'])
            detail_claim=confirm(detail,'synthetic-product-detail')
            detail_rows=detail_claim['delivery']['body']['message']['sections'][0]['rows']
            human=self.decide(incoming(detail_rows[3]['rowId'],'Falar com a equipe')).json()
            self.assertTrue(human['handoff'])
            human_claim=confirm(human,'synthetic-human-handoff')
            quiet=self.decide(incoming(detail_rows[0]['rowId'],'Consultar disponibilidade')).json()
            self.assertEqual(quiet['action'],'human_wait')
            self.assertEqual(quiet['status'],'skipped')
            resume=human_claim['delivery']['body']['message']['sections'][0]['rows'][0]['rowId']
            with patch('whatsapp_bot.pending_human_reply', return_value=True):
                blocked=self.decide(incoming(resume,'Retomar automático')).json()
            self.assertEqual(blocked['action'],'human_wait')
            self.assertEqual(blocked['status'],'skipped')
            with self.db() as c:
                self.assertEqual(c.execute('SELECT state FROM socialmei.wa_bot_conversations '
                    'WHERE workspace_id=%s AND conversation_id=%s',
                    (self.workspace,detail['conversation_id'])).fetchone()[0],'human')
            resumed=self.decide(incoming(resume,'Retomar automático')).json()
            self.assertEqual(resumed['action'],'menu')
            with self.db() as c:
                self.assertEqual(c.execute('SELECT text FROM socialmei.me_messages WHERE workspace_id=%s AND external_message_id=%s',(self.workspace,mid)).fetchone()[0],'Fixture product')
                c.row_factory=dict_row
                channel=c.execute('SELECT * FROM socialmei.wa_bot_access WHERE workspace_id=%s AND channel_id=%s',(self.workspace,self.channel)).fetchone()
                self.assertEqual(nav.resolve(c,channel,detail['conversation_id'],token),{'route':'expired'})
                self.assertEqual(nav.resolve(c,{**channel,'workspace_id':999999},detail['conversation_id'],token),{'route':'expired'})
                self.assertEqual(nav.resolve(c,channel,detail['conversation_id'],resume),{'route':'resume'})
                self.assertEqual(nav.resolve(c,{**channel,'binding_hash':'wrong'},detail['conversation_id'],resume),{'route':'expired'})
                self.assertEqual(nav.resolve(c,channel,detail['conversation_id']+1000,resume),{'route':'expired'})
            inbox=self.owner.get('/api/v1/message-enrichment/conversations')
            self.assertEqual(inbox.status_code,200,inbox.text)
            self.assertIn('Fixture product',inbox.text)
            self.assertNotIn('sm:',inbox.text)
            self.assertNotIn('nav -',inbox.text)

    def test_event_accepted_before_catalog_update_is_persisted_after_update(self):
        import importlib.util
        from dataclasses import asdict
        from pathlib import Path
        spec=importlib.util.spec_from_file_location('catalog_source_test',
            Path(__file__).resolve().parents[1]/'tools/gows_catalog_source.py')
        source=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(source)
        now=int(time.time())
        original=replace(self.service.registry['trusted-a'],engine='GOWS',ingress_after=now-60)
        registry=source.catalog_registry_snapshot({'version':1,'bindings':[asdict(original)]})
        binding=type(original)(**registry['bindings'][0])
        event=gows_list_payload('1',mid='false_222@c.us_'+uuid4().hex,me={'id':BOT_ACCOUNT})
        event['payload']['timestamp']=now-30
        event['timestamp']=(now-30)*1000
        body=raw(event)
        # Reproduce the discarded-spool regression from a reset activation cutoff.
        reset=WahaIngressService({'trusted-a':replace(original,ingress_after=now)})
        self.assertEqual(reset.receive('trusted-a',body,sign(body),'sha512')['ignored'],1)
        updated=WahaIngressService({'trusted-a':binding})
        self.assertEqual(updated.receive('trusted-a',body,sign(body),'sha512')['processed'],1)
        self.assertEqual(updated.receive('trusted-a',body,sign(body),'sha512')['duplicates'],1)
        with self.db() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM socialmei.me_messages WHERE '
                'workspace_id=%s AND external_message_id=%s',
                (self.workspace,event['payload']['id'])).fetchone()[0],1)
