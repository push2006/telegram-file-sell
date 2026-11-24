import importlib.util
from pathlib import Path
import unittest
p=Path(__file__).resolve().parents[1]/'helper'/'business_rules.py'
s=importlib.util.spec_from_file_location('rules',p)
r=importlib.util.module_from_spec(s); s.loader.exec_module(r)

class Rules(unittest.TestCase):
    def test_one_star_rounding(self):
        self.assertEqual(r.split_stars(1,15,5),{'seller_stars':1,'platform_stars':0,'affiliate_stars':0})
    def test_overallocated_commission(self):
        with self.assertRaises(ValueError): r.split_stars(100,80,21)
    def test_full_commission(self):
        self.assertEqual(r.split_stars(100,100)['seller_stars'],0)
    def test_negative_and_zero(self):
        for args in [(0,10,0),(100,-1,0),(100,10,-1)]:
            with self.assertRaises(ValueError): r.split_stars(*args)
    def test_payment_mismatch(self):
        order={'method':'stars','user_id':42,'amount_cents':100}
        self.assertTrue(r.matches_payment(order,42,100,'XTR'))
        for uid,amount,currency in [(43,100,'XTR'),(42,99,'XTR'),(42,100,'USD')]: self.assertFalse(r.matches_payment(order,uid,amount,currency))
        self.assertFalse(r.matches_payment(None,42,100,'XTR'))
    def test_cross_seller(self):
        self.assertFalse(r.can_manage(10,11,1)); self.assertTrue(r.can_manage(10,10,1)); self.assertTrue(r.can_manage(10,1,1))
    def test_accounting_conservation(self):
        for amount in (1,2,99,100,101,100000):
            for p,a in ((0,0),(15,5),(100,0),(50,50)):
                self.assertEqual(sum(r.split_stars(amount,p,a).values()),amount)

if __name__=='__main__': unittest.main()
