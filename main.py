from src.test3_sonar import EchoSounderBridge
import threading

if __name__ == "__main__":
    sonar = EchoSounderBridge("COM10", 115200, "output/releve_bathymetrique_dual.csv")

    errorMsg = sonar.connectToSonar()
    if errorMsg is not None:
        print(errorMsg)
        exit()

    sonar.writeToCSV()
    try:
        # Keep main thread alive until interrupted
        while True:
            threading.Event().wait()
    except KeyboardInterrupt:
        sonar.stopWritingToCSV()

