"""Explicit connection for serial-only firmware. Never creates a gripper."""
import json
import math
import time
import uuid
from datetime import datetime, timezone

class CommunicationError(RuntimeError): pass

class JsonlLog:
    def __init__(self, path, run_kind):
        if run_kind not in ('REAL_SERIAL', 'SIMULATED'): raise ValueError('run_kind')
        self.file=open(path,'x',encoding='utf-8');self.kind=run_kind
    def __call__(self, event, **values):
        self.file.write(json.dumps(dict(timestamp_utc=datetime.now(timezone.utc).isoformat(),monotonic_ns=time.monotonic_ns(),run_kind=self.kind,event=event,**values),ensure_ascii=False)+'\n');self.file.flush()
    def close(self): self.file.close()

class SerialClient:
    def __init__(self, config, log, clock=time.monotonic, sleeper=time.sleep):
        self.config=config;self.log=log;self.clock=clock;self.sleeper=sleeper;self.port=None
    def connect(self, path):
        if self.port is not None: raise CommunicationError('already_connected')
        if not path or not path.startswith('/dev/cu.'): raise ValueError('explicit_mac_port_required')
        import serial
        c=self.config
        # Opening CP210x can reset ESP32 even with DTR/RTS deasserted.
        # Wait BEFORE transmitting; a longer response timeout cannot recover
        # a request lost during boot. Keep boot bytes for normal RX logging.
        boot_wait=c.get('boot_wait_s',2.0)
        if type(boot_wait) not in (int,float) or not math.isfinite(boot_wait) or not 0<=boot_wait<=10:
            raise ValueError('invalid_boot_wait_s')
        port=serial.Serial(port=None,baudrate=c['baudrate'],bytesize=c['bytesize'],parity=c['parity'],stopbits=c['stopbits'],timeout=c['read_timeout_s'],write_timeout=c['write_timeout_s'],exclusive=True)
        port.dtr=False;port.rts=False;port.port=path
        try:
            port.open()
            self.log('CONNECTED',path=path)
            self.log('STARTUP_WAIT',seconds=boot_wait,dtr=False,rts=False)
            self.sleeper(boot_wait)
            self.log('STARTUP_READY')
        except BaseException as exc:
            port.close();self.log('CONNECT_ERROR',error=str(exc))
            if not isinstance(exc,Exception):raise
            raise CommunicationError(str(exc)) from exc
        self.port=port
    def close(self):
        if self.port is not None:self.port.close();self.port=None;self.log('CLOSED')
    def request(self, command):
        if command not in ('PING','GET_STATUS','TEST_UNKNOWN'):raise ValueError('no_motion_commands')
        rid=uuid.uuid4().hex
        raw=(json.dumps(dict(protocol_version=1,request_id=rid,command=command))+'\n').encode()
        return self.exchange(raw,rid)
    def exchange(self, raw, request_id):
        if self.port is None:raise CommunicationError('not_connected')
        self.log('TX',raw_hex=raw.hex(),request_id=request_id)
        try:
            if self.port.write(raw)!=len(raw):raise CommunicationError('short_write')
            deadline=self.clock()+self.config['request_timeout_s'];buffer=bytearray();discard=False
            while self.clock()<deadline:
                byte=self.port.read(1)
                if not byte:continue
                if byte!=b'\n':
                    if not discard:buffer.extend(byte)
                    if len(buffer)>self.config['max_response_bytes']:buffer.clear();discard=True
                    continue
                wire=bytes(buffer);buffer.clear()
                if discard:self.log('IGNORED',reason='oversize_response');discard=False;continue
                self.log('RX',raw_hex=wire.hex())
                try:obj=json.loads(wire.decode('utf-8'))
                except (ValueError,UnicodeError):
                    # A long line that starts like a V2 frame but fails JSON is a
                    # corrupted response (e.g. TX-buffer NUL holes), not boot text.
                    # Keep the same resync/timeout behavior but make it auditable.
                    looks_like_frame=wire.startswith(b'{"protocol_version"') and len(wire)>128
                    self.log('IGNORED',reason='corrupt_response' if looks_like_frame else 'boot_or_invalid_json',length=len(wire),nul_count=wire.count(b'\x00'))
                    continue
                if not isinstance(obj,dict) or obj.get('protocol_version')!=1 or obj.get('request_id')!=request_id or obj.get('firmware_version')!=self.config['firmware_version']:
                    self.log('IGNORED',reason='envelope_or_id');continue
                if obj.get('type') not in self.config.get('response_types', ('PONG','STATUS','ERROR')):continue
                self.log('MATCHED',response=obj);return obj
            raise CommunicationError('response_timeout')
        except Exception as exc:
            self.log('COMMUNICATION_ERROR',error=str(exc));self.close()
            if isinstance(exc,CommunicationError):raise
            raise CommunicationError(str(exc)) from exc
