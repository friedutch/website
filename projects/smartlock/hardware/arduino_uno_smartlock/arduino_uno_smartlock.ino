#include <Adafruit_Fingerprint.h>
#include <Keypad.h>
#include <SoftwareSerial.h>
#include <ctype.h>
#include <string.h>

const unsigned long ACCESS_RESULT_TIMEOUT_MS = 8000;
const unsigned long ACCESS_COOLDOWN_MS = 1500;
const unsigned long UNLOCK_DURATION_MS = 5000;
const uint32_t FINGERPRINT_BAUD_RATES[] = {57600, 9600};
const byte FINGERPRINT_BAUD_RATE_COUNT = sizeof(FINGERPRINT_BAUD_RATES) / sizeof(FINGERPRINT_BAUD_RATES[0]);

const byte ROWS = 4;
const byte COLS = 3;
const byte PASSCODE_LENGTH = 6;
const byte RFID_TAG_LENGTH = 12;

byte keypadRowPins[ROWS] = {9, 8, 7, 6};
byte keypadColPins[COLS] = {5, 4, 3};

const byte RFID_RX_PIN = A0;
const byte RFID_TX_PIN = A3;
const byte FINGERPRINT_RX_PIN = A1;
const byte FINGERPRINT_TX_PIN = A2;

const byte LOCK_RELAY_PIN = 2;
const byte STATUS_LED_PIN = 13;

char keypadMap[ROWS][COLS] = {
  {'1', '2', '3'},
  {'4', '5', '6'},
  {'7', '8', '9'},
  {'*', '0', '#'}
};

SoftwareSerial rfidSerial(RFID_RX_PIN, RFID_TX_PIN);
SoftwareSerial fingerprintSerial(FINGERPRINT_RX_PIN, FINGERPRINT_TX_PIN);
Adafruit_Fingerprint finger = Adafruit_Fingerprint(&fingerprintSerial);
Keypad keypad = Keypad(makeKeymap(keypadMap), keypadRowPins, keypadColPins, ROWS, COLS);

char passcodeBuffer[PASSCODE_LENGTH + 1] = {'\0'};
char rfidBuffer[RFID_TAG_LENGTH + 1] = {'\0'};
char pendingMethod[16] = {'\0'};
bool collectingPasscode = false;
bool awaitingBridgeResult = false;
bool lockIsOpen = false;
bool rfidFrameStarted = false;
byte passcodeLength = 0;
byte rfidLength = 0;
unsigned long lastAccessRequestAt = 0;
unsigned long unlockStartedAt = 0;
uint32_t activeFingerprintBaud = 0;

void clearPasscodeBuffer() {
  for (byte i = 0; i <= PASSCODE_LENGTH; i++) {
    passcodeBuffer[i] = '\0';
  }
  passcodeLength = 0;
}

void startPasscodeEntry() {
  collectingPasscode = true;
  clearPasscodeBuffer();
}

void cancelPasscodeEntry() {
  collectingPasscode = false;
  clearPasscodeBuffer();
}

bool cooldownActive() {
  return millis() - lastAccessRequestAt < ACCESS_COOLDOWN_MS;
}

void sendStatus(const char *value) {
  Serial.print("STATUS|");
  Serial.println(value);
}

void rememberPendingMethod(const char *method) {
  strncpy(pendingMethod, method, sizeof(pendingMethod) - 1);
  pendingMethod[sizeof(pendingMethod) - 1] = '\0';
}

void clearPendingMethod() {
  pendingMethod[0] = '\0';
}

void requestAccess(const char *method, const char *value) {
  if (awaitingBridgeResult || cooldownActive()) {
    return;
  }
  rememberPendingMethod(method);
  awaitingBridgeResult = true;
  lastAccessRequestAt = millis();
  Serial.print("CHECK|");
  Serial.print(method);
  Serial.print("|");
  Serial.println(value);
}

void unlockDoor() {
  digitalWrite(LOCK_RELAY_PIN, HIGH);
  digitalWrite(STATUS_LED_PIN, HIGH);
  lockIsOpen = true;
  unlockStartedAt = millis();
}

void lockDoor() {
  digitalWrite(LOCK_RELAY_PIN, LOW);
  digitalWrite(STATUS_LED_PIN, LOW);
  lockIsOpen = false;
}

void submitPasscode() {
  if (passcodeLength != PASSCODE_LENGTH) {
    sendStatus("PASSCODE_INCOMPLETE");
    cancelPasscodeEntry();
    return;
  }
  collectingPasscode = false;
  requestAccess("passcode", passcodeBuffer);
  clearPasscodeBuffer();
}

