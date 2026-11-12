"""SIMULATED PTY input handshake; no serial imports or device access."""
import os,pty,select,subprocess,sys,time,unittest
CHILD='''import sys,select
if not sys.stdin.isatty():
 print("REJECT_NON_INTERACTIVE",flush=True);sys.exit(2)
print("WAITING_NO_MOTION",flush=True)
while True:
 if select.select([sys.stdin],[],[],.1)[0]:
  line=sys.stdin.readline()
  if not line:sys.exit(3)
  if line.strip()=="CONTINUE_1520":
   print("INPUT_ACCEPTED_SIMULATED_ONLY",flush=True);break
'''
class InteractiveInputTests(unittest.TestCase):
 def test_pipe_rejected_before_action(self):
  r=subprocess.run([sys.executable,'-u','-c',CHILD],input='',capture_output=True,text=True)
  self.assertEqual(r.returncode,2);self.assertIn('REJECT_NON_INTERACTIVE',r.stdout)
 def test_pty_waits_for_explicit_input(self):
  try:master,slave=pty.openpty()
  except OSError as exc:self.skipTest(f"PTY unavailable in this sandbox: {exc}")
  p=subprocess.Popen([sys.executable,'-u','-c',CHILD],stdin=slave,stdout=slave,stderr=slave)
  os.close(slave)
  try:
   output=b'';deadline=time.monotonic()+3
   while b'WAITING_NO_MOTION' not in output and time.monotonic()<deadline:
    if select.select([master],[],[],.1)[0]:output+=os.read(master,4096)
   self.assertIn(b'WAITING_NO_MOTION',output)
   time.sleep(.2);self.assertIsNone(p.poll())
   os.write(master,b'CONTINUE_1520\n')
   deadline=time.monotonic()+3
   while b'INPUT_ACCEPTED_SIMULATED_ONLY' not in output and time.monotonic()<deadline:
    if select.select([master],[],[],.1)[0]:
     try:output+=os.read(master,4096)
     except OSError:break
   self.assertIn(b'INPUT_ACCEPTED_SIMULATED_ONLY',output);self.assertEqual(p.wait(timeout=2),0)
  finally:
   if p.poll() is None:p.kill();p.wait()
   os.close(master)
