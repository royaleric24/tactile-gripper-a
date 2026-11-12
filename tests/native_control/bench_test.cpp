#include "../../firmware/gripper_control/SafetyCore.h"
#include <cassert>
#include <iostream>
struct BenchFake:Output{bool gate=false,fail=false;int sets=0,offs=0;
 bool benchPermit(bool enabled,uint32_t,uint32_t)override{gate=enabled;return true;}
 bool set(uint32_t)override{++sets;return gate&&!fail;}
 bool off()override{++offs;return !fail;}};
int main(){
 BenchFake f;SafetyCore c(Limits{},f);
 assert(c.beginBench(0,1,true,true));assert(f.sets==0);c.benchCap=true;
 assert(c.beginBench(0,1,true,false));assert(c.beginBench(0,1,false,true));
 assert(!c.beginBench(0,1,true,true));assert(c.bench && f.gate && f.sets==0);
 assert(!c.command("BENCH_PULSE",1,2,true,1500));c.tick(501);assert(c.state==SafetyCore::ARMED);
 assert(!c.command("BENCH_PULSE",601,3,true,1550));c.tick(1101);
 assert(!c.command("BENCH_PULSE",1201,4,true,1600));c.tick(1701);
 assert(!c.command("BENCH_PULSE",1801,5,true,1550));c.tick(2301); // no inherited trial 80us cumulative cap
 assert(!c.command("STOP",2302,0,false));assert(!c.bench && !c.trial && !f.gate);
 assert(c.command("BENCH_PULSE",2303,6,true,1500));assert(f.sets==4);
 BenchFake e;SafetyCore expiry(Limits{},e);expiry.benchCap=true;expiry.beginBench(0,1,true,true);
 for(int t=1000;t<300000;t+=1000)assert(!expiry.command("HEARTBEAT",t,t+1,true));
 expiry.tick(300000);assert(expiry.state==SafetyCore::FAULT && !e.gate && !expiry.bench);
 // Stage 0.9B-20C manual Bench relaxed the old fixed-first-target and 50us
 // step rules; the absolute 500..2500 range still applies.
 BenchFake x;SafetyCore first(Limits{},x);first.benchCap=true;first.beginBench(0,1,true,true);
 assert(!first.command("BENCH_PULSE",1,2,true,1550));assert(x.sets==1);
 BenchFake y;SafetyCore range(Limits{},y);range.benchCap=true;range.beginBench(0,1,true,true);
 assert(range.command("BENCH_PULSE",1,2,true,2501));assert(y.sets==0);
 BenchFake z;SafetyCore step(Limits{},z);step.benchCap=true;step.beginBench(0,1,true,true);step.command("BENCH_PULSE",1,2,true,1500);step.tick(501);
 assert(!step.command("BENCH_PULSE",601,3,true,1551));assert(z.sets==2);
 BenchFake a;SafetyCore timeout(Limits{},a);timeout.benchCap=true;timeout.beginBench(0,1,true,true);timeout.tick(5000);assert(timeout.state==SafetyCore::FAULT && !a.gate);
 BenchFake b;SafetyCore failure(Limits{},b);failure.benchCap=true;failure.beginBench(0,1,true,true);b.fail=true;
 assert(failure.command("BENCH_PULSE",1,2,true,1500));assert(failure.outputUnknown && !b.gate);
 std::cout<<"SIMULATED Bench state machine PASS: authorization, arbitrary first target, continuous inputs, absolute range, finite window, heartbeat, comm timeout, stop, fault\n";
}
