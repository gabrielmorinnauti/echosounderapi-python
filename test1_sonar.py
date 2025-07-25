# Copyright (c) EofE Ultrasonics Co., Ltd., 2024
from echosndr import DualEchosounder
import time

# Remplacer par ton vrai port COM ou /dev/ttyUSBx si tu es sur Linux
SERIAL_PORT = "COM10"
BAUD_RATE = 115200

try:
    sonar = DualEchosounder(SERIAL_PORT, BAUD_RATE)
except:
    print("❌ Port non accessible")
else:
    if not sonar.IsDetected():
        print("❗ Sonar non détecté malgré le port ouvert")
    else:
        print("✅ Sonar détecté")

        # --- Configuration initiale ---
        sonar.SetCurrentTime()  # Synchronisation de l'heure interne
        #v/rification de lheure
        pc_time = time.strftime("%H:%M:%S", time.gmtime())
        print("🕒 Heure PC UTC :", pc_time)
        print("🕒 Heure sonar (via trame SDZDA) : voir dans les logs")


        # Tu peux ici choisir l'une des trois lignes suivantes :
        # sonar.SendCommand("IdSetHighFreq")   # Pour travailler en haute fréquence seule
        # sonar.SendCommand("IdSetLowFreq")  # Pour basse fréquence seule
        sonar.SendCommand("IdSetDualFreq") # Pour les deux simultanément

        # Paramètres de mesure
        sonar.SetValue("IdOutput", "3")      # Mode de sortie (valide pour NMEA)
        sonar.SetValue("IdInterval", "0.5")  # Ping toutes les 0.5 sec

        # Démarrage du sonar
        if sonar.Start():
            print("🔄 Fréquence active :", sonar.GetValue("IdGetWorkFreq"), "Hz")

            try:
                print("📡 Lecture des données... (CTRL+C pour arrêter)")
                while True:
                    data = sonar.ReadData(256)  # Lire jusqu'à 256 octets
                    if data:
                        print(data.decode("latin_1", errors="ignore").strip())
                    time.sleep(0.1)

            except KeyboardInterrupt:
                print("\n🛑 Arrêt de l'acquisition par l'utilisateur.")
                sonar.Stop()