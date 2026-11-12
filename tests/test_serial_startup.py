"""SIMULATED open/reset timing and read-only lifecycle regression tests."""
import json
import tempfile
import unittest
import contextlib
import io
import runpy
from pathlib import Path
from unittest.mock import patch
from gripper_a.serial_client import SerialClient, CommunicationError
from gripper_a.gripper_controller import LimitedTrialController
from gripper_a.calibration import CalibrationSession


class StartupPort:
    def __init__(self, **kwargs):
        self.opened = False
        self.closed = False
        self.ready = False
        self.rx = bytearray()
        self.commands = []

    def open(self):
        assert self.dtr is False and self.rts is False
        self.opened = True
        self.rx.extend(b'ets Jun 8 boot text\n')

    def close(self):
        self.closed = True

    def write(self, raw):
        assert self.ready, 'request sent during simulated boot'
        req = json.loads(raw)
        self.commands.append(req['command'])
        response = dict(protocol_version=1, request_id=req['request_id'],
                        type='STATUS' if req['command']=='GET_STATUS' else 'PONG',
                        firmware_version='gripper-control-trial-0.9b2.0', boot_id='SIM_BOOT',
                        state='DISARMED', calibration_state='UNCALIBRATED',
                        hardware_enabled=False, motion_enabled=False,
                        trial_active=False, trial_capable=True,
                        output_state='DISABLED_UNMEASURED')
        self.rx.extend(json.dumps(response).encode()+b'\n')
        return len(raw)

    def read(self, n):
        return bytes([self.rx.pop(0)]) if self.rx else b''


class StartupTests(unittest.TestCase):
    def setUp(self):
        self.config=json.loads(Path('config/gripper_trial.json').read_text())['serial']
        self.events=[]
        self.port=StartupPort()
        self.waits=[]

    def wait(self, seconds):
        self.assertTrue(self.port.opened)
        self.assertEqual(self.port.commands, [])
        self.waits.append(seconds)
        self.port.ready=True

    def client(self, sleeper=None):
        return SerialClient(self.config, lambda e, **v:self.events.append((e,v)), sleeper=sleeper or self.wait)

    def test_first_request_waits_and_boot_text_is_not_response(self):
        c=self.client()
        with patch('serial.Serial', return_value=self.port):
            c.connect('/dev/cu.SIMULATED')
            self.assertEqual(c.request('GET_STATUS')['state'],'DISARMED')
            c.close()
        self.assertEqual(self.waits,[2.0])
        self.assertEqual(self.port.commands,['GET_STATUS'])
        self.assertTrue(self.port.closed)
        self.assertTrue(any(e=='IGNORED' and v.get('reason')=='boot_or_invalid_json' for e,v in self.events))

    def test_configured_wait(self):
        self.config['boot_wait_s']=1.25
        c=self.client()
        with patch('serial.Serial', return_value=self.port):c.connect('/dev/cu.SIMULATED');c.close()
        self.assertEqual(self.waits,[1.25])

    def test_open_error_closes_without_retry(self):
        c=self.client()
        with patch('serial.Serial', return_value=self.port), patch.object(self.port,'open',side_effect=OSError('busy')) as opened:
            with self.assertRaises(CommunicationError):c.connect('/dev/cu.SIMULATED')
        self.assertTrue(self.port.closed);self.assertIsNone(c.port);opened.assert_called_once()

    def test_wait_error_closes(self):
        def broken_wait(seconds):raise OSError('interrupted')
        c=self.client(broken_wait)
        with patch('serial.Serial',return_value=self.port):
            with self.assertRaises(CommunicationError):c.connect('/dev/cu.SIMULATED')
        self.assertTrue(self.port.closed);self.assertIsNone(c.port)

    def test_invalid_wait_never_opens(self):
        for value in (-1, float('nan'), 11, True):
            self.config['boot_wait_s']=value
            with patch('serial.Serial') as serial:
                with self.assertRaises(ValueError):self.client().connect('/dev/cu.SIMULATED')
                serial.assert_not_called()

    def test_interrupt_during_boot_wait_closes(self):
        def interrupted(seconds):raise KeyboardInterrupt()
        c=self.client(interrupted)
        with patch('serial.Serial',return_value=self.port):
            with self.assertRaises(KeyboardInterrupt):c.connect('/dev/cu.SIMULATED')
        self.assertTrue(self.port.closed);self.assertIsNone(c.port)

    def test_real_mode_readonly_lifecycle_only_queries(self):
        # Real-mode code path, all I/O replaced with an in-memory simulated port.
        with tempfile.TemporaryDirectory() as tmp:
            g=LimitedTrialController(dry_run=False,hardware_permission=True,log_path=Path(tmp)/'transport.jsonl')
            s=CalibrationSession(g,Path(tmp)/'session')
            with patch('serial.Serial',return_value=self.port), patch('gripper_a.serial_client.time.sleep',side_effect=self.wait):
                # Constructor default sleeper is bound at import; inject explicitly.
                factory=SerialClient
                with patch('gripper_a.serial_client.SerialClient',side_effect=lambda c,l:factory(c,l,sleeper=self.wait)):
                    s.connect('/dev/cu.SIMULATED');s.status();s.stop();s.close()
            self.assertEqual(self.port.commands,['GET_STATUS','GET_STATUS'])
            self.assertTrue(self.port.closed);self.assertFalse(g.connected)

    def test_unlocked_initial_status_closes_without_disarm(self):
        with tempfile.TemporaryDirectory() as tmp:
            g=LimitedTrialController(log_path=Path(tmp)/'log.jsonl')
            with patch.object(g,'get_status',side_effect=lambda:setattr(g,'state','ACTIVE')):
                with self.assertRaisesRegex(RuntimeError,'device_not_disarmed'):g.connect()
            self.assertFalse(g.connected)
            self.assertEqual(g.fake.events,[])
            g.close()

    def test_exact_real_cli_start_status_quit_sends_only_queries(self):
        # Execute the full command-line entry point, with serial I/O simulated.
        with tempfile.TemporaryDirectory() as tmp:
            args=['scripts/calibrate_gripper.py','--real','--port','/dev/cu.SIMULATED',
                  '--hardware-permission','--output',str(Path(tmp)/'session')]
            with patch('sys.argv',args), patch('sys.stdin',io.StringIO('status\nquit\n')), \
                 patch('select.select',return_value=([True],[],[])), \
                 patch('serial.Serial',return_value=self.port), \
                 patch('gripper_a.serial_client.SerialClient',side_effect=lambda c,l:SerialClient(c,l,sleeper=self.wait)), \
                 contextlib.redirect_stdout(io.StringIO()):
                runpy.run_path('scripts/calibrate_gripper.py',run_name='__main__')
            self.assertEqual(self.port.commands,['GET_STATUS','GET_STATUS'])
            self.assertTrue(self.port.closed)
