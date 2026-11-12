// SIMULATED actual firmware adapter; no hardware accessed or waveform measured.
#include "../../firmware/gripper_control/gripper_control.ino"
#include <cassert>
#include <iostream>
#include <new>
void reset(){
 pwm=LedcOutput{};attachFails=writeFails=detachFails=readMismatch=false;
 stubDuty=0;stubFreq=50;attaches=freqReadsAtZero=pwmCalls=0;testNow=0;
 // A native setup() call does not reset static RAM as an ESP32 reboot does.
 setup();safety->~SafetyCore();new(safety) SafetyCore(limits,pwm);setup();
 assert(CFG_TRIAL_ENABLED && pwmCalls==0);
 assert(safety->state==SafetyCore::DISARMED && !pwm.trialGate);
}
void begin(){assert(!safety->beginTrial(1,1,true,1500,1500,1500,true,false));assert(pwmCalls==0);}
void pulse(){assert(!safety->command("TRIAL_PULSE",2,2,true,1500));}
void failedPulse(){assert(safety->command("TRIAL_PULSE",2,2,true,1500));assert(safety->state==SafetyCore::FAULT && safety->outputUnknown && pwm.uncertain);}
int main(){
 reset();assert(!pwm.set(1500) && pwmCalls==0);loop();assert(pwmCalls==0);
 assert(safety->command("TRIAL_PULSE",0,1,true,1500));assert(pwmCalls==0);
 reset();begin();assert(ledcReadFreq(CFG_GPIO)==0);freqReadsAtZero=0;
 pulse();assert(stubDuty==pulseDuty(1500,50,16));assert(freqReadsAtZero==0 && attaches==1);
 safety->tick(502);assert(stubDuty==0 && !pwm.attached && safety->state==SafetyCore::ARMED);
 assert(!safety->command("TRIAL_PULSE",602,3,true,1500));assert(attaches==2 && freqReadsAtZero==0);
 assert(!safety->command("STOP",603,0,false));assert(stubDuty==0 && !pwm.attached && !pwm.trialGate);
 assert(!safety->command("DISARM",604,0,false));assert(!pwm.set(1500));
 reset();begin();attachFails=true;failedPulse();assert(stubDuty==0);
 reset();begin();writeFails=true;failedPulse();
 reset();begin();readMismatch=true;failedPulse();
 reset();begin();stubFreq=49;failedPulse();assert(stubDuty==0 && !pwm.attached);
 assert(safety->command("DISARM",3,0,false));assert(safety->state==SafetyCore::FAULT && safety->outputUnknown);
 reset();begin();pulse();detachFails=true;
 assert(safety->command("STOP",3,0,false));assert(safety->state==SafetyCore::FAULT && safety->outputUnknown);
 reset();begin();pulse();safety->tick(5002);assert(safety->state==SafetyCore::FAULT && stubDuty==0 && !pwm.trialGate);
 reset();assert(stubDuty==0 && pwmCalls==0);
 std::cout<<"SIMULATED LEDC regression PASS: zero-duty initialization; authorized write/frequency readback; attach/write/read/frequency/detach failures; no startup/unauthorized output; timed off; repeated attach; STOP/DISARM/FAULT/UNKNOWN; timeout/restart\n";
}
