#include "../esp32/PyPortalHomeKit/Protocol.h"
#include <cassert>
#include <string>
#include <iostream>
using pyportal::Op;

int main() {
  auto valid = pyportal::parse("PYC1 PRESS 42 2");
  assert(valid.op == Op::Press && valid.sequence == 42 && valid.button == 2);
  assert(valid.event == 0);
  auto hold = pyportal::parse("PYC1 HOLD 43 1");
  assert(hold.op == Op::Press && hold.sequence == 43 && hold.button == 1 && hold.event == 2);
  assert(pyportal::parse("PYC1 PRESS 4294967295 1").op == Op::Press);
  for (const char *bad : {"PYC1 PRESS 0 1", "PYC1 PRESS -1 1",
                         "PYC1 PRESS 4294967296 1", "PYC1 PRESS 9999999999999999 1",
                         "PYC1 PRESS 1 3", "PYC1 PRESS 1 1 trailing",
                         "PYC1 PRESS 2", "PYC1 PRESS 2 ", "PYC1 PRESS 2 12",
                         "PRESS 2 1", "PYC1 SETUP extra", "PYC1 HOLD 0 1",
                         "PYC1 HOLD 4294967296 1", "PYC1 HOLD 1 3",
                         "PYC1 HOLD 1 1 trailing", "PYC1 HOLD 2"})
    assert(pyportal::parse(bad).op == Op::Invalid);
  assert(pyportal::parse("PYC1 SETUP").op == Op::Setup);
  assert(pyportal::parse("PYC1 EXIT").op == Op::ExitSetup);
  pyportal::LineReader reader;
  int presses = 0;
  const std::string stream = std::string(200, 'X') + "PYC1 PRESS 1 1\n" +
      "boot message\nPYC1 PRESS 5 2\r\n" + std::string("bad\0", 4) +
      "PYC1 PRESS 6 1\nPYC1 PRESS 7 1\n";
  for (char c : stream) {
    const char *line = reader.feed(c);
    if (line && pyportal::parse(line).op == Op::Press) ++presses;
  }
  assert(presses == 2);  // Oversized and binary-damaged frames must not fire.
  std::cout << "UART command tests passed\n";
}
