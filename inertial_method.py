import glob
import random as rnd
import time

import numpy as np
import pandas as pd
import questionary as qst
import serial
from scipy.signal import savgol_filter as svf


PORT = "COM8"
BAUD = 38400
ETA_DRIVELINE = 0.86   # crank->wheel loss estimate (~14%). LABELLED ASSUMPTION.
POLYORDER = 3          # Savitzky-Golay polynomial order
WINDOW_SECONDS = 0.4   

# Serial / ELM327
try:
    elm = serial.Serial(PORT, baudrate=BAUD, timeout=1)
except serial.SerialException:
    print(f"Could not open {PORT}")
    raise SystemExit(1)


def AT(cmd):
    """Send one command, read until the ELM327 prompt '>'."""
    elm.reset_input_buffer()
    elm.write((cmd + "\r").encode("ascii"))
    buf = b""
    while True:
        ch = elm.read(1)
        if not ch:          # timeout
            break
        if ch == b">":      # prompt -> response complete
            break
        buf += ch
    return buf.decode(errors="ignore").replace("\r", " ").strip()


def init_elm():
    """Put the adapter into a known state before polling PIDs."""
    AT("ATZ")          # reset
    time.sleep(1.0)    # give it a moment to reboot
    AT("ATE0")         # echo off  -> parser isn't fighting echoed commands
    AT("ATL0")         # linefeeds off
    AT("ATS0")         # spaces off
    AT("ATH0")         # headers off -> response is just the data bytes
    AT("ATSP0")        # auto protocol (use ATSP6 to force 11-bit 500k CAN)
    AT("0100")         # wake / handshake the ECU


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
    return (256 * A + B) / 4.0


def get_v_kmh():
    d = parse_data_bytes(AT("010D"), "410D")
    if d is None or len(d) < 2:
        return None
    return int(d[0:2], 16)   # km/h


# Road-load profile (fit A + B*v + C*v^2 from a coastdown CSV)
def load_road_load():
    files = glob.glob("road_load*")
    if not files:
        raise SystemExit("No road_load*.csv found. Log a coastdown first.")

    what = qst.select("Select a road_load profile", choices=files).ask()
    rl = pd.read_csv(what)

    if "v" not in rl.columns or "road_load" not in rl.columns:
        raise SystemExit(
            "road_load CSV must have columns 'v' (m/s) and 'road_load' (N). "
            f"Found: {list(rl.columns)}"
        )

    rl = rl.dropna()
    v_rl = rl["v"].to_numpy(dtype=float)

    # Defensive unit check: >50 almost certainly means the CSV is in km/h.
    if v_rl.max() > 50:
        print("road_load 'v' looks like km/h (max > 50). Converting to m/s.")
        v_rl = v_rl / 3.6

    coeffs = np.polyfit(v_rl, rl["road_load"].to_numpy(dtype=float), 2)  # [C, B, A]
    C, B, A = coeffs
    print(f"Road load fit:  F_road(v) = {A:.1f} + {B:.2f}*v + {C:.3f}*v^2  (N)")
    return coeffs


# Main
if __name__ == "__main__":
    coeffs = load_road_load()

    cnt = int(input("Cate persoane: "))
    m_eff = 1240 + 72 * cnt

    init_elm()
    print("Logging... floor it in one gear, then Ctrl+C to stop.")

    rpm, v_kmh, t = [], [], []
    t0 = time.time()
    try:
        while True:
            r = calc_RPM()
            s = get_v_kmh()
            if r is None or s is None:    
                continue
            rpm.append(r)
            v_kmh.append(s)
            t.append(time.time() - t0)
    except KeyboardInterrupt:
        pass

    rpm = np.asarray(rpm, dtype=float)
    v_kmh = np.asarray(v_kmh, dtype=float)
    t = np.asarray(t, dtype=float)

    if len(rpm) < 10:
        raise SystemExit(f"Only {len(rpm)} samples captured; need a real pull.")

    # self-calibrate the gear constant: v[m/s] = const * rpm
    v_ms_raw = v_kmh / 3.6
    mask = (rpm > 1000) & (v_kmh > 0)          # ignore idle / stopped rows
    const = np.median(v_ms_raw[mask] / rpm[mask])
    v_ms = rpm * const                          # smooth speed, from fine rpm
    print(f"Gear constant: {const:.6f} (m/s)/rpm")

    # acceleration via Savitzky-Golay on the rpm-derived speed
    dt = float(np.mean(np.diff(t)))
    W = int(round(WINDOW_SECONDS / dt))
    if W % 2 == 0:
        W += 1
    W = max(W, POLYORDER + 2)
    if W > len(v_ms):
        W = len(v_ms) if len(v_ms) % 2 == 1 else len(v_ms) - 1
    a = svf(v_ms, window_length=W, polyorder=POLYORDER, deriv=1, delta=dt)  # m/s^2
    print(f"Sample rate ~{1/dt:.1f} Hz, savgol window {W} (~{W*dt:.2f} s)")

    # forces & power
    F_road = np.polyval(coeffs, v_ms)           # N
    F_tract = m_eff * a + F_road                # N
    P_wheel = F_tract * v_ms                    # W
    P_wheel_kW = P_wheel / 1000.0

    # crank side (uses the driveline-loss ASSUMPTION)
    P_crank_kW = P_wheel_kW / ETA_DRIVELINE
    omega = rpm * 2 * np.pi / 60.0              # rad/s
    T_engine = np.where(omega > 0, (P_crank_kW * 1000.0) / omega, np.nan)  # Nm

    out = pd.DataFrame({
        "t": t, "rpm": rpm, "v_ms": v_ms, "a": a,
        "F_tract": F_tract, "P_wheel_kW": P_wheel_kW,
        "P_crank_kW": P_crank_kW, "torque_Nm": T_engine,
    })
    new_file = "dyno" + str(rnd.randint(0, 1000)) + ".csv"
    out.to_csv(new_file, index=False)
    print(f"Saved {new_file}")

    # --- plot ----------------------------------------------------------------
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots()
    ax.scatter(rpm, P_wheel_kW, s=8, label="Putere roata (kW)")
    ax.scatter(rpm, P_crank_kW, s=8, label="Putere motor (kW)")
    ax.set_xlabel("RPM")
    ax.set_ylabel("Putere (kW)")
    ax2 = ax.twinx()
    ax2.scatter(rpm, T_engine, s=8, color="tab:green", label="Cuplu (Nm)")
    ax2.set_ylabel("Cuplu (Nm)")
    fig.legend(loc="upper left")
    plt.show()