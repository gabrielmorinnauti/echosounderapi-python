"""Wrapper to proccess data from Dual Echosounder API

Sources:
- API | https://github.com/Echologger/echosounderapi-python/blob/main/Echosounder_commands.md
- Handling NMEA strings | https://actisense.com/wp-content/uploads/2020/01/NMEA-0183-Information-sheet-issue-4-1-1.pdf?srsltid=AfmBOoq3hSo_MP1TLlfYdXYPT6Eau0DEdbwHbn8h0Fksh80b93EzRdZ6
"""
from loguru import logger
import asyncio
import re
import csv
import time
from datetime import datetime
import threading
import os
import tempfile
import atexit
from collections import deque

from app.config import DEBUG, DEBUG_CONFIG
if DEBUG:
    from app.libs.debugDualEchosounder import DualEchosounder
    import app.services.mockGPS as gps_service
    logger.info("🐛 DEBUG MODE: Using mock services")
else:
    from app.libs.echosndr import DualEchosounder
    import app.services.gps_service as gps_service

# Constants
BAUD = 115200

# Globals
sonar: DualEchosounder = None
csvfile = None
lastUSB = None
writer = None  
_data_thread = None
_parse_thread = None
_csv_thread = None
_stop_event = threading.Event()
_csv_flag = threading.Event()
_lock = threading.Lock()
_raw_data_queue = deque(maxlen=1000)  # Store recent raw data
_raw_file = None

# Current parsed readings
current_reading = {
    "gps": {"lat": 0.0, "lon": 0.0},
    "datetime": {"utc_date": "", "local_time": "", "utc_time": ""},
    "depth": 0.0,
    "temperature": 0.0,
    "frequency": "",
    "ema": 0.0,
    "pitch": 0.0,
    "roll": 0.0,
    "timestamp": time.time()
}

DEFAULT_SETTINGS = {
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
    },
}

def connectSonar(usb: str, newSettings: dict):
    """Connects to the DualEchosounder API from usb path"""
    global sonar, DEFAULT_SETTINGS, _data_thread, _parse_thread, _raw_file
    
    if DEBUG: 
        sonar = DualEchosounder(usb, 115200)
        _start_data_collection()
        return

    if sonar is not None and sonar.IsDetected():
        logger.info("Sonar device already connected")
        return
    try:
        logger.info("Connecting to sonar device...")
        if not usb or not isinstance(usb, str):
            raise ValueError("Invalid USB port specified")
        
        sonar = DualEchosounder(usb, BAUD)
    except ValueError as e:
        logger.error(f"Invalid port configuration - {e}")
        raise RuntimeError(e)
    except PermissionError as e:
        logger.error(f"Permission denied accessing port {usb} - {e}")
        raise RuntimeError(e)
    except Exception as e:
        logger.error(f"Failed to connect to port {usb} - {e}")
        raise RuntimeError(e)

    try:
        detected = sonar.Detect()
        if not detected:
            sonar = None
            logger.error("No sonar device detected")
            raise RuntimeError("The device is not a sonar")
    except Exception as e:
        logger.error(f"Device detection failed - {e}")
        raise RuntimeError(e)

    sonar.SetCurrentTime()
    sonar.SendCommand("IdSetDualFreq")
    sonar.SetValue("IdOutput", "3")
    sonar.SetValue("IdNMEADBT", "1")
    sonar.SetValue("IdNMEAMTW", "1")
    sonar.SetValue("IdNMEAXDR", "1")
    sonar.SetValue("IdNMEAEMA", "1")
    sonar.SetValue("IdNMEAZDA", "1")

    for setting in DEFAULT_SETTINGS:
        for command in DEFAULT_SETTINGS[setting]:
            value = DEFAULT_SETTINGS[setting][command]
            if setting in newSettings and command in newSettings[setting]:
                value = newSettings[setting][command]
            
            if value is not None and value != "":
                sonar.SetValue(command, str(value))
    
    _start_data_collection()
    logger.info("Sonar device detected successfully")
    return DualEchosounder.GetSerialPort

def _start_data_collection():
    """Start the main data collection and parsing threads"""
    global _data_thread, _parse_thread, _raw_file
    
    with _lock:
        if _data_thread and _data_thread.is_alive():
            return
        
        # Create raw data file
        timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
        raw_filename = f"{timestamp}_raw_sonar_data.txt"
        output_dir = os.getcwd()
        try:
            preferred_dir = os.path.join(os.getcwd(), "sonar_output")
            os.makedirs(preferred_dir, exist_ok=True)
            output_dir = preferred_dir
        except:
            pass
        
        raw_file_path = os.path.join(output_dir, raw_filename)
        _raw_file = open(raw_file_path, "w")
        
        _stop_event.clear()
        _data_thread = threading.Thread(target=_data_collection_loop, daemon=True)
        _parse_thread = threading.Thread(target=_parse_loop, daemon=True)
        
        _data_thread.start()
        _parse_thread.start()
        
        logger.info(f"Data collection started, raw data file: {raw_file_path}")

