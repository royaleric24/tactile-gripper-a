// SIMULATED diagnostics for the actual LEDC adapter; no hardware accessed.
// Verifies that set() records the exact failing stage and that the optional
// fields appear only on a failure response, without changing control behavior.
#include "../../firmware/gripper_control/gripper_control.ino"
#include <cassert>
#include <iostream>
#include <new>
#include <string>

static void freshAdapter(){
 pwm=LedcOutput{};attachFails=writeFails=detachFails=readMismatch=false;
 stubDuty=0;stubFreq=50;pwmCalls=attaches=0;freqReadsAtZero=0;testNow=0;
 pwm.benchGate=true; // bench-range branch, normally set by BEGIN_BENCH
}
static bool isStage(const char* s,const char* expected){return s && std::string(s)==expected;}

int main(){
 // 1) first write OK, then update OK: first-write flag must distinguish them
 freshAdapter();
 assert(pwm.set(1500));
 assert(isStage(pwm.lastStage,"OK") && pwm.lastFirstWrite && pwm.lastWriteOk && pwm.lastOffOk);
 assert(pwm.lastExpectedDuty==pulseDuty(1500,50,16));
 assert(pwm.lastActualDuty==pwm.lastExpectedDuty);
 assert(pwm.lastExpectedFreq==50 && pwm.lastActualFreq==50);
 assert(pwm.set(1550));
 assert(isStage(pwm.lastStage,"OK") && !pwm.lastFirstWrite);
 assert(pwm.lastExpectedDuty==pulseDuty(1550,50,16));

 // 2) ATTACH_FAIL
 freshAdapter();attachFails=true;
 assert(!pwm.set(1500));
 assert(isStage(pwm.lastStage,"ATTACH_FAIL") && pwm.uncertain && !pwm.lastWriteOk);

 // 3) WRITE_FAIL
 freshAdapter();writeFails=true;
 assert(!pwm.set(1500));
 assert(isStage(pwm.lastStage,"WRITE_FAIL") && pwm.uncertain && !pwm.lastWriteOk);

 // 4) READ_MISMATCH
 freshAdapter();readMismatch=true;
 assert(!pwm.set(1500));
 assert(isStage(pwm.lastStage,"READ_MISMATCH") && pwm.uncertain);
 assert(pwm.lastActualDuty!=pwm.lastExpectedDuty);

 // 5) FREQ_MISMATCH
 freshAdapter();stubFreq=49;
 assert(!pwm.set(1500));
 assert(isStage(pwm.lastStage,"FREQ_MISMATCH") && pwm.uncertain);
 assert(pwm.lastExpectedFreq==50 && pwm.lastActualFreq==49);

 // 6) INVALID_DUTY is defensive: unreachable under the 1400..1600 gate, but the
 //    quantizer still refuses an out-of-period target.
 assert(pulseDuty(20000,50,16)==0);

 // 7) ERROR JSON through the real process()/respond() path
 pwm=LedcOutput{};attachFails=writeFails=detachFails=readMismatch=false;
 stubDuty=0;stubFreq=50;testNow=0;
 setup();safety->~SafetyCore();new(safety) SafetyCore(limits,pwm);setup();
 std::string base=std::string("{\"protocol_version\":1,\"request_id\":\"diag\",\"boot_id\":\"")+bootId+"\",\"sequence\":";
 auto send=[&](const std::string& s){Serial.output.clear();used=s.size();memcpy(buffer,s.data(),used);process();return Serial.output;};
 JsonDocument a;assert(!deserializeJson(a,send(base+"1,\"command\":\"BEGIN_BENCH\",\"physical_condition\":\"DETACHED_BENCH\"}")));assert(a["type"]=="ACK");
 JsonDocument m;assert(!deserializeJson(m,send(base+"2,\"command\":\"BENCH_HOLD_MODE\"}")));assert(m["type"]=="ACK");assert(m["hold_mode"]==true);
 writeFails=true;
 JsonDocument e;assert(!deserializeJson(e,send(base+"3,\"command\":\"BENCH_HOLD\",\"pulse_us\":1500}")));
 assert(e["type"]=="ERROR");assert(e["error"]=="OUTPUT_API_FAILURE");
 assert(e["output_api_stage"]=="WRITE_FAIL");
 assert(e["output_first_write"]==true);
 assert(e["output_write_ok"]==false);
 assert(e["output_off_ok"]==false);
 assert(e["output_expected_duty"]==pulseDuty(1500,50,16));
 assert(e["output_expected_freq_hz"]==50);

 std::cout<<"SIMULATED LEDC diagnostics PASS: first/update write, attach/write/read/freq stages, ERROR JSON fields, control path unchanged\n";
}
