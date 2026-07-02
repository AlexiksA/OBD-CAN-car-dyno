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

import time

max_engine_load = 0
max_engine_load_time = 0
try:
    t0 = time.time()
    while True:
        print(30 * "-")
        print ("Time", time.time() - t0)
        print("RPM", calc_RPM())
        print("STFT", get_STFT())
        print("LTFT", get_LTFT())
        print("air_fuel_ratio", get_air_f_ratio())
        print("Engine load", calc_engine_load())
        val = calc_engine_load()
        if val > max_engine_load:
            max_engine_load = val
            max_engine_load_time = time.time() - t0
        print("Mean absolute pressure", get_map())
        print(30 * "-")
        time.sleep(0.05)
except KeyboardInterrupt:
    print(30 * "#")
    print("MAX_ENGINE_LOAD", max_engine_load)
    print("MAX_ENGINE_LOAD_TIME", max_engine_load_time)