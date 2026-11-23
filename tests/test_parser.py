import unittest
from scripts.fetch_gold import choose_prices,numeric_candidates,clean_digits
class ParserTests(unittest.TestCase):
    def test_arabic_number(self):
        self.assertEqual(numeric_candidates('سعر ٥٬٦٩٩ ج.م'),[5699.0])
    def test_selection(self):
        a={'24':[(1,10,6500,'')],'21':[(1,10,5688,'')],'18':[(1,10,4875,'')],'14':[(1,10,3792,'')]}
        self.assertEqual(choose_prices(a)['21'],5688)
    def test_missing(self):
        with self.assertRaises(ValueError):choose_prices({k:[] for k in ('24','21','18','14')})
if __name__=='__main__':unittest.main()
