#include <Arduino.h>
#include <ArduinoJson.h>
#include "serial_config.h"
// Serial-only test: no pin configuration, PWM, servo or motion initialization.
static const char* FW = TEST_FW_VERSION;
static const size_t MAX_LINE = TEST_MAX_LINE;
static char line[MAX_LINE + 1];
static size_t used = 0;
static bool overflow = false;
static uint32_t lastByte = 0;
void reply(const char* id, const char* type, const char* error = nullptr) {
  JsonDocument out;
  out["protocol_version"] = 1;
  if (id) out["request_id"] = id; else out["request_id"] = nullptr;
  out["type"] = type;
  out["firmware_version"] = FW;
  if (error) out["error"] = error;
  if (!strcmp(type, "STATUS")) {
    out["state"] = "SERIAL_ONLY_NO_MOTION";
    out["uptime_ms"] = millis();
    out["chip_model"] = ESP.getChipModel();
    out["flash_bytes"] = ESP.getFlashChipSize();
    out["motion_enabled"] = false;
  }
  serializeJson(out, Serial); Serial.println();
}
struct Reader {
  size_t pos=0;
  int read(){return pos<used ? (unsigned char)line[pos++] : -1;}
  int peek(){return pos<used ? (unsigned char)line[pos] : -1;}
  size_t readBytes(char* dst,size_t n){size_t i=0;while(i<n && pos<used)dst[i++]=line[pos++];return i;}
};
void processLine() {
  if (overflow) { reply(nullptr,"ERROR","FRAME_TOO_LONG"); return; }
  JsonDocument doc;
  Reader reader;
  auto parseError=deserializeJson(doc, reader);
  bool trailing=false;
  while(reader.pos<used){char c=line[reader.pos++];if(c!=' ' && c!='\r' && c!='\t')trailing=true;}
  if (parseError || trailing || !doc.is<JsonObject>()) {
    reply(nullptr,"ERROR","INVALID_JSON"); return;
  }
  const char* id = doc["request_id"].is<const char*>() ? doc["request_id"].as<const char*>() : nullptr;
  if (!id || !strlen(id) || strlen(id)>64) {reply(nullptr,"ERROR","INVALID_REQUEST_ID");return;}
  if (!doc["protocol_version"].is<int>() || doc["protocol_version"].as<int>() != 1 || !doc["command"].is<const char*>()) {
    reply(id,"ERROR","INVALID_ENVELOPE");return;
  }
  const char* command=doc["command"];
  if (!strcmp(command,"PING")) reply(id,"PONG");
  else if (!strcmp(command,"GET_STATUS")) reply(id,"STATUS");
  else reply(id,"ERROR","UNKNOWN_COMMAND");
}
void setup() { Serial.begin(TEST_BAUD, SERIAL_8N1); }
void loop() {
  // Bounded work per loop; never wait for a complete frame.
  for (size_t n=0;n<64 && Serial.available();++n) {
    char ch=Serial.read(); lastByte=millis();
    if(ch=='\n') {processLine();used=0;overflow=false;}
    else if(!overflow) {if(used<MAX_LINE)line[used++]=ch;else overflow=true;}
  }
  if((used || overflow) && (uint32_t)(millis()-lastByte)>TEST_PARTIAL_TIMEOUT) {
    reply(nullptr,"ERROR","INCOMPLETE_FRAME_TIMEOUT"); used=0;overflow=false;
  }
}
