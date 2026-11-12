// SIMULATED actual firmware state machine + LEDC adapter for the new Bench range.
// No hardware accessed, no waveform measured.
#include "../../firmware/gripper_control/gripper_control.ino"
#include <cassert>
#include <iostream>
#include <new>
#include <string>

static void reset(){
 pwm=LedcOutput{};stubDuty=0;pwmCalls=attaches=0;
 attachFails=writeFails=detachFails=readMismatch=false;stubFreq=50;testNow=0;
 setup();safety->~SafetyCore();new(safety) SafetyCore(limits,pwm);setup();
}
static void beginHold(){
 assert(!safety->beginBench(0,1,true,true));
 assert(!safety->command("BENCH_HOLD_MODE",1,2,true));
}

int main(){
 // every boundary target accepted as the first target; duty matches quantization
 for(uint32_t us : {500u,1000u,1500u,2000u,2500u}){
   reset();beginHold();
   assert(!safety->command("BENCH_HOLD",2,3,true,us));
   assert(safety->state==SafetyCore::ACTIVE);
   assert(stubDuty==pulseDuty(us,50,16));
 }
 // arbitrary first target far from the old 1500 requirement
 reset();beginHold();assert(!safety->command("BENCH_HOLD",2,3,true,2500));assert(stubDuty==pulseDuty(2500,50,16));
 // no 50us step limit; updates reuse the attached channel
 reset();beginHold();
 assert(!safety->command("BENCH_HOLD",2,3,true,1500));assert(attaches==1);
 assert(!safety->command("BENCH_HOLD",502,4,true,1550));assert(attaches==1);
 assert(!safety->command("BENCH_HOLD",1002,5,true,2000));assert(attaches==1);
 assert(!safety->command("BENCH_HOLD",1502,6,true,500));assert(attaches==1);
 // out-of-range rejected at the firmware boundary, before any output
 reset();beginHold();assert(safety->command("BENCH_HOLD",2,3,true,499));assert(safety->state==SafetyCore::FAULT);
 reset();beginHold();assert(safety->command("BENCH_HOLD",2,3,true,2501));assert(safety->state==SafetyCore::FAULT);
 // independent 100ms rate limit still applies between updates
 reset();beginHold();
 assert(!safety->command("BENCH_HOLD",2,3,true,1500));
 assert(safety->command("BENCH_HOLD",50,4,true,1000));assert(std::string(safety->reason)=="RATE_LIMIT");
 // Stage 0.9B-20B LEDC diagnostics remain on the update path
 reset();beginHold();
 assert(!safety->command("BENCH_HOLD",2,3,true,1500));
 writeFails=true;
 assert(safety->command("BENCH_HOLD",502,4,true,2000));
 assert(std::string(pwm.lastStage)=="WRITE_FAIL");
 std::cout<<"SIMULATED bench range PASS: 500/1000/1500/2000/2500, arbitrary first target, no 50us step, out-of-range, 100ms rate limit, WRITE_FAIL diagnostics\n";
}