void pollKeypad() {
  char key = keypad.getKey();
  if (!key || awaitingBridgeResult) {
    return;
  }

  if (key == '*') {
    if (!collectingPasscode) {
      startPasscodeEntry();
      sendStatus("PASSCODE_START");
      return;
    }
    cancelPasscodeEntry();
    sendStatus("PASSCODE_CANCEL");
    return;
  }

  if (!collectingPasscode) {
    return;
  }

  if (key == '#') {
    submitPasscode();
    return;
  }

  if (key >= '0' && key <= '9' && passcodeLength < PASSCODE_LENGTH) {
    passcodeBuffer[passcodeLength] = key;
    passcodeLength++;
    passcodeBuffer[passcodeLength] = '\0';
    if (passcodeLength == PASSCODE_LENGTH) {
      submitPasscode();
    }
  }
}

void pollRfid() {
  if (awaitingBridgeResult || collectingPasscode) {
    return;
  }

  rfidSerial.listen();
  while (rfidSerial.available()) {
    int incoming = rfidSerial.read();
    if (incoming == 2) {
      rfidFrameStarted = true;
      rfidLength = 0;
      continue;
    }
    if (!rfidFrameStarted) {
      continue;
    }
    if (incoming == 3) {
      rfidBuffer[rfidLength] = '\0';
      rfidFrameStarted = false;
      if (rfidLength == RFID_TAG_LENGTH) {
        requestAccess("rfid", rfidBuffer);
      }
      rfidLength = 0;
      continue;
    }
    if (rfidLength < RFID_TAG_LENGTH) {
      char value = (char)incoming;
      if ((value >= '0' && value <= '9') || (value >= 'A' && value <= 'F') || (value >= 'a' && value <= 'f')) {
        rfidBuffer[rfidLength] = toupper(value);
        rfidLength++;
      }
    }
  }
}

int scanFingerprint() {
  fingerprintSerial.listen();
  uint8_t state = finger.getImage();
  if (state == FINGERPRINT_NOFINGER) {
    return -1;
  }
  if (state != FINGERPRINT_OK) {
    return 0;
  }

  state = finger.image2Tz();
  if (state != FINGERPRINT_OK) {
    return 0;
  }

  state = finger.fingerFastSearch();
  if (state == FINGERPRINT_OK) {
    return finger.fingerID;
  }
  if (state == FINGERPRINT_NOTFOUND) {
    return -2;
  }
  return 0;
}

void pollFingerprint() {
  if (awaitingBridgeResult || collectingPasscode || cooldownActive()) {
    return;
  }

  int fingerprintId = scanFingerprint();
  if (fingerprintId > 0) {
    char fingerprintValue[12];
    ltoa(fingerprintId, fingerprintValue, 10);
    requestAccess("fingerprint", fingerprintValue);
  } else if (fingerprintId == -2) {
    requestAccess("fingerprint", "0");
  }
}

void handleBridgeResult(const String &line) {
  if (line == "PONG") {
    return;
  }
  if (!line.startsWith("RESULT|")) {
    return;
  }

  int firstSeparator = line.indexOf('|', 7);
  String decision = firstSeparator == -1 ? line.substring(7) : line.substring(7, firstSeparator);
  awaitingBridgeResult = false;

  if (decision == "ALLOW") {
    unlockDoor();
    sendStatus("ACCESS_GRANTED");
  } else if (decision == "DENY") {
    sendStatus("ACCESS_DENIED");
  } else {
    sendStatus("ACCESS_ERROR");
  }
  clearPendingMethod();
}

void pollBridge() {
  if (!Serial.available()) {
    return;
  }
  String line = Serial.readStringUntil('\n');
  line.trim();
  if (line.length() == 0) {
    return;
  }
  handleBridgeResult(line);
}

void expirePendingRequest() {
  if (!awaitingBridgeResult) {
    return;
  }
  if (millis() - lastAccessRequestAt > ACCESS_RESULT_TIMEOUT_MS) {
    awaitingBridgeResult = false;
    clearPendingMethod();
    sendStatus("ACCESS_TIMEOUT");
  }
}

void refreshLockState() {
  if (lockIsOpen && millis() - unlockStartedAt >= UNLOCK_DURATION_MS) {
    lockDoor();
  }
}

bool initializeFingerprintSensor() {
  for (byte i = 0; i < FINGERPRINT_BAUD_RATE_COUNT; i++) {
    uint32_t baudRate = FINGERPRINT_BAUD_RATES[i];
    fingerprintSerial.begin(baudRate);
    fingerprintSerial.listen();
    finger.begin(baudRate);
    delay(150);
    if (finger.verifyPassword()) {
      activeFingerprintBaud = baudRate;
      return true;
    }
  }
  activeFingerprintBaud = 0;
  return false;
}

void setup() {
  pinMode(LOCK_RELAY_PIN, OUTPUT);
  pinMode(STATUS_LED_PIN, OUTPUT);
  lockDoor();

  Serial.begin(115200);
  Serial.setTimeout(25);
  rfidSerial.begin(9600);

  clearPasscodeBuffer();
  clearPendingMethod();

  if (initializeFingerprintSensor()) {
    sendStatus("READY");
  } else {
    sendStatus("FINGERPRINT_SENSOR_ERROR");
  }
}

void loop() {
  pollBridge();
  expirePendingRequest();
  refreshLockState();
  pollKeypad();
  pollRfid();
  pollFingerprint();
}
