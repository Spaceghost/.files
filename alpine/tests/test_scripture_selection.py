import importlib.machinery
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[2]
helper=importlib.machinery.SourceFileLoader('scripture_command_test',str(REPO/'alpine/desktop/.local/bin/oldbook-scripture')).load_module()


class SelectionTests(unittest.TestCase):
    def test_enter_saves_selection_then_requests_immediate_panel_refresh(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'selection.json'
            seen=[]
            def refresh():
                seen.append(json.loads(path.read_text())['reference'])
            with patch.object(helper,'STATE',Path(directory)), patch.object(helper,'SELECTION',path), \
                 patch.object(helper,'refresh_panel',side_effect=refresh,create=True):
                bible=helper.scripture.Bible([{'book':'John','chapter':3,'verse':16,'text':'Selected text'}])
                helper.select_reference(bible,'John 3:16')
            self.assertEqual(seen,['John 3:16'])

    def test_picker_enter_uses_the_chosen_row_reference(self):
        from subprocess import CompletedProcess
        bible=helper.scripture.Bible([{'book':'John','chapter':3,'verse':16,'text':'Selected text'}])
        with patch.object(helper.subprocess,'run',return_value=CompletedProcess([],0,'John 3:16  Selected text\n','')), \
             patch.object(helper,'select_reference',return_value='John 3:16') as selected:
            helper.find(bible)
            selected.assert_called_once_with(bible,'John 3:16')


class LibraryTests(unittest.TestCase):
    def test_talmud_daf_reference_and_optional_collection_prefix(self):
        bible=helper.scripture.Bible([
            {'book':'Talmud Berakhot','chapter':'2a','verse':1,'text':'First segment'},
            {'book':'Talmud Berakhot','chapter':'2a','verse':2,'text':'Second segment'},
            {'book':'Talmud Berakhot','chapter':'2b','verse':1,'text':'Next page'}])
        records=bible.lookup('Berakhot 2a:1-2')
        self.assertEqual(len(records),2)
        self.assertEqual(helper.scripture.format_reference(records),'Talmud Berakhot 2a:1-2')
        self.assertEqual(len(bible.lookup('Talmud Berakhot 2b')),1)

    def test_torah_and_kjv_are_distinct_and_selection_keeps_attribution(self):
        bible=helper.scripture.Bible([
            {'book':'Genesis','chapter':1,'verse':1,'text':'KJV'},
            {'book':'Torah Genesis','chapter':1,'verse':1,'text':'JPS',
             'edition':'JPS 1917','source_url':'https://www.sefaria.org/Genesis.1.1',
             'license':'Public Domain'}])
        self.assertEqual(bible.lookup('Torah Genesis 1:1')[0]['text'],'JPS')
        self.assertEqual(bible.lookup('Bible Genesis 1:1')[0]['text'],'KJV')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'selection.json'
            with patch.object(helper,'STATE',Path(directory)),patch.object(helper,'SELECTION',path),patch.object(helper,'refresh_panel'):
                helper.select_reference(bible,'Torah Genesis 1:1')
            self.assertEqual(json.loads(path.read_text())['edition'],'JPS 1917')

class PickerScopeTests(unittest.TestCase):
    def library(self):
        return helper.scripture.Bible([
            {'book':'John','chapter':1,'verse':1,'text':'Bible match'},
            {'book':'Talmud Berakhot','chapter':'2a','verse':1,'text':'Talmud match'},
            {'book':'Torah Genesis','chapter':1,'verse':1,'text':'Torah match'}])

    def test_default_picker_contains_only_bible_verses(self):
        from subprocess import CompletedProcess
        with patch.object(helper.subprocess,'run',return_value=CompletedProcess([],1,'','')) as run:
            helper.find(self.library())
        rows=run.call_args.kwargs['input']
        self.assertIn('John 1:1',rows)
        self.assertNotIn('Torah',rows)
        self.assertNotIn('Talmud',rows)
        self.assertNotIn('✦',rows)
        self.assertNotIn('⇄',rows)

    def test_all_picker_preserves_lower_priority_for_bible_matches(self):
        from subprocess import CompletedProcess
        with patch.object(helper.subprocess,'run',return_value=CompletedProcess([],1,'','')) as run:
            helper.find(self.library(),include_all=True)
        rows=run.call_args.kwargs['input']
        self.assertLess(rows.index('Torah Genesis'),rows.index('John 1:1'))
        self.assertLess(rows.index('Talmud Berakhot'),rows.index('John 1:1'))
        self.assertLess(rows.index('✦'),rows.index('John 1:1'))
        self.assertIn('--no-sort',run.call_args.args[0])
        self.assertIn('--delayed-filter-ms=0',run.call_args.args[0])

if __name__ == '__main__':
    unittest.main()
