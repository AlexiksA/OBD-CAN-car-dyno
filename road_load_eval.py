import pandas as pd
import glob
import questionary as qst

avail = glob.glob("speed_over_time*")

choice = qst.select("Choose one", avail).ask()

df = pd.read_csv(choice)

df['v'] = df['v'] / 3.6

dv = df['v'].diff()
dt = df['t'].diff()

df['dv_dt'] = dv / dt

import random
val = random.randint(0, 1000)

new_file = "road_load" + str(val) + ".csv"
cnt = int(input("Numar persoane: "))
m_eff = 1240 + cnt * 72

df['road_load'] = (-1) * m_eff * df['dv_dt']

df = df.drop(0)

df[['road_load', 'v']].to_csv(new_file, index=False)