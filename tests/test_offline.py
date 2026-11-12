"""All fixtures and outcomes are SIMULATED."""
import json, unittest
from pathlib import Path
from gripper_a.gripper_controller import FakeGripper, SerialGripper
from gripper_a.closed_loop import ClosedLoop
from gripper_a.sensor import decode_line

def frame(i=1, score=0):
    return dict(timestamp_ms=i, frame_id=i, material='FABRIC', channels=[0]*16,
                valid_mask=[True]*16, contact_score=score, valid=True, quality_flag='SIM_OK')

class OfflineTests(unittest.TestCase):
    def setUp(self):
        self.config=json.loads(Path('config/simulated.json').read_text())
        self.g=FakeGripper();self.loop=ClosedLoop(self.g,self.config)
    def test_start_no_motion(self):
        self.loop.start(0);self.assertEqual(self.g.events,[])
    def test_contact_and_authorized_release(self):
        self.loop.start(0);self.loop.on_frame(frame(),10);self.loop.on_frame(frame(2,1),20)
        self.assertEqual(self.loop.state,'CONTACT_STOP')
        with self.assertRaises(ValueError):self.loop.release()
        self.loop.release(True);self.assertEqual(self.g.events[-1]['action'],'REQUEST_RELEASE')
        self.assertIsNone(self.g.actual_angle)
        self.assertTrue(all(e['run_kind']=='SIMULATED' and e['executed'] is False for e in self.g.events))
    def test_timeout_latches(self):
        self.loop.start(0);self.loop.tick(100);self.loop.on_frame(frame(),101)
        self.assertEqual(self.loop.state,'FAULT');self.assertEqual(len(self.g.events),1)
    def test_bad_inputs_inhibit(self):
        for key,value in [('channels',[0]*15),('channels',[float('nan')]*16),('valid',False),('valid_mask',[True]*15+[False]),('quality_flag','UNKNOWN'),('frame_id',True)]:
            with self.subTest(key=key,value=str(value)):
                g=FakeGripper();s=ClosedLoop(g,self.config);s.start(0);f=frame();f[key]=value;s.on_frame(f,1)
                self.assertEqual(s.state,'FAULT');self.assertEqual(g.events[0]['action'],'INHIBIT_CLOSING')
    def test_duplicate_frame(self):
        self.loop.start(0);self.loop.on_frame(frame(),1);self.loop.on_frame(frame(),20)
        self.assertEqual(self.loop.state,'FAULT')
    def test_limit(self):
        self.loop.start(0)
        for i in range(1,5):self.loop.on_frame(frame(i),i*10)
        self.assertEqual(self.loop.target,3);self.assertEqual(self.loop.state,'FAULT')
    def test_manual_stop_prevents_motion(self):
        self.loop.start(0);self.loop.stop();self.loop.on_frame(frame(),1)
        self.assertEqual(self.g.events[-1]['action'],'INHIBIT_CLOSING')
    def test_rate_limit(self):
        self.loop.start(0);self.loop.on_frame(frame(),1);self.loop.on_frame(frame(2),2)
        self.assertEqual(self.loop.target,1)
    def test_clock_reversal(self):
        self.loop.start(10);self.loop.tick(9);self.assertEqual(self.loop.state,'FAULT')
    def test_json_framing(self):
        raw=json.dumps(frame()).encode()+b'\n';self.assertEqual(decode_line(raw,4096,['SIM_OK'])['frame_id'],1)
        for invalid in [raw[:-1],b'{"frame_id":1,"frame_id":2}\n',b'\xff\n',b'[]\n']:
            with self.assertRaises(ValueError):decode_line(invalid,4096,['SIM_OK'])
        with self.assertRaises(ValueError):decode_line(raw,5,['SIM_OK'])
    def test_hardware_disabled(self):
        with self.assertRaises(RuntimeError):SerialGripper('/dev/cu.usbserial-EXAMPLE_ESP32')
        with self.assertRaises(ValueError):ClosedLoop(self.g,{**self.config,'run_kind':'REAL'})
    def test_distinct_stop_actions(self):
        self.g.inhibit_closing('test');self.g.hold();self.g.disable_pwm();self.g.release()
        self.assertEqual([e['action'] for e in self.g.events],['INHIBIT_CLOSING','REQUEST_HOLD','DISABLE_PWM','REQUEST_RELEASE'])
