import re
import csv
import time
from echosndr import DualEchosounder

''' Configuration '''
PORT = "COM10"
BAUD = 115200
CSV_PATH = "releve_bathymetrique_dual.csv"

defaultSettings = {
    "Range, m": {
        "IdRangeH": 2,
        "IdRangeL": 2,
    },
    "Interval, sec": {
        "IdInterval": 0.5,
    },
    "Tx Length, μs": {
        "IdTxLengthH": 300,
        "IdTxLengthL": 100,
    },
    "Tx Power, db": {
        "IdTxPower": 0,
    },
    "Gain, dB": {
        "IdGainH": 0,
        "IdGainL": 0,
    },
    "TVG spread coef.": {
        "IdTVGSprdH": 15,
        "IdTVGSprdL": 15,
    },
    "TVG absorb, dB/m": {
        "IdTVGAbsH": 0.006,
        "IdTVGAbsL": 0.05,
    },
    "-20dB Attenuator, μs": {
        "IdAttnH": 200,
        "IdAttnL": 200,
    },
    "Deadzone, mm": {
        "IdDeadzoneH": 1500,
        "IdDeadzoneL": 500,
    },
    "Threshold, %": {
        "IdThresholdH": 10,
        "IdThresholdL": 10,
    },
    "Offset, mm": {
        "IdOffsetH": 210,
        "IdOffsetL": 210,
    },
    "Sounds speed, m/s": {
        "IdSound": 1500.0
    }
}

''' Sonar Connection & Update Parameters'''
try:
    sonar = DualEchosounder(PORT, BAUD)
except:
    print("❌ Port non accessible")
    exit()

if not sonar.IsDetected():
    print("❗ Sonar non détecté")
    exit()

sonar.Stop()
print("✅ Sonar détecté")
sonar.SetCurrentTime()                     # Synchro horloge
sonar.SendCommand("IdSetDualFreq")         # Mode double fréquence
sonar.SetValue("IdOutput", "3")
sonar.SetValue("IdInterval", "0.5")
sonar.SetValue("IdNMEAXDR", "1")  # Active trames XDR (pitch/roll/EMA)
sonar.SetValue("IdNMEAMTW", "1")  # Température
sonar.SetValue("IdNMEADBT", "1")  # Profondeur

print("✅ Adjusting settings")
# Adds other settings by looping through them
for setting in defaultSettings:
    for command in defaultSettings[setting]:
        value = defaultSettings[setting][command]
        sonar.SetValue(command, str(value))
        print(f"Set {command}: {value}")

sonar.Start()
print("📡 Acquisition dual fréquence lancée...")



# === Boucle principale ===
try:
    timestamp = time.localtime()
    
    lastFrequency = 0
    filename_200 = f"200kHzsonar_m{timestamp.tm_min}_s{timestamp.tm_sec}.log"
    filename_30 = f"30kHzsonar_m{timestamp.tm_min}_s{timestamp.tm_sec}.log"

    with open(filename_200, "w") as sonarLogs200kHz, \
        open(filename_30, "w") as sonarLogs30kHz:
        
        while True:
            raw = sonar.ReadData(256)
            if raw:
                lines = raw.decode("latin_1", errors="ignore").splitlines()
                
                for line in lines:
                    if "#F" in line and "200000" in line:
                        lastFrequency = 200000
                    elif "#F" in line and "30000" in line:
                        lastFrequency = 30000

                    if lastFrequency == 200000:
                        sonarLogs200kHz.write(line + "\n")
                        sonarLogs200kHz.flush()
                    elif lastFrequency == 30000:
                        sonarLogs30kHz.write(line + "\n")
                        sonarLogs30kHz.flush()
            time.sleep(0.01)

except KeyboardInterrupt:
    print("\n🛑 Fin du relevé. Fichier sauvegardé.")
    sonar.Stop()
except Exception as e:
    print(f"\n❌ Erreur: {e}")
    sonar.Stop()
    raise