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

print(f"200kHzsonar_{formatted_date}_{formatted_time}")