def _data_collection_loop():
    """Main thread that collects raw data and stores it in file and queue"""
    global sonar, _raw_file
    
    if not sonar.Start():
        logger.error("Failed to start sonar")
        return
    
    try:
        while not _stop_event.is_set():
            try:
                raw = sonar.ReadData(256)
                if raw:
                    decoded_data = raw.decode("latin_1", errors="ignore")
                    timestamp = time.time()
                    
                    # Write to file with timestamp
                    _raw_file.write(f"[{timestamp}] {decoded_data}\n")
                    _raw_file.flush()
                    
                    # Add to queue for parsing
                    _raw_data_queue.append((timestamp, decoded_data))
                
                time.sleep(0.01)
                    
            except Exception as e:
                logger.error(f"Error in data collection: {e}")
                if "permission" in str(e).lower() or "device" in str(e).lower():
                    break
                time.sleep(0.1)
                
    except Exception as e:
        logger.error(f"Critical error in data collection: {e}")
    finally:
        try:
            if sonar:
                sonar.Stop()
            if _raw_file:
                _raw_file.close()
        except:
            pass

def _parse_loop():
    """Thread that continuously parses the latest raw data"""
    global current_reading, _raw_data_queue
    
    while not _stop_event.is_set():
        try:
            # Update GPS position
            try:
                asyncio.run(_update_gps())
            except:
                pass
            
            # Process latest raw data
            while _raw_data_queue:
                timestamp, raw_data = _raw_data_queue.popleft()
                lines = raw_data.splitlines()
                
                for line in lines:
                    if "$SDZDA" in line:
                        _parse_zda_to_dict(line)
                    elif "$SDDBT" in line:
                        _parse_dbt_to_dict(line)
                    elif "$SDMTW" in line:
                        _parse_mtw_to_dict(line)
                    elif "$SDXDR" in line:
                        _parse_xdr_to_dict(line)
                    elif "#F" in line:
                        _parse_freq_to_dict(line)
                
                with _lock:
                    current_reading["timestamp"] = timestamp
            
            time.sleep(0.05)
            
        except Exception as e:
            logger.error(f"Error in parsing loop: {e}")
            time.sleep(0.1)

async def _update_gps():
    """Update GPS position in current reading"""
    try:
        gps_data = await gps_service.get_gps_points()
        with _lock:
            current_reading["gps"]["lat"] = gps_data["lat"]
            current_reading["gps"]["lon"] = gps_data["lon"]
    except:
        pass

def _parse_freq_to_dict(line):
    patterns = [
        r"#F (\d+)\s+Hz\*55",
        r"#F (\d+)\s*Hz",
        r"#F\s*(\d+)\s*Hz",
        r"#F\s*(\d+)",
    ]
    
    for pattern in patterns:
        m = re.match(pattern, line)
        if m:
            with _lock:
                current_reading["frequency"] = str(m.group(1))
            return

def _parse_zda_to_dict(line):
    m = re.match(r"\$SDZDA,(\d{2})(\d{2})(\d{2}\.\d+),(\d{2}),(\d{2}),(\d{4})", line)
    if m:
        hour, minute, second, day, month, year = m.groups()
        utc_time_str = f"{hour}:{minute}:{second[:5]}"
        utc_date_str = f"{year}-{month}-{day}"
        local_time_str = time.strftime("%H:%M:%S", time.localtime())
        with _lock:
            current_reading["datetime"]["utc_date"] = utc_date_str
            current_reading["datetime"]["local_time"] = local_time_str
            current_reading["datetime"]["utc_time"] = utc_time_str

def _parse_mtw_to_dict(line):
    m = re.match(r"\$SDMTW,([\d.]+),C", line)
    if m:
        with _lock:
            current_reading["temperature"] = float(m.group(1))

def _parse_dbt_to_dict(line):
    m = re.match(r"\$SDDBT,[\d.]+,f,([\d.]+),M", line)
    if m:
        with _lock:
            current_reading["depth"] = float(m.group(1))

def _parse_xdr_to_dict(line):
    if "PTCH" in line:
        try:
            parts = line.split(",")
            with _lock:
                current_reading["pitch"] = float(parts[2])
                current_reading["roll"] = float(parts[6])
        except (IndexError, ValueError):
            pass
    elif "EMA" in line:
        try:
            parts = line.split(",")
            with _lock:
                current_reading["ema"] = float(parts[2])
        except (IndexError, ValueError):
            pass

