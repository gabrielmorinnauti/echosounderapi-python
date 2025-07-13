import re
import csv
import time
from datetime import datetime
from echosndr import DualEchosounder

# === Configuration ===
PORT = "COM10"
BAUD = 115200
CSV_PATH = "releve_bathymetrique_dual.csv"

# === Connexion sonar ===
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
sonar.Start()
print("📡 Acquisition dual fréquence lancée...")

# === Initialisation CSV ===
csvfile = open(CSV_PATH, "w", newline="")
writer = csv.writer(csvfile)
writer.writerow(["Date (UTC)", "Heure UTC", "Heure locale", "HF (m)", "LF (m)", "Température eau (°C)"])

# === Variables globales ===
zda_time = None
temp_c = None
last_depths = []

def parse_zda(line):
    global zda_time
    m = re.match(r"\$SDZDA,(\d{2})(\d{2})(\d{2}\.\d+),(\d{2}),(\d{2}),(\d{4})", line)
    if m:
        hour, minute, second, day, month, year = m.groups()
        utc_time_str = f"{hour}:{minute}:{second[:5]}"          # hh:mm:ss.ss
        utc_date_str = f"{year}-{month}-{day}"                  # yyyy-mm-dd
        local_time_str = time.strftime("%H:%M:%S", time.localtime())
        zda_time = (utc_date_str, utc_time_str, local_time_str)

def parse_dbt(line):
    global last_depths
    m = re.match(r"\$SDDBT,[\d.]+,f,([\d.]+),M", line)
    if m:
        depth = float(m.group(1))
        last_depths.append(depth)
        if len(last_depths) == 2 and zda_time and temp_c is not None:
            # Écriture CSV
            writer.writerow([zda_time[0], zda_time[1], zda_time[2], last_depths[0], last_depths[1], temp_c])
            print(f"[{zda_time[1]} | Loc: {zda_time[2]}] HF: {last_depths[0]:.2f} m | LF: {last_depths[1]:.2f} m | 🌡️ {temp_c:.1f} °C")
            last_depths = []

def parse_mtw(line):
    global temp_c
    m = re.match(r"\$SDMTW,([\d.]+),C", line)
    if m:
        temp_c = float(m.group(1))

# === Boucle de lecture ===
try:
    while True:
        raw = sonar.ReadData(256)
        if raw:
            lines = raw.decode("latin_1", errors="ignore").splitlines()
            for line in lines:
                if "$SDZDA" in line:
                    parse_zda(line)
                elif "$SDDBT" in line:
                    parse_dbt(line)
                elif "$SDMTW" in line:
                    parse_mtw(line)
        time.sleep(0.05)

except KeyboardInterrupt:
    print("\n🛑 Fin du relevé. Fichier sauvegardé.")
    csvfile.close()
    sonar.Stop()
