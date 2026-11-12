#pragma once
#include <string>
#include <cstdint>
#include <cstring>
#define SERIAL_8N1 0
inline uint32_t millis(){return 1234;}
struct SerialStub {std::string output;void begin(int,int){} int available(){return 0;} int read(){return -1;} size_t write(uint8_t b){output+=(char)b;return 1;} size_t write(const uint8_t* p,size_t n){output.append((const char*)p,n);return n;} void println(){output+='\n';}};
inline SerialStub Serial;
struct EspStub {const char* getChipModel(){return "SIMULATED_ESP32";} uint32_t getFlashChipSize(){return 4194304;}};
inline EspStub ESP;
