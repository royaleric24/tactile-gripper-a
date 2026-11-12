#include <Arduino.h>
#include <ArduinoJson.h>
#if defined(GRIPPER_BOARD_S3)
#include "generated_config_s3.h"
#define BOARD_TARGET "esp32s3"
#else
#include "generated_config.h"
#define BOARD_TARGET "esp32"
#endif
#include "SafetyCore.h"
struct LedcOutput:Output {
 bool attached=false,uncertain=false,trialGate=false,benchGate=false;uint32_t trialLo=0,trialHi=0;
 // Stage 0.9B-20B diagnostics: record the last output attempt for STATUS/ERROR.
 // These members only expose why set() failed; they never change the control decision.
 const char* lastStage="NONE";bool lastFirstWrite=false,lastWriteOk=false,lastOffOk=true;
 uint32_t lastExpectedDuty=0,lastActualDuty=0,lastExpectedFreq=0,lastActualFreq=0;
 bool trialPermit(bool enabled,uint32_t lo,uint32_t hi) override {
  if(enabled && (!CFG_TRIAL_ENABLED || uncertain || lo<CFG_TRIAL_MIN_US || hi>CFG_TRIAL_MAX_US || lo>hi))return false;
  trialGate=enabled;trialLo=lo;trialHi=hi;return true;
 }
 bool benchPermit(bool enabled,uint32_t lo,uint32_t hi) override {
  if(enabled && (!CFG_BENCH_ENABLED || uncertain || lo<CFG_BENCH_MIN_US || hi>CFG_BENCH_MAX_US || lo>hi))return false;
  benchGate=enabled;return true;
 }
 bool set(uint32_t us) override {
  // Independent guard at the actual output boundary, not only in SafetyCore.
  bool regular=CFG_HARDWARE_ENABLED && CFG_CALIBRATED && limitsForOutput(us);
  bool test=CFG_TRIAL_ENABLED && trialGate && us>=trialLo && us<=trialHi;
  bool benchTest=CFG_BENCH_ENABLED && benchGate && us>=CFG_BENCH_MIN_US && us<=CFG_BENCH_MAX_US;
  if(uncertain || !(regular || test || benchTest))return false;
  lastFirstWrite=!attached;
  if(!attached){
   if(!ledcAttach(CFG_GPIO,CFG_FREQUENCY_HZ,CFG_RESOLUTION_BITS)){uncertain=true;lastStage="ATTACH_FAIL";return false;}
   attached=true;
  }
  // ledcAttach validates timer configuration and reports failure itself.
  // Arduino-ESP32 3.3.2 ledcReadFreq returns 0 while duty is zero:
  // never emit a probe pulse to validate initialization.
  uint32_t duty=pulseDuty(us,CFG_FREQUENCY_HZ,CFG_RESOLUTION_BITS);
  lastExpectedDuty=duty;lastExpectedFreq=CFG_FREQUENCY_HZ;
  // Split the former short-circuit chain so the failing stage is recorded.
  // Evaluation order is unchanged: no write on zero duty, readback only after
  // a successful write, frequency readback only after the duty readback matches.
  if(duty==0){uncertain=true;lastStage="INVALID_DUTY";return false;}
  lastWriteOk=ledcWrite(CFG_GPIO,duty);
  if(!lastWriteOk){uncertain=true;lastStage="WRITE_FAIL";return false;}
  // ESP32 applies a new LEDC duty at the next PWM period; duty_rd can still
  // report the previous target immediately after ledcWrite. The settle delay
  // is board-level: the classic target keeps its original immediate first
  // readback, while the S3 target waits on the first write too.
  uint32_t settle=lastFirstWrite?CFG_FIRST_READBACK_SETTLE_MS:CFG_READBACK_SETTLE_MS;
  if(settle)delay(settle);
  lastActualDuty=ledcRead(CFG_GPIO);
  if(lastActualDuty!=duty){uncertain=true;lastStage="READ_MISMATCH";return false;}
  lastActualFreq=ledcReadFreq(CFG_GPIO);
  if(lastActualFreq!=CFG_FREQUENCY_HZ){uncertain=true;lastStage="FREQ_MISMATCH";return false;}
  lastStage="OK";return true;
 }
 bool limitsForOutput(uint32_t us) const {
  return CFG_SAFE_MIN_US>0 && CFG_SAFE_MIN_US<=CFG_INITIAL_PULSE_US && CFG_INITIAL_PULSE_US<=CFG_SAFE_MAX_US && us>=CFG_SAFE_MIN_US && us<=CFG_SAFE_MAX_US;
 }
 bool off() override {
  if(!attached)return !uncertain;
  bool zero=ledcWrite(CFG_GPIO,0);bool detached=ledcDetach(CFG_GPIO);
  if(detached)attached=false;
  lastOffOk=zero && detached;
  if(!lastOffOk)uncertain=true;
  return zero && detached && !uncertain;
 }
} pwm;
Limits limits;
SafetyCore* safety;
char bootId[33];char buffer[CFG_MAX_LINE_BYTES];size_t used=0;bool oversized=false;uint32_t lastByte=0;
void respond(const char* id,const char* type,const char* error=nullptr){
 JsonDocument d;d["protocol_version"]=1;d["firmware_version"]=CFG_FIRMWARE_VERSION;
 d["board_target"]=BOARD_TARGET;d["pwm_gpio"]=CFG_GPIO;d["pwm_frequency_hz"]=CFG_FREQUENCY_HZ;d["pwm_resolution_bits"]=CFG_RESOLUTION_BITS;
 d["pwm_readback_settle_ms"]=CFG_READBACK_SETTLE_MS;d["pwm_first_readback_settle_ms"]=CFG_FIRST_READBACK_SETTLE_MS;
 d["chip_model"]=ESP.getChipModel();d["flash_size_bytes"]=ESP.getFlashChipSize();d["psram_size_bytes"]=ESP.getPsramSize();
 if(id)d["request_id"]=id;else d["request_id"]=nullptr;
 d["type"]=type;if(error)d["error"]=error;
 d["state"]=safety->name();d["fault_reason"]=safety->reason;d["boot_id"]=bootId;d["uptime_ms"]=millis();
 d["calibration_state"]=CFG_CALIBRATED?"CONFIRMED":"UNCALIBRATED";
 d["hardware_enabled"]=CFG_HARDWARE_ENABLED;d["motion_enabled"]=limits.valid() || safety->trial;d["calibrated_motion_enabled"]=limits.valid();d["trial_capable"]=CFG_TRIAL_ENABLED;d["trial_active"]=safety->trial && !safety->bench;d["bench_capable"]=CFG_BENCH_ENABLED;d["bench_active"]=safety->bench;d["mechanical_assembly"]=safety->mech;d["bench_window_remaining_ms"]=safety->bench?(safety->benchWindow-uint32_t(millis()-safety->trialStart)):0;d["trial_window_remaining_ms"]=(safety->trial && !safety->bench)?(CFG_TRIAL_WINDOW_MS-uint32_t(millis()-safety->trialStart)):0;d["last_sequence"]=safety->sequence;
 d["hold_capable"]=CFG_BENCH_HOLD_ENABLED;d["hold_mode"]=safety->hold;
 d["hold_remaining_ms"]=(safety->hold && safety->holdStarted && !safety->mech)?(safety->holdLimit-uint32_t(millis()-safety->holdStart)):0;
 d["output_state"]=safety->outputUnknown?"UNKNOWN":pwm.attached?"PWM_COMMANDED_UNMEASURED":"DISABLED_UNMEASURED";
 if(pwm.attached)d["commanded_pulse_us"]=safety->target;else d["commanded_pulse_us"]=nullptr;
 d["actual_angle_deg"]=nullptr;d["actual_opening"]=nullptr;
 // Optional backward-compatible diagnostics: present only after an output issue.
 // Normal STATUS/ACK responses keep their previous field set.
 if(pwm.uncertain){
  d["output_api_stage"]=pwm.lastStage;d["output_first_write"]=pwm.lastFirstWrite;
  d["output_write_ok"]=pwm.lastWriteOk;d["output_off_ok"]=pwm.lastOffOk;
  d["output_expected_duty"]=pwm.lastExpectedDuty;d["output_actual_duty"]=pwm.lastActualDuty;
  d["output_expected_freq_hz"]=pwm.lastExpectedFreq;d["output_actual_freq_hz"]=pwm.lastActualFreq;
 }
 if(Serial.availableForWrite()<900){safety->fault("TX_BACKPRESSURE");return;}
 serializeJson(d,Serial);Serial.println();
}
struct Reader {size_t pos=0;int read(){return pos<used?(unsigned char)buffer[pos++]:-1;}int peek(){return pos<used?(unsigned char)buffer[pos]:-1;}size_t readBytes(char* dst,size_t n){size_t i=0;while(i<n && pos<used)dst[i++]=buffer[pos++];return i;}};
void invalid(const char* error){if(safety->state!=SafetyCore::DISARMED)safety->fault(error);respond(nullptr,"ERROR",error);}
void process(){
 if(oversized){invalid("FRAME_TOO_LONG");return;}
 JsonDocument d;Reader reader;auto err=deserializeJson(d,reader);
 bool trailing=false;while(reader.pos<used){char c=buffer[reader.pos++];if(c!=' ' && c!='\r' && c!='\t')trailing=true;}
 if(err || trailing || !d.is<JsonObject>()){invalid("INVALID_JSON");return;}
 const char* id=d["request_id"].is<const char*>()?d["request_id"].as<const char*>():nullptr;
 if(!id || !strlen(id) || strlen(id)>64){invalid("INVALID_ID");return;}
 if(!d["protocol_version"].is<int>() || d["protocol_version"].as<int>()!=1 || !d["command"].is<const char*>()){invalid("INVALID_ENVELOPE");return;}
 const char* cmd=d["command"];
 if(!strcmp(cmd,"PING")){respond(id,"PONG");return;}
 if(!strcmp(cmd,"GET_STATUS")){respond(id,"STATUS");return;}
 bool session=d["boot_id"].is<const char*>() && !strcmp(d["boot_id"].as<const char*>(),bootId);
 if(strcmp(cmd,"STOP") && strcmp(cmd,"DISARM") && (!d["sequence"].is<uint32_t>() || d["sequence"].as<uint32_t>()==0)){invalid("INVALID_SEQUENCE");return;}
 uint32_t us=0;
 if(!strcmp(cmd,"SET_PULSE_US") || !strcmp(cmd,"TRIAL_PULSE") || !strcmp(cmd,"BENCH_PULSE") || !strcmp(cmd,"BENCH_HOLD")){
  if(!d["pulse_us"].is<uint32_t>()){invalid("INVALID_PULSE");return;}us=d["pulse_us"];
 }
 if(!strcmp(cmd,"BEGIN_BENCH")){
  bool detached=d["physical_condition"].is<const char*>() && !strcmp(d["physical_condition"].as<const char*>(),"DETACHED_BENCH");
  bool assembled=d["physical_condition"].is<const char*>() && !strcmp(d["physical_condition"].as<const char*>(),"GRIPPER_ASSEMBLED");
  const char* e=safety->beginBench(millis(),d["sequence"],session,detached,assembled);
  respond(id,e?"ERROR":"ACK",e);return;
 }
 if(!strcmp(cmd,"BEGIN_TRIAL")){
  if(!d["low_us"].is<uint32_t>() || !d["high_us"].is<uint32_t>() || !d["initial_us"].is<uint32_t>()){invalid("TRIAL_RANGE");return;}
  bool detached=d["physical_condition"].is<const char*>() && !strcmp(d["physical_condition"].as<const char*>(),"LINKAGE_DETACHED");
  bool local=d["physical_condition"].is<const char*>() && !strcmp(d["physical_condition"].as<const char*>(),"LOCAL_RANGE_CONFIRMED");
  const char* err=safety->beginTrial(millis(),d["sequence"],session,d["low_us"],d["high_us"],d["initial_us"],detached,local);
  respond(id,err?"ERROR":"ACK",err);return;
 }
 const char* error=safety->command(cmd,millis(),d["sequence"]|0u,session,us);
 respond(id,error?"ERROR":"ACK",error);
}
void setup(){
 // Deliberately no GPIO, LEDC or servo initialization here.
 Serial.setTxBufferSize(2048);Serial.begin(115200,SERIAL_8N1);
 limits.enabled=CFG_HARDWARE_ENABLED;limits.calibrated=CFG_CALIBRATED;
 limits.hz=CFG_FREQUENCY_HZ;limits.bits=CFG_RESOLUTION_BITS;
 limits.low=CFG_SAFE_MIN_US;limits.high=CFG_SAFE_MAX_US;limits.initial=CFG_INITIAL_PULSE_US;limits.step=CFG_MAX_STEP_US;limits.total=CFG_MAX_TOTAL_CHANGE_US;
 limits.interval=CFG_MIN_INTERVAL_MS;limits.timeout=CFG_COMMUNICATION_TIMEOUT_MS;limits.lease=CFG_MAX_OUTPUT_MS;
 static SafetyCore core(limits,pwm);safety=&core;
 core.trialCap=CFG_TRIAL_ENABLED;core.trialLow=CFG_TRIAL_MIN_US;core.trialHigh=CFG_TRIAL_MAX_US;core.trialStep=CFG_TRIAL_STEP_US;core.trialTotal=CFG_TRIAL_TOTAL_US;core.trialWindow=CFG_TRIAL_WINDOW_MS;core.pulseTime=CFG_TRIAL_PULSE_MS;core.trialComm=CFG_TRIAL_COMM_TIMEOUT_MS;
 core.benchCap=CFG_BENCH_ENABLED;core.benchLow=CFG_BENCH_MIN_US;core.benchHigh=CFG_BENCH_MAX_US;core.benchInitial=CFG_BENCH_INITIAL_US;core.benchStep=CFG_BENCH_STEP_US;core.benchWindow=CFG_BENCH_WINDOW_MS;core.benchPulse=CFG_BENCH_PULSE_MS;core.benchComm=CFG_BENCH_COMM_TIMEOUT_MS;
 core.holdCap=CFG_BENCH_HOLD_ENABLED;core.holdLimit=CFG_BENCH_HOLD_MS;
 snprintf(bootId,sizeof(bootId),"%08lx%08lx%08lx%08lx",(unsigned long)esp_random(),(unsigned long)esp_random(),(unsigned long)esp_random(),(unsigned long)esp_random());
}
void loop(){
 safety->tick(millis());
 for(size_t n=0;n<64 && Serial.available();++n){
  safety->tick(millis());char c=Serial.read();lastByte=millis();
  if(c=='\n'){process();used=0;oversized=false;}
  else if(!oversized){if(used<sizeof(buffer))buffer[used++]=c;else oversized=true;}
 }
 if((used || oversized) && uint32_t(millis()-lastByte)>=CFG_PARTIAL_TIMEOUT_MS){invalid("PARTIAL_TIMEOUT");used=0;oversized=false;}
}
