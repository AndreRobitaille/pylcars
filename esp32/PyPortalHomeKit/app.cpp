// PyPortal HomeKit button coprocessor, prototype 0.3.0.
// Ordinary C++ source; forward declarations are explicit below.
// ESP32 UART0 connects to the PyPortal SAMD51's ESP_TX / ESP_RX.
// HomeSpan 2.1.8, Arduino-ESP32 3.3.8, ESP32 Dev Module, 4MB/min_spiffs.

#include <Arduino.h>
#include <HomeSpan.h>
#include <Preferences.h>
#include <WebServer.h>
#include <DNSServer.h>
#include <WiFi.h>
#include <esp_system.h>
#include "Protocol.h"

static const char *VERSION = "0.3.0";
static char pairingCode[9];
static char apPassword[13];
static char apSSID[24];
static char serialNumber[24];
static bool provisioning = false;
static bool setupRequested = false;
static bool exitSetup = false;
static uint32_t lastSequence = 0;
static uint8_t lastButton = 0;
static uint8_t lastEvent = 0;
static uint32_t lastStatusTime = 0;
static pyportal::LineReader reader;
static SpanCharacteristic *buttons[2] = {nullptr, nullptr};

void sendStatus();
void readCommands();
void provisionWiFi();

const char *statusToken() {
  if (provisioning) return "SETUP";
  switch (homeSpan.getStatus().first) {
    case HS_WIFI_NEEDED: return "NO_WIFI";
    case HS_WIFI_SCANNING:
    case HS_WIFI_CONNECTING: return "CONNECTING";
    case HS_PAIRING_NEEDED: return "PAIR";
    case HS_PAIRED: return "WAIT_HOME";
    case HS_CONNECTED: return "READY";
    default: return "BOOT";
  }
}

void sendStatus() {
  // This link is internal to the board. Do not mirror these codes to USB logs.
  Serial.printf("PYC1 STATE %s %s %s %s\n", statusToken(), pairingCode,
                apSSID, apPassword);
  Serial.println("PYC1 CAPS HOLD");
  lastStatusTime = millis();
}

bool acceptableCode(const char *s) {
  if (!strcmp(s, "12345678") || !strcmp(s, "87654321")) return false;
  for (int i = 1; i < 8; ++i) if (s[i] != s[0]) return true;
  return false;
}

void loadDeviceCodes() {
  Preferences prefs;
  if (!prefs.begin("pyportal", false)) {
    Serial.println("PYC1 FATAL STORAGE");
    while (true) delay(1000);
  }
  String code = prefs.getString("pairing", "");
  if (code.length() != 8) {
    do {
      snprintf(pairingCode, sizeof(pairingCode), "%08lu",
               static_cast<unsigned long>(esp_random() % 100000000));
    } while (!acceptableCode(pairingCode));
    prefs.putString("pairing", pairingCode);
  } else {
    code.toCharArray(pairingCode, sizeof(pairingCode));
  }
  String password = prefs.getString("ap_password", "");
  if (password.length() != 12) {
    const char alphabet[] = "23456789abcdefghjkmnpqrstuvwxyz";
    for (int i = 0; i < 12; ++i)
      apPassword[i] = alphabet[esp_random() % (sizeof(alphabet) - 1)];
    apPassword[12] = '\0';
    prefs.putString("ap_password", apPassword);
  } else {
    password.toCharArray(apPassword, sizeof(apPassword));
  }
  prefs.end();
  const uint64_t mac = ESP.getEfuseMac();
  snprintf(apSSID, sizeof(apSSID), "PyPortal-%06lX",
           static_cast<unsigned long>(mac & 0xFFFFFF));
  snprintf(serialNumber, sizeof(serialNumber), "PYP-%04X%08lX",
           static_cast<unsigned>((mac >> 32) & 0xFFFF),
           static_cast<unsigned long>(mac & 0xFFFFFFFF));
}

void handleCommand(const char *line) {
  const auto cmd = pyportal::parse(line);
  if (cmd.op == pyportal::Op::Status) sendStatus();
  else if (cmd.op == pyportal::Op::Setup && !provisioning) setupRequested = true;
  else if (cmd.op == pyportal::Op::ExitSetup && provisioning) exitSetup = true;
  else if (cmd.op == pyportal::Op::Press) {
    if (cmd.sequence == lastSequence) {
      Serial.printf("PYC1 %s %lu\n", (cmd.button == lastButton && cmd.event == lastEvent) ? "ACK" : "ERROR",
                    static_cast<unsigned long>(cmd.sequence));
      return;
    }
    if (provisioning || homeSpan.getStatus().first != HS_CONNECTED) {
      Serial.printf("PYC1 OFFLINE %lu\n", static_cast<unsigned long>(cmd.sequence));
      return;
    }
    buttons[cmd.button - 1]->setVal(cmd.event);  // SINGLE_PRESS or LONG_PRESS.
    lastSequence = cmd.sequence;
    lastButton = cmd.button;
    lastEvent = cmd.event;
    // ACK means queued for HomeKit. It does not confirm actual lamp state.
    Serial.printf("PYC1 ACK %lu\n", static_cast<unsigned long>(cmd.sequence));
  }
}