def getCurrentReading():
    """Return the current parsed readings"""
    with _lock:
        return current_reading.copy()

def writeToCSVFile(usb: str, csv_name, settings):
    global csvfile, writer, _csv_thread, sonar, lastUSB, _csv_flag

    logger.info("Starting CSV file creation...")

    if not sonar:
        raise RuntimeError("Must connect to sonar by calling connectSonar(usb: str, newSettings: dict).")

    # Directory and file setup
    output_dir = os.getcwd()
    try:
        preferred_dir = os.path.join(os.getcwd(), "sonar_output")
        os.makedirs(preferred_dir, exist_ok=True)
        output_dir = preferred_dir
    except:
        pass
    
    timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
    csv_filename = f"{timestamp}_{csv_name}.csv"
    csv_path = os.path.join(output_dir, csv_filename)
    
    try:
        with _lock:
            if _csv_thread and _csv_thread.is_alive():
                stopWritingToCSV()
        
        try:
            with open(csv_path, "w") as test_file:
                pass
            os.remove(csv_path)
        except PermissionError:
            temp_dir = tempfile.gettempdir()
            csv_path = os.path.join(temp_dir, csv_filename)
        
        lastUSB = usb
        csvfile = open(csv_path, "w", newline="")
        writer = csv.writer(csvfile)
        writer.writerow(["Lat ", "Lon ", "Date (UTC)", "Heure UTC", "Frequency", "Depth (m)", "Temp eau (deg C)", "EMA (%)", "Pitch (deg)", "Roll (deg)"])
        
        _csv_flag.set()
        _csv_thread = threading.Thread(target=_csv_write_loop, daemon=True)
        _csv_thread.start()
        
        logger.info(f"CSV file created: {csv_path}")
        return csv_path
        
    except Exception as e:
        logger.error(f"Failed to start CSV writing: {e}")
        cleanup_resources()
        raise RuntimeError(f"Failed to start CSV writing: {e}")

def _csv_write_loop():
    """Thread that writes current readings to CSV when flag is set"""
    global csvfile, writer, current_reading
    
    while _csv_flag.is_set() and not _stop_event.is_set():
        try:
            with _lock:
                reading = current_reading.copy()
            
            if (reading["datetime"]["utc_date"] and 
                reading["temperature"] > 0 and 
                reading["depth"] > 0):
                
                writer.writerow([
                    reading["gps"]["lat"], 
                    reading["gps"]["lon"], 
                    reading["datetime"]["utc_date"], 
                    reading["datetime"]["local_time"],
                    reading["frequency"], 
                    reading["depth"], 
                    reading["temperature"],
                    reading["ema"], 
                    reading["pitch"], 
                    reading["roll"]
                ])
                csvfile.flush()
            
            time.sleep(1.0)  # Write every second
            
        except Exception as e:
            logger.error(f"Error in CSV writing: {e}")
            time.sleep(0.1)

atexit.register(lambda: cleanup_resources())

def cleanup_resources():
    """Emergency cleanup function"""
    global _data_thread, _parse_thread, _csv_thread, csvfile, writer, sonar, _stop_event, _raw_file
    
    logger.info("Cleaning up resources...")
    
    _stop_event.set()
    _csv_flag.clear()
    
    for thread in [_data_thread, _parse_thread, _csv_thread]:
        if thread and thread.is_alive():
            thread.join(timeout=3.0)
    
    try:
        if sonar and hasattr(sonar, 'Stop'):
            sonar.Stop()
    except:
        pass
    
    try:
        if csvfile:
            csvfile.close()
        if _raw_file:
            _raw_file.close()
    except:
        pass
    
    globals().update({
        '_data_thread': None,
        '_parse_thread': None,
        '_csv_thread': None,
        'csvfile': None,
        'writer': None,
        '_raw_file': None
    })

def getActiveCSV():
    try:
        with _lock:
            if _csv_thread and _csv_thread.is_alive():
                return {"csvFilePath": csvfile.name, "activeUSB": lastUSB, "settings": DEFAULT_SETTINGS}
            else: 
                return { "settings": DEFAULT_SETTINGS }
    except Exception as e:
        logger.error(f"Failed to find CSV: {e}")
        cleanup_resources()
        return None

def stopWritingToCSV():
    """Stop CSV writing"""
    global _csv_thread, csvfile, writer
    
    logger.info("Stopping CSV writing...")
    
    _csv_flag.clear()
    
    file_path = None
    
    if _csv_thread and _csv_thread.is_alive():
        _csv_thread.join(timeout=5.0)
    
    try:
        if csvfile:
            file_path = csvfile.name
            csvfile.close()
    except Exception as e:
        logger.error(f"Error closing CSV file: {e}")
    
    csvfile = None
    writer = None
    _csv_thread = None
    
    return file_path
