import serial
import time
import questionary as qst
import random as rnd
import csv

try:
    elm = serial.Serial("COM8", baudrate=38400, timeout=1)
except serial.SerialException:
    print("Nu s-a gasit pe portul dat nimic")
    exit(1)

'''
F_tractiune = m_eff * a + f_road(v) // m_eff - masa efectiva, f_road - forta de frecare la sol (dep de vit)
P_wheel = F_tractiune * v
P_volanta = P_wheel / rand_distributie

m_eff * (dv / dt) = -f_road(v)

aproximam f_road in sensul cmmp sau interpolam 
'''

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

def calc_RPM():
    d = parse_data_bytes(AT("010C"), "410C")
    if d is None or len(d) < 4:
        return None
    A, B = int(d[0:2], 16), int(d[2:4], 16)
    return (256*A + B) / 4

def get_v():
    d = parse_data_bytes(AT("010D"), "410D")
    if(d is None or len(d) < 2):
        return None
    A = int(d[0:2], 16)
    return A

if __name__ == "__main__":

    for cmd in ["ATZ", "ATE0", "ATL0", "ATS0", "ATH0", "ATSP0"]:
        AT(cmd)
        time.sleep(0.2)

    while True:
        try:
            go = qst.confirm("Log?").ask()
            if go == True:
                file_name = "speed_over_time" + str(rnd.randint(0, 1000)) + ".csv"
                with open(file_name, "w") as f:
                    t0 = time.time()

                    w = csv.writer(f)
                    
                    speed = get_v()
                    while speed is None: 
                        speed = get_v()
                    w.writerow(["t", "v"])
                    while speed > 30:
                        w.writerow([time.time() - t0, speed])
                        time.sleep(0.01)
                        s = get_v()
                        if s is not None:
                            speed = s
            else:
                break
        except KeyboardInterrupt:
            pass
