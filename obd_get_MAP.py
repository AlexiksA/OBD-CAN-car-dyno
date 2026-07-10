import serial
import numpy as np

elm = serial.Serial("COM8", baudrate= 38400, timeout=1)

def AT(cmd):
    elm.reset_input_buffer()
    elm.write((cmd + "\r").encode('ascii'))
    buf = b""
    while True:
        ch = elm.read(1)
        if not ch:
            break
        if ch == b">":
            break
        buf += ch
    return buf.decode(errors="ignore").replace("\r", " ").strip()

def parse_data_bytes(raw, expected_mode_pid):
    clean = raw.replace(" ", "").replace("\r", "")
    if expected_mode_pid not in clean:
        return None
    idx = clean.index(expected_mode_pid) + len(expected_mode_pid)
    return clean[idx:]

vec_RPM = np.array([800, 2000, 2500, 3000, 3500, 4000, 4500, 5000, 6000])
rnd_eff = np.array([0.20,0.28, 0.31, 0.32, 0.32, 0.31, 0.29, 0.27, 0.23])

def get_eff_term(cur_rpm):
    return np.interp(cur_rpm, vec_RPM, rnd_eff)

def calc_RPM():
    d = parse_data_bytes(AT("010C"), "410C")
    if d is None or len(d) < 4:
        return None
    A, B = int(d[0:2], 16), int(d[2:4], 16)
    return (256*A + B) / 4

def calc_engine_load():
    d = parse_data_bytes(AT("0104"), "4104")
    if d is None or len(d) < 2:
        return None
    A = int(d[0:2], 16)
    return A / 255

def get_map():
    d = parse_data_bytes(AT("010B"), "410B")
    if d is None or len(d) < 2:
        return None
    A = int(d[0:2], 16)
    return A

def get_iat():
    d = parse_data_bytes(AT("010F"), "410F")
    if d is None or len(d) < 2:
        return None
    A = int(d[0:2], 16)
    return A - 40

def get_STFT():
    d = parse_data_bytes(AT("0106"), "4106")
    if d is None or len(d) < 2:
        return None
    A = int(d[0:2], 16)
    return A / 128 - 1

def get_LTFT():
    d = parse_data_bytes(AT("0107"), "4107")
    if d is None or len(d) < 2:
        return None
    A = int(d[0:2], 16)
    return A / 128 - 1

def get_air_f_ratio():
    d = parse_data_bytes(AT("0144"), "4144")
    if d is None or len(d) < 4:
        return None
    A, B = int(d[0:2], 16), int(d[2:4], 16)
    return 2 / 65536 * (256 * A + B)

def update_stuffies(rpm, map_kPa, iat_c, eng_load, STFT, LTFT, air_fuel_ratio, MAF_REAL, MFF_REAL):
    print("\033[9A", end="", flush=True)
    print("RPM: ", rpm)
    print("Manfiold Abs Pressure: ", map_kPa / 100, "bari")
    print("Intake air temp: ", iat_c, "C")
    print("Engine Load: ", eng_load)
    print("Short term fuel trim: ", STFT)
    print("Long term fuel trim: ", LTFT)
    print("Air-fuel ratio: ", air_fuel_ratio)
    print("Masa aer: ", MAF_REAL * 1e3, "g/s")
    print("Masa combustibil: ", MFF_REAL * 1e3, "g/s")
    

def estimare_putere_cuplu(rpm, map_kPa, iat_c, afr, eng_load, STFT, LTFT, air_fuel_ratio):
    '''
    rpm - rotatii pe min
    map_kPa - Presiunea absoluta din galeria de admisie
    Iat_c - Intake air temperature in C
    AFR - indice stoichiometric combustibil (E10 - 14.0-14.1)
    eng_load = eficienta volumetrica din tabela fordului
    STFT - Short term fuel trim
    LTFT - Long term fuel trim
    air_fuel_ratio - e de fapt lambda ul de enrichment dat de motor
    '''
    kW_to_HP = 1.35962
    map_Pa = map_kPa * 1000
    iat_K = iat_c + 273.15
    dens_aer = map_Pa / (287.08563 * iat_K)

    Vol_eff_real = eng_load * (1 + STFT + LTFT)

    MAF_REAL = dens_aer * 1.596e-3 * rpm / 120 * Vol_eff_real
    MFF_REAL = MAF_REAL / (air_fuel_ratio * afr)
    # print("MAF_REAL ", MAF_REAL)
    Power_generated = MFF_REAL * 44e6 * get_eff_term(rpm)
    cuplu = Power_generated / (rpm * 2 * np.pi / 60)

    update_stuffies(rpm, map_kPa, iat_c, eng_load, STFT, LTFT, air_fuel_ratio, MAF_REAL, MFF_REAL)
    
    return Power_generated / 1000 * kW_to_HP, cuplu

if __name__ == "__main__":
    import time
    AT("ATZ")
    time.sleep(1)
    AT("ATE0")
    AT("ATL0")
    AT("ATSP6")
    print("\n\n\n\n\n\n\n\n\n")
    RPM_rise_tol = 5
    RPM_drop_tol = 150
    WOT_LOAD = 0.85

    import matplotlib.pyplot as plt
    import csv
    import random
    val = random.randint(0, 10000)
    csv_name = "dyno" + str(val) + ".csv"

    last_rpm = 0
    pull_rpm, pull_cpl, pull_put = [], [], []

    plt.ion()
    fig, ax = plt.subplots()

    line_cpl, = ax.plot([], [], 'o', ms = 4, label = "cuplu(nm)")
    line_put, = ax.plot([], [], 'o', ms = 4, label = "putere(hp)")

    ax.set_xlabel("RPM")
    ax.set_ylabel("Cuplu / Putere")
    ax.set_title("Pull curent")
    ax.legend()

    with open(csv_name, "w", newline="") as f:
        field_names = ["t","rpm","map","iat","afr","torque","hp"]
        w = csv.writer(f)
        w.writerow(field_names)
        t0 = time.time()

        try:
            while True:
                
                rpm = calc_RPM()
                if rpm is None or rpm < 200:
                    continue

                map_kPa = get_map()
                iat = get_iat()
                afr = 14.05
                eng_load = calc_engine_load()
                STFT = get_STFT()
                LTFT = get_LTFT()
                air_fuel_ratio = get_air_f_ratio() # lambda ul dat de ECU


                HP, cuplu = estimare_putere_cuplu(rpm, map_kPa, iat, afr, eng_load, STFT, LTFT, air_fuel_ratio)
                t= time.time()
                w.writerow([t - t0, rpm, map_kPa, iat, afr, cuplu, HP])

                if(eng_load > WOT_LOAD):
                    if rpm > last_rpm + RPM_rise_tol:
                        pull_rpm.append(rpm)
                        pull_cpl.append(cuplu)
                        pull_put.append(HP)
                    elif rpm < last_rpm - RPM_drop_tol:
                        pull_rpm, pull_cpl, pull_put = [], [], []
                last_rpm = rpm
                
                if pull_rpm:
                    line_cpl.set_data(pull_rpm, pull_cpl)
                    line_put.set_data(pull_rpm, pull_put)

                ax.relim()
                ax.autoscale_view()
                plt.pause(0.001)

                time.sleep(0.001)
        except KeyboardInterrupt:
            pass

    import pandas as pd
    fig2, ax2 = plt.subplots()
    df = pd.read_csv(csv_name).sort_values("rpm")
    ax2.plot(df.rpm, df.torque, label="Cuplu(nm)")
    ax2.plot(df.rpm, df.hp, label = "Putere(cp)")
    ax2.legend()
    plt.show(block = True)