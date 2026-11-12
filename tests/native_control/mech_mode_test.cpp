// SIMULATED mechanical-assembly mode; no hardware accessed.
// GRIPPER_ASSEMBLED is a separate explicit condition; the DETACHED/neither
// checks are not bypassed, and the existing 5s Hold / no-step path is reused.
#include "../../firmware/gripper_control/gripper_control.ino"
#include <cassert>
#include <iostream>
#include <new>
#include <string>

static void reset(){
 pwm=LedcOutput{};stubDuty=0;stubAppliedDuty=0;stubFreq=50;stubFreshAttach=true;
 lagReadback=false;lagNeverLatch=false;readMismatch=false;writeFails=false;attachFails=false;detachFails=false;
 pwmCalls=attaches=0;testNow=0;
 setup();safety->~SafetyCore();new(safety) SafetyCore(limits,pwm);setup();
}
int main(){
 // neither condition is refused
 reset();assert(safety->beginBench(0,1,true,false,false));assert(safety->state==SafetyCore::DISARMED);
 // assembled condition is an explicit, separate path
 reset();assert(!safety->beginBench(0,1,true,false,true));
 assert(safety->state==SafetyCore::ARMED && safety->mech && safety->bench);
 // same 5s Hold / no-step / LEDC path as detached bench
 assert(!safety->command("BENCH_HOLD_MODE",1,2,true));
 assert(!safety->command("BENCH_HOLD",2,3,true,1500));
 assert(safety->state==SafetyCore::ACTIVE && stubDuty==pulseDuty(1500,50,16));
 assert(!safety->command("BENCH_HOLD",702,4,true,1650));
 assert(safety->state==SafetyCore::ACTIVE && stubDuty==pulseDuty(1650,50,16));
 // STOP clears the mechanical flag and disarms
 assert(!safety->command("STOP",1502,0,false));
 assert(safety->state==SafetyCore::DISARMED && !safety->mech && !safety->bench);
 // real JSON path: BEGIN_BENCH with GRIPPER_ASSEMBLED is acknowledged
 reset();
 std::string base=std::string("{\"protocol_version\":1,\"request_id\":\"mech\",\"boot_id\":\"")+bootId+"\",\"sequence\":";
 auto send=[&](const std::string& s){Serial.output.clear();used=s.size();memcpy(buffer,s.data(),used);process();return Serial.output;};
 JsonDocument a;assert(!deserializeJson(a,send(base+"1,\"command\":\"BEGIN_BENCH\",\"physical_condition\":\"GRIPPER_ASSEMBLED\"}")));
 assert(a["type"]=="ACK");assert(a["mechanical_assembly"]==true);assert(a["bench_active"]==true);
 JsonDocument m;assert(!deserializeJson(m,send(base+"2,\"command\":\"BENCH_HOLD_MODE\"}")));assert(m["type"]=="ACK");
 JsonDocument h;assert(!deserializeJson(h,send(base+"3,\"command\":\"BENCH_HOLD\",\"pulse_us\":1500}")));assert(h["type"]=="ACK");assert(h["commanded_pulse_us"]==1500);
 std::cout<<"SIMULATED mechanical mode PASS: GRIPPER_ASSEMBLED accepted, neither-condition refused, 1500/1650, JSON ACK, STOP clears\n";
}
