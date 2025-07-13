"""
To integrate to sonar_service.py as an extension:
1) Replace all print staments with logger.info
2) Replace all print(f"Error: {e}") with logger.error
3) Add the following imports
from loguru import logger
from app.libs.echosndr import DualEchosounder
import app.services.gps_service as gps_service
4) Remove irrelevant imports
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "libraries"))
from echosndr import DualEchosounder
import asyncio
import re
import csv
import time
from datetime import datetime
import threading
import os

csvfile = None
writer = None  
_thread = None
_stop_event = threading.Event()
_lock = threading.Lock()

zda_time = None
temp_c = None
last_depths = []

sonar: DualEchosounder = None
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
        "lat": 0.0,
        "lon": 0.0
    }
}

def connectSonar(usb: str):
    global sonar

    if sonar is not None and sonar.IsDetected():
        print("Sonar device already connected")
        return

    try:
        print("Connecting to sonar device...")
        # Add validation for port format
        if not usb or not isinstance(usb, str):
            raise ValueError("Invalid USB port specified")
        
        sonar = DualEchosounder(usb, 115200)
    except ValueError as e:
        print(f"Error: Invalid port configuration - {e}")
        raise RuntimeError(e)
    except PermissionError as e:
        print(f"Error: Permission denied accessing port {usb} - {e}")
        raise RuntimeError(e)
    except Exception as e:
        print(f"Error: Failed to connect to port {usb} - {e}")
        raise RuntimeError(e)

    try:
        detected = sonar.Detect()
        if not detected:
            print("Error: No sonar device detected")
            raise RuntimeError("The device is not a sonar")
    except Exception as e:
        print(f"Error: Device detection failed - {e}")
        raise RuntimeError(e)

    sonar.SetCurrentTime()
    sonar.SendCommand("IdSetDualFreq")
    sonar.SetValue("IdOutput", "3")
    sonar.SetValue("IdInterval", "1")
    print("Sonar device detected successfully")

def writeToCSVFile(usb: str, csv_name):
    global csvfile, writer, _thread, sonar
    connectSonar(usb)

    # Create output directory with better error handling
    output_dir = os.getcwd()  # Start with current directory as fallback
    
    try:
        # Try to create sonar_output subdirectory
        preferred_dir = os.path.join(os.getcwd(), "sonar_output")
        os.makedirs(preferred_dir, exist_ok=True)
        output_dir = preferred_dir
        print(f"Using output directory: {output_dir}")
    except PermissionError:
        print("Warning: Cannot create sonar_output directory, using current directory")
    except Exception as e:
        print(f"Warning: Directory creation failed: {e}, using current directory")
    
    # Create timestamped filename
    timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
    csv_filename = f"{timestamp}_{csv_name}.csv"
    csv_path = os.path.join(output_dir, csv_filename)
    
    try:
        with _lock:
            if _thread and _thread.is_alive():
                print("Error: Thread already running.")
                return csv_path
        
        # Test file write permissions before proceeding
        try:
            test_file = open(csv_path, "w")
            test_file.close()
            os.remove(csv_path)  # Clean up test file
        except PermissionError:
            # Try with a different filename in temp directory
            import tempfile
            temp_dir = tempfile.gettempdir()
            csv_path = os.path.join(temp_dir, csv_filename)
            print(f"Warning: Using temporary directory: {temp_dir}")
        
        csvfile = open(csv_path, "w", newline="")
        writer = csv.writer(csvfile)
        writer.writerow(["Date (UTC)", "Heure UTC", "Heure locale", "HF (m)", "LF (m)", "Température eau (°C)"])
        
        _stop_event.clear()
        _thread = threading.Thread(target=_write_loop)
        _thread.start()
        
        print(f"CSV file created: {csv_path}")
    except Exception as e:
        print(f"Error: {e}")
        raise RuntimeError(e)
    
    return csv_path
    
def stopWritingToCSV():
    global _thread, csvfile, writer
    _stop_event.set()
    if _thread:
        _thread.join()
    
    if csvfile:
        file_path = csvfile.name
        csvfile.close()
        csvfile = None  # Add this line
        writer = None   # Add this line
        return file_path
    
    return None

## Uses multithreading
def _write_loop():
    global csvfile, sonar
    try:
        while not _stop_event.is_set():
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
            time.sleep(0.05)
    except Exception as e:
        if csvfile:
            csvfile.close()
        print(f"Error: {e}")
        raise RuntimeError(e)
    finally:
        print("\n Fin du relevé. Fichier sauvegardé.")
        if csvfile:
            csvfile.close()
        
""" COMMENTED OUT FOR DEBUGGING 
## Uses continous readings
async def readSonarData():
    global sonar
    global last_data

    if sonar.Start():
        gps_data = await gps_service.get_gps_points()

        for i in range(2):
            serial = sonar.GetSerialPort()
            current_lines = ""
            current_freq = ""
            is_first = True
            while True:
                if serial.in_waiting > 0:
                    line = serial.readline().decode("latin_1").strip()
                    current_lines = current_lines + line + '\n'

                    line_type = ""
                    parts = []

                    if line.startswith('#F'):
                        line_type = "#F"
                        parts = line.split()
                        if len(parts) == 3 and parts[1].isdigit():
                            current_freq = "H" if int(parts[1]) == 200000 else "L"
                    elif line.startswith("$"):
                        parts = line.split(',')
                        line_type = parts[0]

                    if not current_freq == "":
                        if line_type == "$SDDBT":
                            last_data[current_freq]["depth"] = float(parts[3])
                        elif line_type == "$SDMTW":
                            last_data[current_freq]["temperature"] = float(parts[1])
                        elif line_type == "$SDZDA":
                            time_parts = parts[1].split('.') # hhmmss.ss
                            day = parts[2] # dd
                            month = parts[3] # mm
                            year = parts[4] # yyyy
                            last_data[current_freq]["datetime"] = f"{year}-{month}-{day}T{time_parts[0][:2]}:{time_parts[0][2:4]}:{time_parts[0][4:]}Z"

                    if "$SDXDR" in line:
                        if is_first:
                            is_first = False
                        else:
                            break
                else:
                    await asyncio.sleep(0.01)
            last_data[current_freq]["raw_data"] = current_lines.strip()
            last_data["gps"]["lat"] = gps_data["lat"]
            last_data["gps"]["lon"] = gps_data["lon"]
        sonar.Stop()
        logger.info("Sonar data retrieved successfully")

