import importlib.util
from pathlib import Path
import unittest
import ast
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('easy_forms',ROOT/'helper/easy_forms.py')
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
class Forms(unittest.TestCase):
    def test_valid_product(self):
        self.assertEqual(f.assemble('addproduct',['My course','100','0','-1001234567890']),'My course|100|0|-1001234567890')
    def test_invalid_price_and_channel(self):
        for price in ['0','-1','1.5','100001','1|999']:
            with self.assertRaises(ValueError): f.assemble('addproduct',['Course',price,'30','-1001234567890'])
        with self.assertRaises(ValueError): f.assemble('addproduct',['Course','50','30','123'])
    def test_commission(self):
        with self.assertRaises(ValueError): f.assemble('commission',['80','21'])
        self.assertEqual(f.assemble('commission',['80','20']),'80 20')
    def test_incomplete(self):
        with self.assertRaises(ValueError): f.assemble('addproduct',['Only name'])
    def test_injection(self):
        with self.assertRaises(ValueError): f.assemble('addproduct',['Bad|name','50','30','-1001234567890'])
    def test_campaign(self):
        for url in ['http://example.com','https://','https://user:pass@example.com']:
            with self.assertRaises(ValueError): f.assemble('newcampaign',['Promotion',url,'7'])
        self.assertEqual(f.assemble('newcampaign',['Promotion','https://example.com','7']),'Promotion|https://example.com|7')
    def test_profile_limits(self):
        with self.assertRaises(ValueError): f.assemble('setprofile',['name','x'*65])
    def test_neutral_branding(self):
        self.assertEqual(f.neutralize('push2006 • Digital marketplace'),'Digital marketplace')
        self.assertEqual(f.neutralize('push2006 Business OS'),'')
        self.assertEqual(f.neutralize('  Custom welcome!  '),'  Custom welcome!  ')
    def test_permanent_premium(self):
        self.assertEqual(f.assemble('addpremium',['123','permanent']),'123')
    def test_legacy_routes_resolve(self):
        tree=ast.parse((ROOT/'plugins/easy_ui.py').read_text())
        mapping=next(n.value for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='legacy' for t in n.targets))
        for value in mapping.values:
            module=value.value.id; func=value.attr
            defs={n.name for n in ast.parse((ROOT/f'plugins/{module}.py').read_text()).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
            self.assertIn(func,defs)
    def test_text_update(self):
        self.assertEqual(f.assemble('settext',['START','Hello there']),'START|Hello there')
    def test_coupon_and_review(self):
        key='1234567890abcdef12345678'
        self.assertEqual(f.assemble('createcoupon',['HELLO',key,'1','0']),f'HELLO|{key}|1|0')
        with self.assertRaises(ValueError): f.assemble('review',[key,'6','test'])
    def test_batch_valid(self):
        self.assertEqual(f.assemble('batch',['-100123:5','-100123:104']),'-100123:5 -100123:104')
    def test_batch_invalid(self):
        for last in ['-100456:6','-100123:4','-100123:105','-100123:0']:
            with self.assertRaises(ValueError): f.assemble('batch',['-100123:5',last])
    def test_post_validation(self):
        self.assertEqual(f.assemble('genlink',['-100123:1']),'-100123:1')
        for value in ['100123:1','-100123:2147483648','-100123:0']:
            with self.assertRaises(ValueError): f.assemble('genlink',[value])
    def test_application_role(self):
        self.assertEqual(f.assemble('reviewapplication',['123:seller','approve']),'123 seller approve')
        for value in ['123:owner','0:seller','123:unknown']:
            with self.assertRaises(ValueError): f.assemble('reviewapplication',[value,'approve'])
    def test_pagination(self):
        self.assertEqual(f.page_options(list(range(9))),(list(range(8)),True))
        self.assertEqual(f.page_options(list(range(8))),(list(range(8)),False))
        self.assertEqual(f.page_options([]),([],False))
    def test_readable_labels(self):
        self.assertEqual(f.choice_label('days','0'),'Lifetime')
        self.assertEqual(f.choice_label('stars','100'),'100 Stars')
        self.assertEqual(f.choice_label('percent','15'),'15%')
    def test_channel_links(self):
        self.assertEqual(f.assemble('linkchannel',['1234567890abcdef12345678','-100123']),'1234567890abcdef12345678 -100123')
        with self.assertRaises(ValueError): f.assemble('removedb',['123'])
if __name__=='__main__': unittest.main()
