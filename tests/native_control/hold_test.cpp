// SIMULATED actual LEDC adapter; no physical PWM.
#include "../../firmware/gripper_control/gripper_control.ino"
#include <cassert>
#include <iostream>
#include <new>
void reset(){pwm=LedcOutput{};stubDuty=0;pwmCalls=attaches=0;attachFails=writeFails=detachFails=readMismatch=false;testNow=0;setup();safety->~SafetyCore();new(safety) SafetyCore(limits,pwm);setup();assert(CFG_BENCH_HOLD_ENABLED && pwmCalls==0);}
void begin(){assert(!safety->beginBench(0,1,true,true));assert(!safety->command("BENCH_HOLD_MODE",1,2,true));assert(pwmCalls==0);}
void first(){assert(!safety->command("BENCH_HOLD",2,3,true,1500));assert(attaches==1 && safety->holdStarted);}
int main(){
 reset();assert(safety->command("BENCH_HOLD",0,1,true,1500));assert(pwmCalls==0);
 begin();first();safety->tick(502);assert(pwm.attached && stubDuty==4915); // no inherited 500ms stop
 assert(!safety->command("BENCH_HOLD",602,4,true,1550));assert(attaches==1);
 assert(!safety->command("BENCH_HOLD",702,5,true,1550));assert(attaches==1 && safety->holdStart==2);
 for(int t=1000;t<=4000;t+=1000)assert(!safety->command("HEARTBEAT",t,6+t,true));
 safety->tick(5002);assert(safety->state==SafetyCore::DISARMED && !safety->bench && !pwm.attached && stubDuty==0);
 assert(safety->command("BENCH_HOLD",5003,9000,true,1550));assert(attaches==1);
 reset();begin();first();assert(!safety->command("STOP",100,0,false));assert(!pwm.attached && !safety->hold);
 reset();begin();first();safety->fault("TEST_FAULT");assert(safety->state==SafetyCore::FAULT && !pwm.attached && !safety->hold);
 reset();begin();first();safety->tick(5002);assert(!pwm.attached && safety->state==SafetyCore::FAULT); // disconnect
 reset();begin();first();safety->benchWindow=1000;safety->tick(1000);assert(!pwm.attached && safety->state==SafetyCore::FAULT);
 reset();begin();first();assert(!safety->command("DISARM",100,0,false));assert(!pwm.attached);
 reset();begin();assert(safety->command("BENCH_HOLD",2,3,true,400));assert(pwmCalls==0 && safety->state==SafetyCore::FAULT);
 reset();begin();first();writeFails=true;assert(safety->command("BENCH_HOLD",102,4,true,1550));assert(safety->outputUnknown);
 std::cout<<"SIMULATED Hold PASS: no initial output; explicit mode; same/update no attach; fixed 5s lease; heartbeat no renewal; stop/disarm/fault/comm/window; first target; API failure\n";
}
