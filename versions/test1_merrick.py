# sonar_logger.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "libraries"))
from echosndr import DualEchosounder
import time
import threading
import sys
import msvcrt  # Windows only

PORT = "\\\\.\\COM10"  # Update this if your port changes
BAUD = 115200
OUTPUT_FILE = "sonar_log.txt"
LOG_INTERVAL = 0.2  # seconds between reads

def keyboard_listener(stop_flag):
    print("Press '+' to stop logging...")
    while True:
        if msvcrt.kbhit():
            key = msvcrt.getch()
            if key == b'+':
                stop_flag.append(True)
                break

def main():
    try:
        ss = DualEchosounder(PORT, BAUD)
    except Exception as e:
        print("Unable to open port:", e)
        return

    if not ss.IsDetected():
        print("Port opened but echosounder is not detected")
        return

    print("SONAR STARTED")

    ss.SetCurrentTime()
    ss.SendCommand("IdSetDualFreq")         # Enable dual frequency mode
    ss.SetValue("IdOutput", "3")            # Output mode 3
    ss.SetValue("IdInterval", str(LOG_INTERVAL))

    if not ss.Start():
        print("Failed to start sonar.")
        return

    stop_flag = []
    threading.Thread(target=keyboard_listener, args=(stop_flag,), daemon=True).start()

    with open(OUTPUT_FILE, "w", encoding="latin_1") as f:
        while not stop_flag:
            data = ss.ReadData(128)
            decoded = data.decode("latin_1", errors="ignore")
            print(decoded, end='')  # Optional console output
            f.write(decoded)
            time.sleep(LOG_INTERVAL)

    ss.Stop()
    print("\nSONAR STOPPED. Data saved to", OUTPUT_FILE)

if __name__ == "__main__":
    main()