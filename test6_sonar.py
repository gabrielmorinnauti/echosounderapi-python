import re
import csv
import time
from echosndr import DualEchosounder

''' Configuration '''
PORT = "COM10"
BAUD = 115200
CSV_PATH = "releve_bathymetrique_dual.csv"

# OMIT
last_data = {
    "H": { # 200 kHz
        "frequency": 200,
        "depth": 0.0,
        "temperature": 0.0,
        "datetime": "2025-01-01T00:00:00Z",
        "raw_data" : ""
    },
    "L": { # 30 kHz
        "frequency": 30,
        "depth": 0.0,
        "temperature": 0.0,
        "datetime": "2025-01-01T00:00:00Z",
        "raw_data" : ""
    },
    "gps": {
        "lat": 1.0,
        "lon": 1.0
    }
}

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

print("✅ Sonar détecté")
sonar.SetCurrentTime()                     # Synchro horloge
sonar.SendCommand("IdSetDualFreq")         # Mode double fréquence
sonar.SetValue("IdOutput", "3")
sonar.SetValue("IdInterval", "0.5")
sonar.SetValue("IdNMEAXDR", "1")  # Active trames XDR (pitch/roll/EMA)
sonar.SetValue("IdNMEAMTW", "1")  # Température
sonar.SetValue("IdNMEADBT", "1")  # Profondeur
sonar.Start()

print("✅ Adjusting settings")
# Adds other settings by looping through them
for setting in defaultSettings:
    for command in defaultSettings[setting]:
        value = defaultSettings[setting][command]
        sonar.SetValue(command, str(value))
        print(f"Set {command}: {value}")

print("📡 Acquisition dual fréquence lancée...")

# === Initialisation CSV ===
csvfile = open(CSV_PATH, "w", newline="")
writer = csv.writer(csvfile)
writer.writerow(["Lat ", "Lon ", 
                 "Date (UTC)", "Heure UTC", 
                 "Frequency", "Depth (m)", 
                 "Temp eau (deg C)", 
                 "EMA (%)", "Pitch (deg)", 
                 "Roll (deg)"])

# === Variables globales ===
zda_time = None
temp_c = None
last_depths = []
pitch = None
roll = None
ema = None
freq = None

# === Utility Methods ===
def _parse_freq(line):
    global freq
    # Try multiple patterns to catch different frequency formats
    patterns = [
        r"#F (\d+)\s+Hz\*55",           # Your current pattern
        r"#F (\d+)\s*Hz",               # Without checksum
        r"#F\s*(\d+)\s*Hz",             # With variable spacing
        r"#F\s*(\d+)",                  # Just frequency number
    ]

    for pattern in patterns:
        m = re.match(pattern, line)
        if m:
            freq = str(m.group(1))
            return
    

def _parse_zda(line):
    global zda_time
    m = re.match(r"\$SDZDA,(\d{2})(\d{2})(\d{2}\.\d+),(\d{2}),(\d{2}),(\d{4})", line)
    # TODO: Local time is UTC time, and UTC time is local time
    if m:
        hour, minute, second, day, month, year = m.groups()
        utc_time_str = f"{hour}:{minute}:{second[:5]}"          # hh:mm:ss.ss
        utc_date_str = f"{year}-{month}-{day}"                  # yyyy-mm-dd
        local_time_str = time.strftime("%H:%M:%S", time.localtime())
        zda_time = (utc_date_str, local_time_str, utc_time_str)

def _parse_mtw(line):
    global temp_c
    m = re.match(r"\$SDMTW,([\d.]+),C", line)
    if m:
        temp_c = float(m.group(1))

def _parse_dbt(line):
    global last_depths
    m = re.match(r"\$SDDBT,[\d.]+,f,([\d.]+),M", line)
    if m:
        depth = float(m.group(1))
        if zda_time and temp_c is not None:
            writer.writerow([
                last_data["gps"]["lat"], last_data["gps"]["lon"], 
                zda_time[0], zda_time[1],
                freq, depth, temp_c,
                ema, pitch, roll
            ])

def _parse_xdr(line):
    global pitch, roll, ema
    # Pitch & Roll
    if "PTCH" in line:
        try:
            parts = line.split(",")
            pitch = float(parts[2])
            roll = float(parts[6])
        except (IndexError, ValueError):
            pass

    # EMA (signal max)
    elif "EMA" in line:
        try:
            parts = line.split(",")
            ema = float(parts[2])
        except (IndexError, ValueError):
            pass

# === Boucle principale ===
try:
    while True:
        raw = sonar.ReadData(256)
        if raw:
            lines = raw.decode("latin_1", errors="ignore").splitlines()
            for line in lines:
                if "$SDZDA" in line:
                    _parse_zda(line)
                elif "$SDDBT" in line:
                    _parse_dbt(line)
                elif "$SDMTW" in line:
                    _parse_mtw(line)
                elif "$SDXDR" in line:
                    _parse_xdr(line)
                elif "#F" in line:
                    _parse_freq(line)     
        time.sleep(1.0)

except KeyboardInterrupt:
    print("\n🛑 Fin du relevé. Fichier sauvegardé.")
    csvfile.close()
    sonar.Stop()
