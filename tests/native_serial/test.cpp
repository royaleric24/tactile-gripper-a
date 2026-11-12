#include "../../firmware/serial_test/serial_test.ino"
#include <cassert>
#include <iostream>
void check(const std::string& input,const char* type,const char* error=nullptr){
 Serial.output.clear();used=input.size();overflow=used>MAX_LINE;
 if(!overflow)memcpy(line,input.data(),used);
 processLine();JsonDocument d;assert(!deserializeJson(d,Serial.output));
 assert(d["type"]==type);if(error)assert(d["error"]==error);
}
int main(){
 check("{\"protocol_version\":1,\"request_id\":\"test\",\"command\":\"PING\"}","PONG");
 check("{\"protocol_version\":1,\"request_id\":\"test\",\"command\":\"GET_STATUS\"}","STATUS");
 check("{invalid}","ERROR","INVALID_JSON");
 check("{}trailing","ERROR","INVALID_JSON");
 check("[]","ERROR","INVALID_JSON");
 check("{}","ERROR","INVALID_REQUEST_ID");
 check("{\"protocol_version\":1,\"request_id\":\"test\",\"command\":\"MOVE\"}","ERROR","UNKNOWN_COMMAND");
 check(std::string(513,'x'),"ERROR","FRAME_TOO_LONG");
 std::cout<<"SIMULATED: 8 firmware parser cases passed; native host stubs, not ESP32 execution\n";
}
