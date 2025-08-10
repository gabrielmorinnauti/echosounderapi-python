import re
import csv
import time
from echosndr import DualEchosounder
from datetime import date
from datetime import datetime

today = date.today()
formatted_date = today.strftime("%d-%m-%Y")
current_datetime = datetime.now()
formatted_time = current_datetime.strftime("%Hh%M")

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
    "Tx Length, us": {
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
    "-20dB Attenuator, us": {
        "IdAttnH": 200,
        "IdAttnL": 200,
    },
    "Deadzone, mm": {
        "IdDeadzoneH": 500,
        "IdDeadzoneL": 500,
    },
    "Threshold, %": {
        "IdThresholdH": 10,
        "IdThresholdL": 10,
    },
    "Offset, mm": {
        "IdOffsetH": 150,
        "IdOffsetL": 150,
    },
    "Sounds speed, m/s": {
        "IdSound": 1500.0
    }
}

# --- AJOUT 1 (modifié): helpers pour écrire l'entête ---

def _iter_defaultsettings_lines(defaults: dict):
    """Génère des lignes texte à partir de defaultSettings (sans préfixe #)."""
    for group, kv in defaults.items():
        yield f"{group}"
        for k, v in kv.items():
            yield f"  {k}: {v}"

def write_defaultsettings_header(fh, freq_label: str, defaults: dict):
    """Écrit au début du .log un en-tête clair avec les paramètres d'analyse."""
    P = "// "  # <-- préfixe 'comment' inoffensif pour ton spectro
    fh.write(f"{P}==============================================\n")
    fh.write(f"{P}Sonar analysis parameters — {freq_label}\n")
    for line in _iter_defaultsettings_lines(defaults):
        fh.write(P + line + "\n")
    fh.write(f"{P}==============================================\n\n")
    fh.flush()

import csv

def _params_for_freq(defaults: dict, freq_hz: int) -> dict:
    """Retourne un dict {param: value} pour la fréquence demandée.
       H -> 200 kHz, L -> 30 kHz. Les clés sans suffixe sont gardées.
    """
    is_high = (freq_hz == 200000)
    out = {}
    for group, kv in defaults.items():
        for key, val in kv.items():
            if key.endswith('H') or key.endswith('L'):
                base, suff = key[:-1], key[-1]
                if (suff == 'H' and is_high) or (suff == 'L' and not is_high):
                    out.setdefault(group, {})[base] = val
            else:
                out.setdefault(group, {})[key] = val
    return out

def write_meta_csv(csv_path: str, freq_hz: int, defaults: dict):
    """Écrit un CSV: freq_hz,group,param,value (uniquement defaultSettings mappés)."""
    rows = []
    by_group = _params_for_freq(defaults, freq_hz)
    for group, params in by_group.items():
        for param, value in params.items():
            rows.append([freq_hz, group, param, value])
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["freq_hz", "group", "param", "value"])
        w.writerows(rows)




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
    #filename_200 = f"200kHzsonar_m{timestamp.tm_min}_s{timestamp.tm_sec}.log"
    #filename_30 = f"30kHzsonar_m{timestamp.tm_min}_s{timestamp.tm_sec}.log"

    # juste avant d'ouvrir tes .log
    #with open(f"200kHzsonar_{formatted_date}_{formatted_time}.meta", "w") as meta200, \
       # open(f"30kHzsonar_{formatted_date}_{formatted_time}.meta", "w") as meta30:
       # write_defaultsettings_header(meta200, "200 kHz", defaultSettings)
        #write_defaultsettings_header(meta30,  "30 kHz",  defaultSettings)

    # --- NOUVEAU: écrire les métadonnées dans des CSV séparés ---
    meta_200 = f"200kHzsonar_{formatted_date}_{formatted_time}_meta.csv"
    meta_30  = f"30kHzsonar_{formatted_date}_{formatted_time}_meta.csv"
    write_meta_csv(meta_200, 200000, defaultSettings)
    write_meta_csv(meta_30,   30000,  defaultSettings)

    filename_200 = f"200kHzsonar_{formatted_date}_{formatted_time}.log"
    filename_30 = f"30kHzsonar_{formatted_date}_{formatted_time}.log"

    with open(filename_200, "w") as sonarLogs200kHz, \
        open(filename_30, "w") as sonarLogs30kHz:
        
        # --- AJOUT 2: écrire l'entête dans chaque fichier log ---
        #write_defaultsettings_header(sonarLogs200kHz, "200 kHz", defaultSettings)
        #write_defaultsettings_header(sonarLogs30kHz,  "30 kHz",  defaultSettings)

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