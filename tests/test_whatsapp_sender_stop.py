import ast
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock


class SenderStopTests(unittest.TestCase):
    def test_idle_sender_is_stopped_without_resuming_another_poll(self):
        source=Path(__file__).resolve().parents[1]/'tools/gows-list-canary.py'
        node=next(x for x in ast.parse(source.read_text(encoding='utf-8-sig')).body
                  if isinstance(x,ast.FunctionDef) and x.name=='stop_sender')
        with tempfile.TemporaryDirectory() as folder:
            state=Path(folder)/'state.json';state.write_text(json.dumps({'in_flight':False}))
            run=Mock();scope=dict(run=run,json=json,statefile=state,WORKER='fixture-worker')
            exec(compile(ast.Module(body=[node],type_ignores=[]),'stop_sender','exec'),scope)
            scope['stop_sender']()
            self.assertEqual([c.args for c in run.call_args_list],[
                ('docker','kill','--signal','STOP','fixture-worker'),
                ('docker','stop','-t','1','fixture-worker')])
