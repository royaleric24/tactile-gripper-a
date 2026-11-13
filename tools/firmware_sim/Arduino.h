#pragma once
#include <cstdint>
#include <cstdio>
#include <cstring>

#define HIGH 1
#define LOW 0
#define INPUT 0
#define OUTPUT 1

void pinMode(uint8_t pin, uint8_t mode);
void digitalWrite(uint8_t pin, uint8_t value);
int digitalRead(uint8_t pin);
void delay(unsigned long ms);
void delayMicroseconds(unsigned int us);

typedef uint8_t byte;
