// SIMULATED LEDC readback-lag regression; no hardware accessed.
// Models the observed ESP32 behavior: the first attach applies immediately,
// an update's duty_rd still holds the previous target until the next PWM period.
#include "../../firmware/gripper_control/gripper_control.ino"
#include <cassert>
#include <iostream>
#include <new>
#include <string>

static void fresh(){
 pwm=LedcOutput{};stubDuty=0;stubAppliedDuty=0;stubFreq=50;stubFreshAttach=true;
 lagReadback=true;lagNeverLatch=false;readMismatch=false;writeFails=false;attachFails=false;detachFails=false;
 pwmCalls=attaches=0;testNow=0;pwm.benchGate=true;
}
int main(){
 // First attach keeps the original immediate readback: 1500 must pass.
 fresh();
 assert(pwm.set(1500));
 assert(std::string(pwm.lastStage)=="OK");
 assert(pwm.lastFirstWrite);
 // Update 1800: duty_rd still holds the old 4915 until the next PWM period.
 // The firmware must wait ~25ms, then read 5898 and NOT fault.
 assert(pwm.set(1800));
 assert(std::string(pwm.lastStage)=="OK");
 assert(pwm.lastExpectedDuty==pulseDuty(1800,50,16));
 assert(pwm.lastActualDuty==pulseDuty(1800,50,16));
 // Prove the stub really lags: immediate read is old, after delay it is new.
 ledcWrite(CFG_GPIO,pulseDuty(1200,50,16));
 assert(ledcRead(CFG_GPIO)==pulseDuty(1800,50,16));
 delay(25);
 assert(ledcRead(CFG_GPIO)==pulseDuty(1200,50,16));
 // If the delayed readback still fails, FAULT must be retained (no blind retry).
 fresh();lagNeverLatch=true;
 assert(pwm.set(1500));assert(std::string(pwm.lastStage)=="OK");
 assert(!pwm.set(1800));
 assert(std::string(pwm.lastStage)=="READ_MISMATCH");
 std::cout<<"SIMULATED LEDC timing PASS: first readback; update waits one PWM period then reads new duty; persistent mismatch still faults\n";
}
