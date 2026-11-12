// SIMULATED continuous GRIPPER_ASSEMBLED mode; no hardware accessed.
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
static void start(bool assembled){
 assert(!safety->beginBench(0,1,true,!assembled,assembled));
 assert(!safety->command("BENCH_HOLD_MODE",1,2,true));
}
int main(){
 // mechanical: no 5s hold timeout, no 5min window; heartbeat keeps comm alive
 reset();start(true);
 assert(!safety->command("BENCH_HOLD",2,3,true,1500));
 assert(!safety->command("HEARTBEAT",4000,4,true));
 safety->tick(6000);assert(safety->state==SafetyCore::ACTIVE);
 assert(!safety->command("HEARTBEAT",8000,5,true));
 safety->tick(10000);assert(safety->state==SafetyCore::ACTIVE);
 assert(!safety->command("BENCH_HOLD",10000,6,true,1400));assert(safety->state==SafetyCore::ACTIVE);
 assert(!safety->command("HEARTBEAT",14000,7,true));
 safety->tick(16000);assert(safety->state==SafetyCore::ACTIVE);
 safety->tick(20000);assert(safety->state==SafetyCore::FAULT);assert(std::string(safety->reason)=="COMM_TIMEOUT");
 // detached still enforces the fixed 5s hold
 reset();start(false);
 assert(!safety->command("BENCH_HOLD",2,3,true,1500));
 assert(!safety->command("HEARTBEAT",4000,4,true));
 safety->tick(5002);assert(safety->state==SafetyCore::DISARMED);assert(std::string(safety->reason)=="BENCH_HOLD_TIMEOUT");
 std::cout<<"SIMULATED continuous mode PASS: mech holds past 5s with heartbeat; detached still times out at 5s\n";
}
