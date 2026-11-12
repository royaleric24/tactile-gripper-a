#include "../../firmware/gripper_control/SafetyCore.h"
#include <cassert>
#include <string>

#include <iostream>
struct Fake:Output{bool gate=false,fail=false;int sets=0;bool trialPermit(bool v,uint32_t,uint32_t)override{gate=v;return true;}bool set(uint32_t)override{++sets;return gate&&!fail;}bool off()override{return !fail;}};
void begin(SafetyCore& c){c.trialCap=true;assert(!c.beginTrial(1,1,true,1460,1540,1500,true,false));}
int main(){
 Fake f;SafetyCore s(Limits{},f);
 assert(s.beginTrial(0,1,true,1460,1540,1500,true,false));assert(f.sets==0);
 s.trialCap=true;assert(s.beginTrial(0,1,true,1460,1540,1500,false,false));assert(s.beginTrial(0,1,false,1460,1540,1500,true,false));
 assert(s.beginTrial(0,1,true,500,2500,1500,true,false));begin(s);assert(s.state==SafetyCore::ARMED && f.sets==0);
 assert(!s.command("TRIAL_PULSE",2,2,true,1500));assert(f.sets==1);
 s.tick(502);assert(s.state==SafetyCore::ARMED && s.reason==std::string("TRIAL_PULSE_ENDED"));
 assert(!s.command("TRIAL_PULSE",602,3,true,1520));s.tick(1102);
 assert(s.command("TRIAL_PULSE",1202,4,true,1541));assert(s.state==SafetyCore::FAULT && !f.gate);
 SafetyCore a(Limits{},f);begin(a);assert(a.command("TRIAL_PULSE",2,2,true,1520));
 SafetyCore step(Limits{},f);begin(step);step.command("TRIAL_PULSE",2,2,true,1500);step.tick(502);assert(step.command("TRIAL_PULSE",602,3,true,1540));
 SafetyCore deadline(Limits{},f);begin(deadline);deadline.command("TRIAL_PULSE",2,2,true,1500);deadline.tick(502);
 for(unsigned i=1;i<=29;i++)assert(!deadline.command("HEARTBEAT",i*1000,i+2,true));
 deadline.tick(30001);assert(deadline.state==SafetyCore::FAULT && !deadline.trial);
 SafetyCore lost(Limits{},f);begin(lost);lost.tick(5001);assert(lost.state==SafetyCore::FAULT);
 SafetyCore stop(Limits{},f);begin(stop);stop.command("TRIAL_PULSE",2,2,true,1500);stop.command("STOP",3,0,false);assert(stop.state==SafetyCore::DISARMED && !stop.trial && !f.gate);
 SafetyCore disarm(Limits{},f);begin(disarm);disarm.command("DISARM",2,0,false);assert(!disarm.trial && !f.gate);
 SafetyCore fault(Limits{},f);begin(fault);f.fail=true;fault.command("TRIAL_PULSE",2,2,true,1500);assert(fault.outputUnknown);f.fail=false;
 SafetyCore again(Limits{},f);assert(again.state==SafetyCore::DISARMED && !again.trial);
 SafetyCore repeat(Limits{},f);begin(repeat);assert(repeat.command("TRIAL_PULSE",2,1,true,1500));
 SafetyCore running(Limits{},f);begin(running);running.command("TRIAL_PULSE",2,2,true,1500);assert(running.command("TRIAL_PULSE",102,3,true,1520));
 SafetyCore regular(Limits{},f);begin(regular);assert(regular.command("SET_PULSE_US",2,2,true,1500));
 std::cout<<"SIMULATED trial checks PASS: capability/physical/session gate, range/initial/step, pulse end, window/heartbeat/comm timeout, stop/disarm/fault/reboot/replay, no regular SET bypass\n";
}
