#pragma once
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace pyportal {
enum class Op { Invalid, Status, Press, Setup, ExitSetup };
struct Command {
  Op op = Op::Invalid;
  uint32_t sequence = 0;
  uint8_t button = 0;
  uint8_t event = 0;  // HomeKit single press=0, long press=2.
};

inline Command parse(const char *line) {
  Command cmd;
  if (!std::strcmp(line, "PYC1 STATUS")) cmd.op = Op::Status;
  else if (!std::strcmp(line, "PYC1 SETUP")) cmd.op = Op::Setup;
  else if (!std::strcmp(line, "PYC1 EXIT")) cmd.op = Op::ExitSetup;
  else if (!std::strncmp(line, "PYC1 PRESS ", 11) ||
           !std::strncmp(line, "PYC1 HOLD ", 10)) {
    const bool hold = line[5] == 'H';
    const char *p = line + (hold ? 10 : 11);
    if (*p < '0' || *p > '9') return cmd;
    uint32_t sequence = 0;
    while (*p >= '0' && *p <= '9') {
      uint32_t digit = static_cast<uint32_t>(*p++ - '0');
      if (sequence > (UINT32_MAX - digit) / 10) return cmd;
      sequence = sequence * 10 + digit;
    }
    if (!sequence || *p++ != ' ') return cmd;
    if ((*p != '1' && *p != '2') || p[1] != '\0') return cmd;
    cmd.op = Op::Press;
    cmd.sequence = sequence;
    cmd.button = static_cast<uint8_t>(*p - '0');
    cmd.event = hold ? 2 : 0;
  }
  return cmd;
}

// Drop an entire damaged/oversized line and resume at the next newline.
// This keeps ESP32 boot messages and partial serial frames out of the protocol.
struct LineReader {
  char data[96] = {};
  size_t used = 0;
  bool discard = false;
  const char *feed(char c) {
    if (c == '\r') return nullptr;
    if (c == '\n') {
      bool valid = !discard && used != 0;
      data[used] = '\0';
      used = 0;
      discard = false;
      return valid ? data : nullptr;
    }
    if (discard) return nullptr;
    if (c < 32 || c > 126 || used >= sizeof(data) - 1) {
      discard = true;
      used = 0;
      return nullptr;
    }
    data[used++] = c;
    return nullptr;
  }
};
}  // namespace pyportal
