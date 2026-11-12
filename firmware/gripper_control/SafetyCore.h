#pragma once
#include <cstdint>
#include <cstring>

#include <cstdlib>
// Board-level PWM timing limits.  The classic ESP32 target uses 16-bit at
// 50 Hz; the ESP32-S3 target uses 14-bit at 50 Hz.  Neither value is hardcoded
// into the control path any more.
inline bool pwmConfigValid(uint32_t hz,uint32_t bits) {
 return hz>0 && hz<=40000 && bits>=8 && bits<=20;
}
struct Limits {
 bool enabled=false, calibrated=false;
 uint32_t hz=50,bits=16,low=0,high=0,initial=0,step=0,total=0,interval=100,timeout=1000,lease=2000;
 bool valid() const {return enabled && calibrated && pwmConfigValid(hz,bits) && low>0 && low<=initial && initial<=high && high<1000000/hz && step>0 && total>0 && interval>0 && timeout>0 && lease>0;}
};
// Rounding uses 2^bits ticks per PWM period, NOT a raw microsecond duty.
inline uint32_t pulseDuty(uint32_t us,uint32_t hz,uint32_t bits) {
 if(!pwmConfigValid(hz,bits) || us>=1000000/hz)return 0;
 uint64_t ticks=(uint64_t(us)*hz*(uint64_t(1)<<bits)+500000)/1000000;
 if(ticks>=(uint64_t(1)<<bits))return 0;
 return (uint32_t)ticks;
}
struct Output {
 virtual bool trialPermit(bool enabled,uint32_t lo,uint32_t hi){return !enabled;}
 virtual bool benchPermit(bool enabled,uint32_t,uint32_t){return !enabled;}
 virtual bool set(uint32_t us)=0;
 virtual bool off()=0;
 virtual ~Output()=default;
};
struct SafetyCore {
 enum State {DISARMED,ARMED,ACTIVE,FAULT};
 bool hold=false,holdCap=false,holdStarted=false;uint32_t holdStart=0,holdLimit=5000;
 bool bench=false,benchCap=false;uint32_t benchLow=500,benchHigh=2500,benchInitial=1500,benchStep=2000,benchWindow=300000,benchPulse=500,benchComm=5000;
 bool mech=false;
 bool hasTarget=false,trial=false, trialCap=false;uint32_t trialStart=0,trialWindow=30000,pulseTime=500,trialComm=5000,trialLow=1460,trialHigh=1540,trialStep=20,trialTotal=80;
 Limits cfg;Output& output;State state=DISARMED;
 const char* reason="BOOT";
 bool outputUnknown=false;uint32_t last=0,started=0,lastSet=0,target=0,total=0,sequence=0;
 SafetyCore(Limits c,Output& o):cfg(c),output(o){}
 const char* name()const{return state==DISARMED?"DISARMED":state==ARMED?"ARMED":state==ACTIVE?"ACTIVE":"FAULT";}
 void fault(const char* why){trial=false;bench=false;hold=false;holdStarted=false;mech=false;output.trialPermit(false,0,0);output.benchPermit(false,0,0);bool ok=output.off();outputUnknown=!ok || !strcmp(why,"OUTPUT_API_FAILURE");state=FAULT;reason=outputUnknown?"OUTPUT_UNKNOWN":why;}
 void tick(uint32_t now){
  if(state!=ARMED && state!=ACTIVE)return;
  if(trial){
   // GRIPPER_ASSEMBLED (mech): keep the last target with no 5s hold and no 5min session limit.
   if(!mech && uint32_t(now-trialStart)>=(bench?benchWindow:trialWindow)){fault(bench?"BENCH_WINDOW_EXPIRED":"TRIAL_WINDOW_EXPIRED");return;}
   if(uint32_t(now-last)>=(bench?benchComm:trialComm)){fault("COMM_TIMEOUT");return;}
   if(bench && hold && holdStarted && !mech && uint32_t(now-holdStart)>=holdLimit){
    trial=false;bench=false;hold=false;holdStarted=false;mech=false;
    output.trialPermit(false,0,0);output.benchPermit(false,0,0);
    if(!output.off()){fault("OUTPUT_UNKNOWN");return;}
    state=DISARMED;target=0;reason="BENCH_HOLD_TIMEOUT";return;
   }
   if(!hold && state==ACTIVE && uint32_t(now-started)>=(bench?benchPulse:pulseTime)){
    if(!output.off()){fault("OUTPUT_UNKNOWN");return;}
    state=ARMED;reason=bench?"BENCH_PULSE_ENDED":"TRIAL_PULSE_ENDED";
   }
   return;
  }
  if(uint32_t(now-last)>=cfg.timeout)fault("COMM_TIMEOUT");
  else if(state==ACTIVE && uint32_t(now-started)>=cfg.lease)fault("OUTPUT_LEASE_EXPIRED");
 }
 const char* beginTrial(uint32_t now,uint32_t seq,bool sessionOk,uint32_t lo,uint32_t hi,uint32_t initial,bool detached,bool localConfirmed){
  tick(now);
  if(state!=DISARMED || outputUnknown)return "NOT_DISARMED";
  if(!trialCap)return "TRIAL_DISABLED";
  if(!sessionOk || seq<=sequence)return "SESSION_OR_REPLAY";
  if(!(detached || localConfirmed))return "PHYSICAL_CONFIRMATION_REQUIRED";
  if(lo<trialLow || hi>trialHigh || lo>hi || initial<lo || initial>hi || (detached && initial!=1500))return "TRIAL_RANGE";
  if(!output.trialPermit(true,lo,hi)){fault("OUTPUT_UNKNOWN");return "OUTPUT_UNKNOWN";}
  hold=false;holdStarted=false;bench=false;trial=true;mech=false;trialStart=now;last=now;sequence=seq;state=ARMED;reason="TRIAL_EXPLICITLY_AUTHORIZED";
  cfg.low=lo;cfg.high=hi;cfg.initial=initial;cfg.step=trialStep;cfg.total=trialTotal;target=initial;total=0;lastSet=0;hasTarget=false;
  return nullptr;
 }
 const char* beginBench(uint32_t now,uint32_t seq,bool sessionOk,bool detached,bool assembled=false){
  tick(now);
  if(state!=DISARMED || outputUnknown)return "NOT_DISARMED";
  if(!benchCap)return "BENCH_DISABLED";
  if(!sessionOk || seq<=sequence)return "SESSION_OR_REPLAY";
  if(!detached && !assembled)return "PHYSICAL_CONDITION_REQUIRED";
  if(!output.benchPermit(true,benchLow,benchHigh)){fault("OUTPUT_UNKNOWN");return "OUTPUT_UNKNOWN";}
  hold=false;holdStarted=false;bench=true;trial=true;mech=assembled;trialStart=now;last=now;sequence=seq;state=ARMED;reason=assembled?"GRIPPER_ASSEMBLED_AUTHORIZED":"BENCH_EXPLICITLY_AUTHORIZED";
  cfg.low=benchLow;cfg.high=benchHigh;cfg.initial=benchInitial;cfg.step=benchStep;
  target=benchInitial;total=0;lastSet=0;hasTarget=false;return nullptr;
 }
 const char* command(const char* cmd,uint32_t now,uint32_t seq,bool sessionOk,uint32_t us=0){
  tick(now);
  if(!strcmp(cmd,"STOP") && state==FAULT){
   bool ok=output.off();outputUnknown=outputUnknown || !ok;return ok?nullptr:"OUTPUT_UNKNOWN";
  }
  if(!strcmp(cmd,"STOP") || !strcmp(cmd,"DISARM")){
   trial=false;bench=false;hold=false;holdStarted=false;mech=false;output.trialPermit(false,0,0);output.benchPermit(false,0,0);
   bool ok=output.off();outputUnknown=!ok;state=ok?DISARMED:FAULT;reason=ok?cmd:"OUTPUT_UNKNOWN";target=0;total=0;
   return ok?nullptr:"OUTPUT_UNKNOWN";
  }
  if(state==FAULT)return reason;
  if(!sessionOk || seq<=sequence){if(state!=DISARMED)fault("SESSION_OR_REPLAY");return "SESSION_OR_REPLAY";}
  if(!strcmp(cmd,"ARM")){
   if(state!=DISARMED)return "ALREADY_ARMED";
   if(!cfg.valid())return "UNCALIBRATED_OR_DISABLED";
   state=ARMED;reason="EXPLICIT_ARM";last=now;sequence=seq;target=cfg.initial;total=0;hasTarget=false;return nullptr;
  }
  if(state!=ARMED && state!=ACTIVE)return "NOT_ARMED";
  if(!strcmp(cmd,"BENCH_HOLD_MODE") || !strcmp(cmd,"BENCH_PULSE_MODE")){
   if(!bench || state!=ARMED || hasTarget)return "MODE_REQUIRES_FRESH_BENCH";
   bool wantHold=!strcmp(cmd,"BENCH_HOLD_MODE");
   if(wantHold && !holdCap)return "BENCH_HOLD_DISABLED";
   hold=wantHold;holdStarted=false;last=now;sequence=seq;reason=hold?"BENCH_HOLD_SELECTED":"BENCH_PULSE_SELECTED";return nullptr;
  }
  if(!strcmp(cmd,"HEARTBEAT")){last=now;sequence=seq;return nullptr;}
  bool trialPulse=trial && !strcmp(cmd,bench?(hold?"BENCH_HOLD":"BENCH_PULSE"):"TRIAL_PULSE");
  if(trial && !trialPulse){fault("TRIAL_COMMAND_REQUIRED");return "TRIAL_COMMAND_REQUIRED";}
  if(!trialPulse && strcmp(cmd,"SET_PULSE_US")){fault("UNKNOWN_COMMAND");return "UNKNOWN_COMMAND";}
  if(trialPulse && state==ACTIVE && !hold){fault("PULSE_RUNNING");return "PULSE_RUNNING";}
  if(us<cfg.low || us>cfg.high){fault("PULSE_LIMIT");return "PULSE_LIMIT";}
  uint32_t delta=us>target?us-target:target-us;
  // Bench manual mode deliberately accepts any legal step and any first target;
  // only Trial keeps the step/total and fixed-initial limits.
  if(!bench && (delta>cfg.step || uint64_t(total)+delta>cfg.total)){fault("STEP_OR_TOTAL_LIMIT");return "STEP_OR_TOTAL_LIMIT";}
  if(!hasTarget && us!=cfg.initial && !bench){fault("INITIAL_PULSE_REQUIRED");return "INITIAL_PULSE_REQUIRED";}
  if(hasTarget && uint32_t(now-lastSet)<cfg.interval){fault("RATE_LIMIT");return "RATE_LIMIT";}
  if(!output.set(us)){fault("OUTPUT_API_FAILURE");return "OUTPUT_API_FAILURE";}
  if(hold && !holdStarted){holdStart=now;holdStarted=true;}
  if(!hold && (trial || state==ARMED))started=now;
  state=ACTIVE;hasTarget=true;target=us;total+=delta;last=now;lastSet=now;sequence=seq;reason="TARGET_COMMANDED";return nullptr;
 }
};
