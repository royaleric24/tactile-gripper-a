#include "../../firmware/gripper_control/gripper_control.ino"
#include <cassert>
#include <iostream>
void request(const std::string& text,const char* type){Serial.output.clear();used=text.size();memcpy(buffer,text.data(),used);process();JsonDocument d;assert(!deserializeJson(d,Serial.output));assert(d["type"]==type);}
int main(){
 setup();assert(CFG_BENCH_ENABLED && !CFG_TRIAL_ENABLED);assert(pwmCalls==0 && !pwm.benchGate && safety->state==SafetyCore::DISARMED);
 assert(!pwm.set(1500));
 std::string base=std::string("{\"protocol_version\":1,\"request_id\":\"bench\",\"boot_id\":\"")+bootId+"\",\"sequence\":";
 request(base+"1,\"command\":\"BEGIN_BENCH\",\"physical_condition\":\"DETACHED_BENCH\"}","ACK");assert(pwmCalls==0 && pwm.benchGate);
 request(base+"2,\"command\":\"BENCH_PULSE\",\"pulse_us\":1500}","ACK");assert(stubDuty==4915 && freqReadsAtZero==0);
 testNow=500;safety->tick(testNow);assert(!pwm.attached && safety->state==SafetyCore::ARMED);
 testNow=600;request(base+"3,\"command\":\"BENCH_PULSE\",\"pulse_us\":1550}","ACK");testNow=1100;safety->tick(testNow);
 request(base+"4,\"command\":\"DISARM\"}","ACK");assert(!pwm.benchGate && !pwm.attached && safety->state==SafetyCore::DISARMED);
 assert(!pwm.set(1500));
 std::cout<<"SIMULATED Bench actual firmware JSON/LEDC adapter PASS; default disabled, authorized pulse/end/repeat/disarm\n";
}
