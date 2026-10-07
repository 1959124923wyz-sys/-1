import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from update_prices import extract_price,parse_fang_index,clean_name,gcj02_to_wgs84
class TestParser(unittest.TestCase):
    def test_detail_fang(self):
        p,period=extract_price('<html><body>华润城润府一期 122921元/㎡（09月参考价）</body></html>')
        self.assertEqual(p,122921); self.assertTrue(period.endswith('-09'))
    def test_detail_58(self):
        p,period=extract_price('<p>2026年10月华润城润府一期二手房价格均价117749元/平米</p>')
        self.assertEqual((p,period),(117749,'2026-10'))
    def test_index_and_next(self):
        h='''<html><body><div class="houseList"><dl class="clearfix"><dd><p><a href="/housing/abc">红树西岸</a> 住宅</p><p><a>南山</a> - <a>华侨城</a> 深湾一路3号</p><span>168268 元/㎡</span></dd></dl></div><a href="/housing/page2">下一页</a></body></html>'''
        rows,nxt=parse_fang_index(h,'https://sz.esf.fang.com/housing/')
        self.assertEqual(rows[0]['name'],'红树西岸');self.assertEqual(rows[0]['unit_price'],168268);self.assertTrue(nxt.endswith('/housing/page2'))
    def test_clean_name(self): self.assertEqual(clean_name('华润城·润府（一期）'),'华润城润府1期')
    def test_gcj_to_wgs(self):
        lat,lng=gcj02_to_wgs84(22.741305,113.943976)
        self.assertAlmostEqual(lat,22.744281,places=5); self.assertAlmostEqual(lng,113.939086,places=5)
if __name__=='__main__': unittest.main()
