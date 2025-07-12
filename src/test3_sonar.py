import re
import csv
import time
from datetime import datetime
from ..libraries.echosndr import DualEchosounder
import threading
import os


class EchoSounderBridge():
    def __init__(self, port, baud, CSV_PATH):
        # sonar connection
        self.port = port
        self.baud = baud
        self.CSV_PATH = CSV_PATH
        # Used to log data
        self.sonar = None
        self.zda_time = None
        self.temp_c = None
        self.last_depths = []
        self.csvfile = None
        self.writer = None
        self._thread = None
        self._stop_event = threading.Event()
        self._csv_error = None
        self._lock = threading.Lock()

        self.make_new_csv_file(self.CSV_PATH)

    def make_new_csv_file(self, CSV_PATH):
        # Check output directory exists
        output_dir = os.path.dirname(CSV_PATH)
        if output_dir and not os.path.exists(output_dir):
            self._csv_error = f"❌ Output directory does not exist: {output_dir}"
            return
        try:
            self.csvfile = open(CSV_PATH, "w", newline="")
            self.writer = csv.writer(self.csvfile)
            self.writer.writerow(["Date (UTC)", "Heure UTC", "Heure locale", "HF (m)", "LF (m)", "Température eau (°C)"])
        except Exception as e:
            self._csv_error = f"❌ Could not create CSV file: {e}"

    # === Connexion sonar ===
    def connectToSonar(self):
        if self._csv_error:
            return self._csv_error
        
        try:
            self.sonar = DualEchosounder(self.port, self.baud)
        except Exception as e:
            return f"❌ Port non accessible: {e}"
        if not self.sonar.IsDetected():
            return "❗ Sonar non détecté"
        try:
            self.sonar.SetCurrentTime()                     # Synchro horloge
            self.sonar.SendCommand("IdSetDualFreq")         # Mode double fréquence
            self.sonar.SetValue("IdOutput", "3")
            self.sonar.SetValue("IdInterval", "0.5")
            self.sonar.Start()
        except Exception as e:
            return f"❌ Erreur lors de la configuration du sonar: {e}"
        return None

    # === Boucle de lecture ===
    def writeToCSV(self):
        if self._thread and self._thread.is_alive():
            print("Thread already running.")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._write_loop)
        self._thread.start()

    def _write_loop(self):
        try:
            while not self._stop_event.is_set():
                raw = self.sonar.ReadData(256)
                if raw:
                    lines = raw.decode("latin_1", errors="ignore").splitlines()
                    for line in lines:
                        if "$SDZDA" in line:
                            self._parse_zda(line)
                        elif "$SDDBT" in line:
                            self._parse_dbt(line)
                        elif "$SDMTW" in line:
                            self._parse_mtw(line)
                time.sleep(0.05)
        except Exception as e:
            print(f"Error in thread: {e}")
        finally:
            print("\n🛑 Fin du relevé. Fichier sauvegardé.")
            if self.csvfile:
                self.csvfile.close()
            if self.sonar:
                self.sonar.Stop()

    def stopWritingToCSV(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join()

    # === Utility Methods (thread-safe) ===
    def _parse_zda(self, line):
        m = re.match(r"\$SDZDA,(\d{2})(\d{2})(\d{2}\.\d+),(\d{2}),(\d{2}),(\d{4})", line)
        if m:
            hour, minute, second, day, month, year = m.groups()
            utc_time_str = f"{hour}:{minute}:{second[:5]}"          # hh:mm:ss.ss
            utc_date_str = f"{year}-{month}-{day}"                  # yyyy-mm-dd
            local_time_str = time.strftime("%H:%M:%S", time.localtime())
            with self._lock:
                self.zda_time = (utc_date_str, utc_time_str, local_time_str)

    def _parse_dbt(self, line):
        m = re.match(r"\$SDDBT,[\d.]+,f,([\d.]+),M", line)
        if m:
            depth = float(m.group(1))
            with self._lock:
                self.last_depths.append(depth)
                if len(self.last_depths) == 2 and self.zda_time and self.temp_c is not None:
                    # Écriture CSV
                    self.writer.writerow([
                        self.zda_time[0], self.zda_time[1], self.zda_time[2],
                        self.last_depths[0], self.last_depths[1], self.temp_c
                    ])
                    print(f"[{self.zda_time[1]} | Loc: {self.zda_time[2]}] HF: {self.last_depths[0]:.2f} m | LF: {self.last_depths[1]:.2f} m | 🌡️ {self.temp_c:.1f} °C")
                    self.last_depths = []

    def _parse_mtw(self, line):
        m = re.match(r"\$SDMTW,([\d.]+),C", line)
        if m:
            with self._lock:
                self.temp_c = float(m.group(1))