async def getSonarData(usb: str):
    global sonar

    connectSonar(usb)

    await readSonarData()

    return last_data
"""

# === Utility Methods (thread-safe) ===
def _parse_zda(line):
    global zda_time
    m = re.match(r"\$SDZDA,(\d{2})(\d{2})(\d{2}\.\d+),(\d{2}),(\d{2}),(\d{4})", line)
    if m:
        hour, minute, second, day, month, year = m.groups()
        utc_time_str = f"{hour}:{minute}:{second[:5]}"          # hh:mm:ss.ss
        utc_date_str = f"{year}-{month}-{day}"                  # yyyy-mm-dd
        local_time_str = time.strftime("%H:%M:%S", time.localtime())
        with _lock:
            zda_time = (utc_date_str, utc_time_str, local_time_str)

def _parse_mtw(line):
    global temp_c
    m = re.match(r"\$SDMTW,([\d.]+),C", line)
    if m:
        with _lock:
            temp_c = float(m.group(1))

def _parse_dbt(line):
    global last_depths
    m = re.match(r"\$SDDBT,[\d.]+,f,([\d.]+),M", line)
    if m:
        depth = float(m.group(1))
        with _lock:
            last_depths.append(depth)
            if len(last_depths) == 2 and zda_time and temp_c is not None:
                # Écriture CSV
                writer.writerow([
                    zda_time[0], zda_time[1], zda_time[2],
                    last_depths[0], last_depths[1], temp_c
                ])
                print(f"[{zda_time[1]} | Loc: {zda_time[2]}] HF: {last_depths[0]:.2f} m | LF: {last_depths[1]:.2f} m | 🌡️ {temp_c:.1f} °C")
                last_depths = []