import re
import csv
import time
from echosndr import DualEchosounder

''' Configuration '''
PORT = "COM10"
BAUD = 115200

''' Sonar Connection & Update Parameters'''
try:
    sonar = DualEchosounder(PORT, BAUD)
except:
    print("❌ Port non accessible")
    exit()

if not sonar.IsDetected():
    print("❗ Sonar non détecté")
    exit()
print("✅ Sonar détecté")
sonar.Stop()
print("✅ Sonar arrêté")