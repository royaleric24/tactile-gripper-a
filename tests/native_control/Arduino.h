#pragma once
#include <string>
#include <cstdint>
#include <cstring>
#define SERIAL_8N1 0
inline uint32_t testNow=0;inline int pwmCalls=0;
inline uint32_t millis(){return testNow;}
inline uint32_t esp_random(){return 123456;}
inline bool attachFails=false,writeFails=false,detachFails=false,readMismatch=false;
inline bool lagReadback=false,lagNeverLatch=false,stubFreshAttach=true;
inline uint32_t stubDuty=0,stubAppliedDuty=0,stubFreq=50;inline int attaches=0,freqReadsAtZero=0;
inline bool ledcAttach(int,int,int){++pwmCalls;++attaches;stubDuty=0;stubAppliedDuty=0;stubFreshAttach=true;return !attachFails;}
inline bool ledcWrite(int,uint32_t duty){++pwmCalls;if(writeFails)return false;stubDuty=duty;if(!lagReadback)stubAppliedDuty=duty;else if(stubFreshAttach){stubAppliedDuty=duty;stubFreshAttach=false;}return true;}
inline bool ledcDetach(int){++pwmCalls;return !detachFails;}
inline void delay(uint32_t ms){testNow+=ms;if(lagReadback && !lagNeverLatch)stubAppliedDuty=stubDuty;}
inline uint32_t ledcRead(int){return readMismatch?0:(lagReadback?stubAppliedDuty:stubDuty);}
inline uint32_t ledcReadFreq(int){if(!ledcRead(0)){++freqReadsAtZero;return 0;}return stubFreq;}
struct SerialStub {std::string output;void setTxBufferSize(int){}void begin(int,int){}int available(){return 0;}int availableForWrite(){return 2048;}int read(){return -1;}size_t write(uint8_t b){output+=(char)b;return 1;}size_t write(const uint8_t* p,size_t n){output.append((const char*)p,n);return n;}void println(){output+='\n';}};
inline SerialStub Serial;
struct EspStub {const char* chip="SIMULATED_ESP32";uint32_t flash=4194304,psram=0;const char* getChipModel(){return chip;}uint32_t getFlashChipSize(){return flash;}uint32_t getPsramSize(){return psram;}};
inline EspStub ESP;
