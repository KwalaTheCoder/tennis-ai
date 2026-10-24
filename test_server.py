import tempfile, unittest
from pathlib import Path
import server

class Tests(unittest.TestCase):
 def setUp(self):
  self.old=server.DB;self.tmp=tempfile.TemporaryDirectory();server.DB=Path(self.tmp.name)/'test.db';server.init_db()
 def tearDown(self):server.DB=self.old;self.tmp.cleanup()
 def test_probabilities_sum(self):
  o=server.predict({});self.assertAlmostEqual(o['player1_win']+o['player2_win'],1,8)
 def test_elo_advantage(self):self.assertGreater(server.predict({'elo1':2000,'elo2':1600})['player1_win'],.7)
 def test_live_lead(self):self.assertGreater(server.predict({'mode':'live','sets1':1,'sets2':0,'games1':5,'games2':1,'best_of':3})['player1_win'],.8)
 def test_finished(self):self.assertGreater(server.predict({'mode':'live','sets1':2,'sets2':0,'best_of':3})['player1_win'],.99)
 def test_winner_from_sets(self):self.assertEqual(server.winner_of({'score':{'sets':[[6,4],[3,6],[6,2]]}}),1)
 def test_settlement_scores_and_updates_elo(self):
  with server.connect() as c:
   cur=c.execute("INSERT INTO predictions(created_at,match_id,mode,player1,player2,p1,p2,model,input_json,surface) VALUES(?,?,?,?,?,?,?,?,?,?)",(server.now(),'m1','prematch','A','B',.7,.3,server.MODEL,'{}','Clay'));pid=cur.lastrowid
  self.assertTrue(server.settle(pid,1))
  with server.connect() as c:r=c.execute('SELECT brier,log_loss,correct FROM predictions WHERE id=?',(pid,)).fetchone();ratings=c.execute('SELECT COUNT(*) FROM ratings').fetchone()[0]
  self.assertAlmostEqual(r['brier'],.09);self.assertEqual(r['correct'],1);self.assertEqual(ratings,2)

if __name__=='__main__':unittest.main()
