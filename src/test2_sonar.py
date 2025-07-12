import re
import csv
import time
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
sonar.SetCurrentTime()

pc_time_utc = time.strftime("%H:%M:%S", time.gmtime())
pc_time_local = time.strftime("%H:%M:%S", time.localtime())

print("🕒 Heure PC UTC :", pc_time_utc)
print("🕒 Heure PC locale (Québec) :", pc_time_local)
print("🕒 Heure sonar (via trame SDZDA) : voir dans les logs")           
    # Synchro horloge
sonar.SendCommand("IdSetDualFreq")         # Mode double fréquence
sonar.SetValue("IdOutput", "3")
sonar.SetValue("IdInterval", "0.5")
sonar.Start()
print("📡 Acquisition dual fréquence lancée...")

# === Initialisation CSV ===
csvfile = open(CSV_PATH, "w", newline="")
writer = csv.writer(csvfile)
writer.writerow(["Date", "Heure UTC", "Profondeur_HF (m)", "Profondeur_LF (m)"])

# === Parsing et Logging ===
zda_time = None
last_depths = []

def parse_zda(line):
    global zda_time
    m = re.match(r"\$SDZDA,(\d{2})(\d{2})(\d{2}\.\d+),(\d{2}),(\d{2}),(\d{4})", line)
    if m:
        hour, minute, sec, day, month, year = m.groups()
        time_str = f"{hour}:{minute}:{sec[:5]}"  # hh:mm:ss.ss
        date_str = f"{year}-{month}-{day}"       # yyyy-mm-dd
        zda_time = (date_str, time_str)

def parse_dbt(line):
    global last_depths
    m = re.match(r"\$SDDBT,[\d.]+,f,([\d.]+),M", line)
    if m:
        depth = float(m.group(1))
        last_depths.append(depth)
        if len(last_depths) == 2 and zda_time:
            # Écriture CSV
            writer.writerow([zda_time[0], zda_time[1], last_depths[0], last_depths[1]])
            print(f"[{zda_time[1]}] HF: {last_depths[0]:.2f} m | LF: {last_depths[1]:.2f} m")
            last_depths = []

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
        time.sleep(0.05)

except KeyboardInterrupt:
    print("\n🛑 Fin du relevé. Fichier sauvegardé.")
    csvfile.close()
    sonar.Stop()
