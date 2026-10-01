from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase
from apps.warehouse.models import Product, ProductComponent
from apps.knowledge.models import KnowledgeItem
from apps.knowledge import catalog, live_catalog
from apps.knowledge.answer import _spec_seller, _spec_funnel

class LiveCatalogTests(TestCase):
    def setUp(self):
        self.p = Product.objects.create(name='Nova Finish', sku='NF-700', price='321.45', unit='л', currency='UAH')
        self.k = Product.objects.create(name='Тестовий набір Nova Finish', price='410.55')
        self.c = ProductComponent.objects.create(bundle=self.k, component=self.p, quantity='0.125')
        self.kb = KnowledgeItem.objects.create(status='approved', kind='fact', title='Nova Finish', text='Сучасний матеріал', audience=['yulia_web'])
        self.kb.products.add(self.p)
    def test_price_changes_visible_with_same_prefetched_knowledge(self):
        item = KnowledgeItem.objects.prefetch_related('products').get(pk=self.kb.pk)
        self.assertIn('321,45 грн/л', catalog.prices_block([item], 'Nova Finish'))
        Product.objects.filter(pk=self.p.pk).update(price='399.99')
        text = catalog.prices_block([item], 'Nova Finish')
        self.assertIn('399,99 грн/л', text)
        self.assertNotIn('321,45', text)
    def test_new_product_found_by_name_and_sku_without_alias_code(self):
        for q in ['Nova Finish', 'Ціна NF-700']:
            self.assertIn(self.p.id, [p.id for p in live_catalog.selected(query=q)])
    def test_bundle_changes_visible_without_kb_republish(self):
        self.assertIn('0,125 л', live_catalog.kits_block())
        replacement = Product.objects.create(name='Nova Primer', unit='кг', price='123.45')
        ProductComponent.objects.filter(pk=self.c.pk).update(component=replacement, quantity='0.333')
        after = live_catalog.kits_block()
        self.assertIn('Nova Primer — 0,333 кг', after)
        self.assertNotIn('0,125 л', after)
    def test_inactive_or_quote_required_product_not_sold_at_old_price(self):
        Product.objects.filter(pk=self.p.pk).update(shop_specs={'price_status':'quote_required'})
        text = catalog.prices_block([self.kb], 'Nova Finish')
        self.assertNotIn('321,45', text)
        self.assertIn('ціну уточнює менеджер', text)
        Product.objects.filter(pk=self.p.pk).update(is_active=False)
        self.assertNotIn(self.p.id, [p.id for p in live_catalog.selected([self.kb], 'Nova Finish')])
    def test_zero_kit_is_not_free_and_missing_composition_not_invented(self):
        Product.objects.create(name='Тестовий набір Empty', price=0)
        text = live_catalog.kits_block()
        self.assertIn('Комплектацію в CRM не заповнено', text)
        self.assertNotIn('— 0 грн', text)
    def test_currency_and_unit_are_preserved(self):
        self.p.price=Decimal('19.99');self.p.currency='EUR';self.p.unit='м';self.p.save()
        self.assertIn('19,99 EUR/м', catalog.render('{price:%s}' % self.p.id))
    def test_seller_next_prompt_gets_new_price(self):
        messages=[{'role':'client','text':'Скільки коштує Nova Finish?'}]
        self.assertIn('321,45 грн/л',_spec_seller('yulia_web',messages,None)['user'])
        Product.objects.filter(pk=self.p.pk).update(price='455.15')
        prompt=_spec_seller('yulia_web',messages,None)['user']
        self.assertIn('455,15 грн/л',prompt)
        self.assertNotIn('321,45',prompt)
    def test_card_worker_cannot_create_parallel_offer(self):
        from apps.crm import agent
        from apps.crm.models import AgentConfig, Funnel, Stage, Deal
        AgentConfig.objects.create(id=1,enabled=True,autonomous=True)
        f=Funnel.objects.create(name='Offline');st=Stage.objects.create(funnel=f,name='New',order=0)
        deal=Deal.objects.create(title='Offline',funnel=f,stage=st)
        response={'content':[{'type':'tool_use','name':'make_offer','input':{'items':[{'name':self.k.name}]}}]}
        with patch.object(agent,'_call',return_value=response), patch('apps.crm.views.make_offer') as offer:
            result=agent.run_agent(deal,'deal')
        offer.assert_not_called()
        self.assertEqual(result['actions'][0]['result']['msg'],'tool not authorized')
        spec=_spec_funnel('funnel_agent',[{'role':'client','text':'Хочу набір'}],None)
        self.assertEqual({t['name'] for t in spec['tools']},{'fill_needs','move_stage','no_action'})

    def test_historical_product_price_is_not_allowed(self):
        self.kb.topic='materials';self.kb.text='Nova Finish — 777 грн';self.kb.save()
        spec=_spec_seller('yulia_web',[{'role':'client','text':'Nova Finish ціна'}],None)
        self.assertNotIn('777 грн',spec['allowed'])
    def test_catalog_change_during_generation_cancels_stale_quote(self):
        from apps.knowledge.answer import answer
        def generated(*args,**kwargs):
            Product.objects.filter(pk=self.p.pk).update(price='500.15')
            return {'content':[{'type':'text','text':'{"reply":"Ціна 321,45 грн/л"}'}]}
        with patch('apps.knowledge.answer.call_claude',side_effect=generated):
            result=answer('yulia_web',[{'role':'client','text':'Nova Finish ціна'}])
        self.assertTrue(result['handoff'])
        self.assertNotIn('321,45',result['text'])
        self.assertNotIn('order',result)
    def test_only_relevant_kits_are_loaded_into_seller_context(self):
        Product.objects.create(name='Тестовий набір Unrelated',price='101')
        self.assertNotIn('Unrelated',live_catalog.kits_block('Nova Finish'))
