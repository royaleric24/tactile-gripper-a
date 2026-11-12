#include "../../firmware/gripper_control/SafetyCore.h"
#include <cassert>
#include <iostream>
struct Fake:Output{int sets=0,offs=0;bool fail=false;bool set(uint32_t)override{sets++;return !fail;}bool off()override{offs++;return !fail;}};
Limits calibrated(){Limits c;c.enabled=c.calibrated=true;c.low=1000;c.high=2000;c.initial=1400;c.step=20;c.total=50;return c;} // SIMULATED only, not servo limits!
int main(){
 assert(pulseDuty(1500,50,16)==4915);assert(pulseDuty(1000,50,16)==3277);assert(pulseDuty(20000,50,16)==0);
 Fake f;SafetyCore locked(Limits{},f);assert(locked.state==SafetyCore::DISARMED && f.sets==0);
 assert(locked.command("ARM",0,1,true)!=nullptr && f.sets==0);
 assert(locked.command("SET_PULSE_US",1,2,true,1500)!=nullptr && f.sets==0);
 auto c=calibrated();SafetyCore s(c,f);assert(!s.command("ARM",0,1,true));assert(f.sets==0);
 assert(!s.command("SET_PULSE_US",1,2,true,1400));assert(f.sets==1);
 assert(s.command("SET_PULSE_US",2,3,true,1410)!=nullptr && s.state==SafetyCore::FAULT);
 assert(!s.command("STOP",3,0,false));assert(s.state==SafetyCore::FAULT);
 assert(!s.command("DISARM",3,0,false));assert(!s.command("ARM",4,4,true));
 assert(s.command("SET_PULSE_US",5,5,true,2500)!=nullptr);
 SafetyCore initial(c,f);initial.command("ARM",0,1,true);assert(initial.command("SET_PULSE_US",1,2,true,1410));
 SafetyCore timeout(c,f);timeout.command("ARM",0,1,true);timeout.tick(1000);assert(timeout.state==SafetyCore::FAULT);
 SafetyCore lease(c,f);lease.command("ARM",0,1,true);lease.command("SET_PULSE_US",1,2,true,1400);
 for(int i=1;i<5;i++)lease.command("HEARTBEAT",i*400,i+2,true);
 lease.tick(2001);assert(lease.state==SafetyCore::FAULT);
 SafetyCore replay(c,f);replay.command("ARM",0,1,true);assert(replay.command("HEARTBEAT",1,1,true));assert(replay.state==SafetyCore::FAULT);
 SafetyCore step(c,f);step.command("ARM",0,1,true);step.command("SET_PULSE_US",1,2,true,1400);assert(step.command("SET_PULSE_US",101,3,true,1421));
 SafetyCore total(c,f);total.command("ARM",0,1,true);total.command("SET_PULSE_US",1,2,true,1400);total.command("SET_PULSE_US",101,3,true,1420);total.command("SET_PULSE_US",201,4,true,1440);assert(total.command("SET_PULSE_US",301,5,true,1460));
 Fake bad;SafetyCore failure(c,bad);failure.command("ARM",0,1,true);bad.fail=true;failure.command("SET_PULSE_US",1,2,true,1400);assert(failure.outputUnknown && failure.state==SafetyCore::FAULT);
 SafetyCore reboot(c,f);assert(reboot.state==SafetyCore::DISARMED && reboot.target==0);
 std::cout<<"SIMULATED native SafetyCore: PWM rounding, default lock, ARM no output, first pulse, rate, range, step, total, timeout, heartbeat lease, replay, API failure UNKNOWN, reboot passed\n";
}
