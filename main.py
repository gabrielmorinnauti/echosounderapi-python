"""To run the code

1 | venv/scripts/activate.bat
2 | python -m pip install --upgrade pip
3 | pip install loguru 
"""
import sys
from loguru import logger
import sonar_service

PORT = "COM10"
CSV_PATH = "releve_bathymetrique_dual.csv"

SETTINGS = {
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

def main():
    logger.level(logger.debug)
    logger.info("Connecting to sonar.")

    sonar_service.connectSonar(PORT, SETTINGS)


if __name__ == '__main__':
    main()