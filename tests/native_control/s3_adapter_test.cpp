// SIMULATED ESP32-S3 adapter test: 14-bit/50Hz/GPIO4 board profile.
// No hardware accessed, no waveform measured. Compile with -DGRIPPER_BOARD_S3.
#include "../../firmware/gripper_control/gripper_control.ino"
#include <cassert>
#include <iostream>
#include <new>
#include <string>

static void reset(){
 pwm=LedcOutput{};stubDuty=0;stubAppliedDuty=0;stubFreq=50;stubFreshAttach=true;
 lagReadback=false;lagNeverLatch=false;readMismatch=false;writeFails=false;attachFails=false;detachFails=false;
 pwmCalls=attaches=0;testNow=0;ESP.chip="SIMULATED_ESP32_S3";ESP.flash=16777216;ESP.psram=8388608;
 setup();safety->~SafetyCore();new(safety) SafetyCore(limits,pwm);setup();
}

static std::string request(const std::string& text){
 Serial.output.clear();used=text.size();memcpy(buffer,text.data(),used);process();return Serial.output;
}

int main(){
 // Board-level profile, not a guessed runtime detection.
 static_assert(CFG_GPIO==4,"S3 PWM GPIO must be 4");
 static_assert(CFG_FREQUENCY_HZ==50,"S3 PWM must stay at 50Hz");
 static_assert(CFG_RESOLUTION_BITS==14,"S3 LEDC must use 14-bit");
 assert(std::string(CFG_FIRMWARE_VERSION)=="gripper-control-s3-0.9b26.0");
 assert(std::string(CFG_BOARD_TARGET)=="s3");

 // 14-bit microsecond conversion, including the requested A/B positions.
 assert(pulseDuty(500,50,14)==410);
 assert(pulseDuty(1150,50,14)==942);
 assert(pulseDuty(1200,50,14)==983);
 assert(pulseDuty(1400,50,14)==1147);
 assert(pulseDuty(1500,50,14)==1229);
 assert(pulseDuty(2500,50,14)==2048);
 assert(pulseDuty(20000,50,14)==0);
 // Classic 16-bit rounding remains unchanged for the old target.
 assert(pulseDuty(1500,50,16)==4915);

 // 14-bit must be accepted by the calibrated-limits validator, not only 16-bit.
 Limits calibrated;calibrated.enabled=calibrated.calibrated=true;calibrated.bits=14;
 calibrated.low=1000;calibrated.high=2000;calibrated.initial=1500;calibrated.step=50;calibrated.total=100;
 assert(calibrated.valid());
 Limits wrong;wrong=calibrated;wrong.bits=0;assert(!wrong.valid());

 // Boot remains gated: no attach, no duty, no gate.
 reset();
 assert(CFG_BENCH_ENABLED && !CFG_TRIAL_ENABLED);
 assert(pwmCalls==0 && !pwm.benchGate && safety->state==SafetyCore::DISARMED);
 assert(!pwm.set(1500) && pwmCalls==0);

 // STATUS exposes the complete old diagnostics plus S3 board fields.
 JsonDocument status;
 assert(!deserializeJson(status,request("{\"protocol_version\":1,\"request_id\":\"s3\",\"command\":\"GET_STATUS\"}")));
 assert(status["board_target"]=="esp32s3");
 assert(status["pwm_gpio"]==4);
 assert(status["pwm_frequency_hz"]==50);
 assert(status["pwm_resolution_bits"]==14);
 assert(status["pwm_readback_settle_ms"]==25);
 assert(status["pwm_first_readback_settle_ms"]==25);
 assert(status["chip_model"]=="SIMULATED_ESP32_S3");
 assert(status["flash_size_bytes"]==16777216);
 assert(status["psram_size_bytes"]==8388608);
 assert(status["state"]=="DISARMED" && status["output_state"]=="DISABLED_UNMEASURED");

 // Mechanical continuous mode: 1500 -> 1400 -> 1200 -> 1150 -> 1500.
 reset();
 assert(!safety->beginBench(0,1,true,false,true));
 assert(!safety->command("BENCH_HOLD_MODE",1,2,true));
 assert(!safety->command("BENCH_HOLD",2,3,true,1500));
 assert(stubDuty==pulseDuty(1500,50,14) && attaches==1);
 assert(!safety->command("BENCH_HOLD",102,4,true,1400));
 assert(stubDuty==pulseDuty(1400,50,14) && attaches==1);
 assert(!safety->command("BENCH_HOLD",202,5,true,1200));
 assert(stubDuty==pulseDuty(1200,50,14) && attaches==1);
 assert(!safety->command("BENCH_HOLD",302,6,true,1150));
 assert(stubDuty==pulseDuty(1150,50,14) && attaches==1);
 assert(pwm.lastStage==std::string("OK"));

 // Continuous hold beyond 5s: heartbeat keeps communication alive; no hold lease.
 assert(!safety->command("HEARTBEAT",3000,7,true));
 safety->tick(6000);assert(safety->state==SafetyCore::ACTIVE && pwm.attached);
 assert(!safety->command("HEARTBEAT",7000,8,true));
 safety->tick(9000);assert(safety->state==SafetyCore::ACTIVE && pwm.attached);
 assert(!safety->command("BENCH_HOLD",9100,9,true,1500));
 assert(stubDuty==pulseDuty(1500,50,14));
 assert(!safety->command("HEARTBEAT",13000,10,true));
 safety->tick(16000);assert(safety->state==SafetyCore::ACTIVE);
 // STOP erases gate and detaches the channel.
 assert(!safety->command("STOP",16001,0,false));
 assert(safety->state==SafetyCore::DISARMED && !pwm.attached && stubDuty==0);
 assert(!pwm.set(1500));

 // Out-of-range target faults before any output; gate is revoked.
 reset();
 assert(!safety->beginBench(0,1,true,false,true));
 assert(!safety->command("BENCH_HOLD_MODE",1,2,true));
 assert(safety->command("BENCH_HOLD",2,3,true,2501));
 assert(safety->state==SafetyCore::FAULT && !pwm.attached && !pwm.benchGate);

 // LEDC write failure keeps the old diagnostic fields on the 14-bit path.
 reset();
 assert(!safety->beginBench(0,1,true,false,true));
 assert(!safety->command("BENCH_HOLD_MODE",1,2,true));
 assert(!safety->command("BENCH_HOLD",2,3,true,1500));
 writeFails=true;testNow=1002; // clear the 100ms rate limit, not the 5s comm timeout
 std::string base=std::string("{\"protocol_version\":1,\"request_id\":\"diag\",\"boot_id\":\"")+bootId+"\",\"sequence\":";
 JsonDocument e;
 assert(!deserializeJson(e,request(base+"4,\"command\":\"BENCH_HOLD\",\"pulse_us\":1400}")));
 assert(e["type"]=="ERROR" && e["error"]=="OUTPUT_API_FAILURE");
 assert(e["output_api_stage"]=="WRITE_FAIL");
 assert(e["output_expected_duty"]==pulseDuty(1400,50,14));
 assert(e["output_expected_freq_hz"]==50);
 assert(safety->state==SafetyCore::FAULT);

 std::cout<<"SIMULATED S3 adapter PASS: GPIO4/50Hz/14-bit, duty rounding, 1500-1400-1200-1150-1500, >5s hold, STOP, FAULT, LEDC diagnostics, old 16-bit rounding\n";
}
