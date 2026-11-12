#include "../../firmware/gripper_control/gripper_control.ino"
#include <cassert>
#include <iostream>
void send(const std::string& s,const char* type,const char* error=nullptr){
 Serial.output.clear();used=s.size();oversized=used>sizeof(buffer);if(!oversized)memcpy(buffer,s.data(),used);process();JsonDocument d;assert(!deserializeJson(d,Serial.output));assert(d["type"]==type);if(error)assert(d["error"]==error);
}
int main(){assert(!pwm.set(1500) && pwmCalls==0);setup();assert(pwmCalls==0 && safety->state==SafetyCore::DISARMED);loop();assert(pwmCalls==0);
 send("{\"request_id\":\"a\",\"protocol_version\":1,\"command\":\"PING\"}","PONG");
 send("{\"request_id\":\"a\",\"protocol_version\":1,\"command\":\"GET_STATUS\"}","STATUS");
 std::string arm=std::string("{\"request_id\":\"b\",\"protocol_version\":1,\"command\":\"ARM\",\"sequence\":1,\"boot_id\":\"")+bootId+"\"}";
 send(arm,"ERROR","UNCALIBRATED_OR_DISABLED");
 send(arm,"ERROR","UNCALIBRATED_OR_DISABLED");
 send("{\"request_id\":\"\",\"protocol_version\":1,\"command\":\"PING\"}","ERROR","INVALID_ID");
 std::string set=std::string("{\"request_id\":\"c\",\"protocol_version\":1,\"command\":\"SET_PULSE_US\",\"pulse_us\":4294967295,\"sequence\":2,\"boot_id\":\"")+bootId+"\"}";
 send(set,"ERROR","NOT_ARMED");
 send("{invalid}","ERROR","INVALID_JSON");send("{} garbage","ERROR","INVALID_JSON");send(std::string(513,'x'),"ERROR","FRAME_TOO_LONG");
 assert(pwmCalls==0);setup();assert(safety->state==SafetyCore::DISARMED && pwmCalls==0);
 std::cout<<"SIMULATED actual firmware adapter: setup/loop disabled, PING/STATUS, locked ARM, malformed/trailing/oversized inputs, restart; zero stub LEDC calls\n";
}
