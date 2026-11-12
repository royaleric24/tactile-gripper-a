#include "../../firmware/gripper_control/gripper_control.ino"
#include <cassert>
#include <iostream>
int main(){
 setup();assert(CFG_TRIAL_ENABLED);assert(pwmCalls==0 && !pwm.trialGate && safety->state==SafetyCore::DISARMED);
 assert(!pwm.set(1500) && pwmCalls==0);
 assert(!safety->beginTrial(1,1,true,1460,1540,1500,true,false));assert(pwmCalls==0);
 // Explicitly inject readback failure; normal stub now follows real zero-duty frequency semantics.
 readMismatch=true;
 assert(safety->command("TRIAL_PULSE",2,2,true,1500));assert(safety->state==SafetyCore::FAULT && safety->outputUnknown && pwm.uncertain);
 assert(safety->command("DISARM",3,0,false));assert(safety->outputUnknown && safety->state==SafetyCore::FAULT);
 std::cout<<"SIMULATED trial adapter PASS: boot no LEDC, no trial gate bypass, BEGIN emits nothing, failed output/close UNKNOWN remains latched across DISARM\n";
}
