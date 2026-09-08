from pathlib import Path
import runpy
import unittest

MODULE=Path(__file__).resolve().parents[1]/'desktop/.local/lib/mbp_intel/expo.py'


class ExpoTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(MODULE.exists(),'Workspace overview is missing')
        self.api=runpy.run_path(str(MODULE))

    def test_overview_keeps_empty_desktops_and_excludes_scratchpad(self):
        tree={'type':'root','nodes':[
            {'type':'workspace','id':99,'num':-1,'name':'__i3_scratch','nodes':[{'id':7,'app_id':'secret'}]},
            {'type':'workspace','id':5,'num':10,'name':'10: STRATA','rect':{'width':1000,'height':700},
             'nodes':[{'id':8,'app_id':'firefox','name':'Review','rect':{'x':0,'y':0,'width':900,'height':600}}]}]}
        cards=self.api['workspaces'](tree)
        self.assertEqual([c['num'] for c in cards],list(range(1,11)))
        self.assertEqual(cards[9]['name'],'10: STRATA')
        self.assertEqual([w['id'] for c in cards for w in c['windows']],[8])

    def test_empty_strata_is_available_on_ten_and_six_is_ordinary(self):
        cards = self.api['workspaces']({'type': 'root', 'nodes': []})
        self.assertEqual(cards[9]['num'], 10)
        self.assertEqual(cards[9]['name'], '10: Strata')
        self.assertEqual(cards[5]['name'], 'Desktop 6')

    def test_uncreated_workspaces_already_have_their_names_in_the_picker(self):
        cards = self.api['workspaces']({'type': 'root', 'nodes': []})
        self.assertEqual([card['name'] for card in cards[:5]],
                         ['1: Ghost', '2: Orbit', '3: Lab', '4: Signal', '5: Lounge'])
        self.assertEqual(self.api['focus_command']({'num': 4, 'name': 'bad; exit'}),
                         'workspace number "4: Signal"')

    def test_focus_command_uses_numeric_identity_not_untrusted_window_title(self):
        self.assertEqual(self.api['focus_command']({'id':37,'name':'bad; exec nope'}),'[con_id=37] focus')
        self.assertEqual(self.api['focus_command']({'num':10}), 'workspace number "10: Strata"')
        with self.assertRaises(ValueError):self.api['focus_command']({'id':'1; exit'})

    def test_picker_keeps_duplicate_titles_distinct_and_removes_line_breaks(self):
        tree={'type':'workspace','num':1,'name':'1:Work','nodes':[
            {'id':11,'app_id':'foot','name':'Same\ntitle'},
            {'id':12,'app_id':'foot','name':'Same title'}]}
        entries=self.api['menu_entries'](tree)
        windows=[entry for entry in entries if 'id' in entry[1]]
        self.assertEqual([entry[1]['id'] for entry in windows],[11,12])
        self.assertTrue(all('\n' not in entry[0] for entry in entries))
        self.assertEqual(self.api['selected_target']('1',entries)['id'],12)

    def test_cancelled_or_invalid_menu_output_never_selects_a_window(self):
        entries=[('Window',{'id':11})]
        for value in ('','not an index','-1','99'):
            self.assertIsNone(self.api['selected_target'](value,entries))
