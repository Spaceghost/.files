from pathlib import Path
import runpy
import unittest

MODULE=Path(__file__).resolve().parents[1]/'desktop/.local/lib/oldbook/expo.py'


class ExpoTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(MODULE.exists(),'Workspace overview is missing')
        self.api=runpy.run_path(str(MODULE))

    def test_overview_keeps_empty_desktops_and_excludes_scratchpad(self):
        tree={'type':'root','nodes':[
            {'type':'workspace','id':99,'num':-1,'name':'__i3_scratch','nodes':[{'id':7,'app_id':'secret'}]},
            {'type':'workspace','id':5,'num':6,'name':'6:STRATA','rect':{'width':1000,'height':700},
             'nodes':[{'id':8,'app_id':'firefox','name':'Review','rect':{'x':0,'y':0,'width':900,'height':600}}]}]}
        cards=self.api['workspace_cards'](tree)
        self.assertEqual([c['num'] for c in cards],list(range(1,11)))
        self.assertEqual(cards[5]['name'],'6:STRATA')
        self.assertEqual([w['id'] for c in cards for w in c['windows']],[8])

    def test_focus_command_uses_numeric_identity_not_untrusted_window_title(self):
        self.assertEqual(self.api['focus_command']({'id':37,'name':'bad; exec nope'}),'[con_id=37] focus')
        self.assertEqual(self.api['focus_command']({'num':6}), 'workspace number 6')
        with self.assertRaises(ValueError):self.api['focus_command']({'id':'1; exit'})

    def test_miniature_keeps_floating_windows_inside_card_on_offset_output(self):
        rectangle=self.api['miniature_rect']({'x':1800,'y':-40,'width':600,'height':600},
                                          {'x':1920,'y':0,'width':1000,'height':700},320,160)
        x,y,width,height=rectangle
        self.assertGreaterEqual(x,0);self.assertGreaterEqual(y,0)
        self.assertLessEqual(x+width,320);self.assertLessEqual(y+height,160)
