import os
import sys
import importlib.util
from pathlib import Path

# Add libraries directory to Python path
SCRIPT_DIR = Path(__file__).parent
LIBRARIES_DIR = SCRIPT_DIR / "libraries"
VERSIONS_DIR = SCRIPT_DIR / "versions"
OUTPUT_DIR = SCRIPT_DIR / "output"

sys.path.insert(0, str(LIBRARIES_DIR))

import versions.sonar_services_v0 as sonar_service

def main():
    try:
        print("Handling request: /sonar/sonar_write_to_csv_file")
        file_path = sonar_service.writeToCSVFile("COM10", "output")
        result = {"status": "success", "message": file_path, "file_path": file_path}
        print(result)
    except Exception as e:
        print(f"Error creating CSV file: {e}")
        return
    
    try:
        while True:
            pass
    except KeyboardInterrupt:
        print("\nStopping sonar data collection...")
        sonar_service.stopWritingToCSV()
        print("Program terminated.")

if __name__ == "__main__":
    main()