void readCommands() {
  size_t budget = 256;
  while (Serial.available() && budget--) {
    const char *line = reader.feed(static_cast<char>(Serial.read()));
    if (line) handleCommand(line);
  }
}

void provisionWiFi() {
  provisioning = true;
  setupRequested = false;
  exitSetup = false;
  sendStatus();
  WiFi.mode(WIFI_AP_STA);
  const IPAddress address(192, 168, 4, 1);
  WiFi.softAPConfig(address, address, IPAddress(255, 255, 255, 0));
  if (!WiFi.softAP(apSSID, apPassword)) {
    Serial.println("PYC1 FATAL ACCESS_POINT");
    delay(1000);
    ESP.restart();
  }
  DNSServer dns;
  dns.start(53, "*", address);
  WebServer server(80);
  bool saved = false;
  String ssid, password;
  char token[17];
  snprintf(token, sizeof(token), "%08lX%08lX",
           static_cast<unsigned long>(esp_random()),
           static_cast<unsigned long>(esp_random()));
  auto showPage = [&]() {
    String page = F("<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'><title>PyPortal setup</title><style>body{font:18px system-ui;max-width:440px;margin:32px auto;padding:0 18px;background:#101923;color:#edf3f7}label{display:block;margin:18px 0 6px}input,button{box-sizing:border-box;width:100%;padding:12px;font:inherit;border-radius:6px}button{margin-top:24px;background:#63b891;border:0}small{color:#b9c7d1}</style></head><body><h1>Connect your PyPortal</h1><p>Enter the 2.4 GHz Wi-Fi network used by your Apple Home hubs.</p><form method='post' action='/save'><label for='ssid'>Wi-Fi name</label><input id='ssid' name='ssid' maxlength='32' required autocapitalize='none' autocorrect='off'><label for='password'>Wi-Fi password</label><input id='password' name='password' type='password' maxlength='64' autocomplete='off'><input type='hidden' name='token' value='");
    page += token;
    page += F("'><button>Save and connect</button></form><p><small>After this screen closes, reconnect your phone to your home Wi-Fi. Add PyPortal Lamp Buttons in Apple Home using the code on the PyPortal's Setup screen.</small></p></body></html>");
    server.sendHeader("Cache-Control", "no-store");
    server.send(200, "text/html", page);
  };
  server.on("/", HTTP_GET, showPage);
  server.on("/save", HTTP_POST, [&]() {
    if (server.arg("token") != token) {
      server.send(403, "text/plain", "Reload the setup page and try again.");
      return;
    }
    ssid = server.arg("ssid");
    password = server.arg("password");
    if (!ssid.length() || ssid.length() > 32 || password.length() > 64 ||
        (password.length() > 0 && password.length() < 8)) {
      server.send(400, "text/plain", "Check the Wi-Fi name and password, then go back.");
      return;
    }
    server.sendHeader("Cache-Control", "no-store");
    server.send(200, "text/html", "<meta name='viewport' content='width=device-width,initial-scale=1'><h2>Settings saved</h2><p>Reconnect to your home Wi-Fi and check the PyPortal screen.</p>");
    saved = true;
  });
  server.onNotFound(showPage);
  server.begin();
  const uint32_t started = millis();
  while (!saved && !exitSetup && millis() - started < 600000UL) {
    dns.processNextRequest();
    server.handleClient();
    readCommands();
    if (millis() - lastStatusTime >= 1000) sendStatus();
    delay(2);
  }
  if (saved) {
    homeSpan.setWifiCredentials(ssid.c_str(), password.c_str());
    // Credentials are stored on the ESP32, never in source files or logs.
    password = "";
  }
  delay(500);
  server.stop();
  dns.stop();
  WiFi.softAPdisconnect(true);
  ESP.restart();
}

void setup() {
  Serial.setRxBufferSize(1024);
  Serial.begin(115200);
  loadDeviceCodes();
  homeSpan.setLogLevel(-1);
  homeSpan.setSerialInputDisable(true);
  homeSpan.setSketchVersion(VERSION);
  homeSpan.setApFunction(provisionWiFi);
  homeSpan.enableAutoStartAP();
  homeSpan.begin(Category::ProgrammableSwitches, "PyPortal Lamp Buttons",
                 "pyportal", "PyPortal");
  // begin() opens HomeSpan's NVS namespace before this call.
  homeSpan.setPairingCode(pairingCode);

  new SpanAccessory();
    new Service::AccessoryInformation();
      new Characteristic::Identify();
      new Characteristic::Name("PyPortal Lamp Buttons");
      new Characteristic::Manufacturer("pylcars");
      new Characteristic::Model("PyPortal");
      new Characteristic::SerialNumber(serialNumber);
      new Characteristic::FirmwareRevision(VERSION);
    new Service::StatelessProgrammableSwitch();
      buttons[0] = new Characteristic::ProgrammableSwitchEvent();
      new Characteristic::ServiceLabelIndex(1);
    new Service::StatelessProgrammableSwitch();
      buttons[1] = new Characteristic::ProgrammableSwitchEvent();
      new Characteristic::ServiceLabelIndex(2);
  sendStatus();
}

void loop() {
  homeSpan.poll();
  readCommands();
  if (setupRequested) provisionWiFi();
  if (millis() - lastStatusTime >= 1000) sendStatus();
  delay(2);
}
