# OBD-CAN car dyno

A DIY dynamometer that estimates engine **torque** and **power** from live OBD-II
data read through an ELM327 adapter (serial / USB / Bluetooth-serial). No rollers
needed; two independent estimation methods are provided:

| Method | Script | Idea |
|---|---|---|
| **MAP / airflow** | `obd_get_MAP.py` | Speed-density: MAP + IAT + RPM + engine load + fuel trims → air mass → fuel mass → power |
| **Inertial** | `inertial_method.py` | Acceleration of the car in one gear + a measured road-load curve → wheel power → crank power |

Everything is plain Python scripts that talk to the adapter with `pyserial` and
write CSV files that you review afterwards.

---

## Requirements

- Python 3.8+
- An ELM327 adapter exposing a serial port (the scripts default to `COM8` @ 38400 baud)
- Packages:

```bash
pip install pyserial numpy pandas scipy matplotlib questionary
```

> **Port:** every script that talks to the car has `COM8` hard-coded near the top
> (`serial.Serial("COM8", 38400, ...)` or `PORT = "COM8"`). On Linux use something
> like `/dev/ttyUSB0` or `/dev/rfcomm0`. Change it before running.

---

## Files

| File | Purpose |
|---|---|
| `obd_test.py` | Adapter sanity check: resets the ELM, prints version/voltage and which PIDs the ECU supports (`0100`, `0120`, `0140`, `0160`) |
| `real_deal.py` | Live console readout (RPM, STFT, LTFT, lambda, engine load, MAP) and tracks the peak engine load. No CSV. |
| `obd_get_MAP.py` | **Dyno run, MAP method.** Logs live, plots the pull in real time, writes `dyno<N>.csv` |
| `speed_over_time.py` | **Coastdown logger.** Writes `speed_over_time<N>.csv` (`t`, `v` in km/h) |
| `road_load_eval.py` | Converts a `speed_over_time*.csv` into a road-load profile `road_load<N>.csv` (`v` in m/s, `road_load` in N) |
| `inertial_method.py` | **Dyno run, inertial method.** Needs a `road_load*.csv`; writes `dyno<N>.csv` |
| `check_previous_csvs.py` | **Viewer.** Pick one or more `dyno*.csv`, bins/smooths them, prints peak torque/power and plots (compare multiple runs) |
| `dyno*.csv` | Example logged runs |

---

## Workflow

### 0. Check the adapter

```bash
python obd_test.py
```

You should see the ELM version string, the battery voltage (`ATRV`) and hex
replies for the supported-PID queries. If you get `?` / `NO DATA` / nothing,
fix the connection before going further (ignition on, correct COM port, baud
rate).

Optionally run `python real_deal.py` to watch live values and confirm your car
actually reports RPM, MAP, IAT, load, trims and the lambda PID (`0144`).
`Ctrl+C` stops it and prints the maximum engine load seen.

### 1. Method A — MAP-based dyno (`obd_get_MAP.py`)

Estimates airflow from manifold pressure, then fuel flow, then power:

```
air density   = MAP / (R * IAT)
VE_real       = engine_load * (1 + STFT + LTFT)
air mass flow = density * displacement * RPM/120 * VE_real
fuel flow     = air mass flow / (lambda * AFR_stoich)      # AFR_stoich = 14.05 (E10)
power         = fuel flow * 44 MJ/kg * efficiency(RPM)     # efficiency from an RPM lookup table
torque        = power / angular speed
```

To take a measurement:

1. Park safely / use a closed road, engine warm, in a gear that gives a long pull
   (3rd or 4th is typical).
2. `python obd_get_MAP.py`
3. Start from low RPM and do a **full-throttle pull** up through the rev range.
   The live plot only keeps points where engine load > 0.85 (WOT) and RPM is
   rising, and resets if RPM drops sharply, so repeated pulls are fine.
4. Press `Ctrl+C` to stop. The run is saved as `dyno<random 0-9999>.csv` and a
   final torque/power vs. RPM plot opens.

Columns: `t, rpm, map, iat, afr, torque, hp` (`torque` in Nm, `hp` in metric HP).

Things to tune at the top of the file: displacement (`1.596e-3` m³ in
`estimare_putere_cuplu`), the efficiency table (`vec_RPM` / `rnd_eff`),
`WOT_LOAD`, `afr`.

### 2. Method B — Inertial dyno (`inertial_method.py`)

This needs a **road-load curve** for your car first (rolling resistance + drag as
a function of speed). Get it from a coastdown.

#### 2a. Coastdown logging — `speed_over_time.py`

1. On a flat, straight, quiet road, accelerate above ~30 km/h (the higher the
   better, e.g. 100+ km/h), shift to neutral and let the car roll.
2. `python speed_over_time.py`, answer **yes** to `Log?` — logging records
   `t, v` (km/h) until speed falls to 30 km/h, then asks again.
3. Repeat in both directions of the road to cancel wind/grade, then answer no.

Output: `speed_over_time<N>.csv`.

#### 2b. Compute road load — `road_load_eval.py`

```bash
python road_load_eval.py
```

Pick the coastdown file, enter the number of occupants. The script converts
speed to m/s, differentiates it, and computes

```
road_load = -m_eff * dv/dt        m_eff = 1240 kg + 72 kg * people
```

and saves `road_load<N>.csv` with columns `road_load` (N) and `v` (m/s).
(Adjust the `1240` curb-mass constant for your car; the same constant lives in
`inertial_method.py`.)

#### 2c. Acceleration pull — `inertial_method.py`

```bash
python inertial_method.py
```

1. Select the `road_load*.csv` profile; a quadratic `A + B·v + C·v²` is fitted.
2. Enter the number of occupants (sets the effective mass).
3. When it prints *Logging…*, do a **WOT pull in a single gear**, then `Ctrl+C`.
4. The script self-calibrates the gear constant `v = k·rpm` (the OBD speed PID is
   only 1 km/h resolution, RPM is much finer), differentiates with a
   Savitzky–Golay filter, and computes:

```
F_tract  = m_eff * a + F_road(v)
P_wheel  = F_tract * v
P_crank  = P_wheel / 0.86          # assumed 14 % driveline loss (ETA_DRIVELINE)
torque   = P_crank / omega
```

Output `dyno<N>.csv` with columns `t, rpm, v_ms, a, F_tract, P_wheel_kW,
P_crank_kW, torque_Nm`, and a plot (wheel power, crank power, torque).

### 3. Reviewing CSVs — `check_previous_csvs.py`

```bash
python check_previous_csvs.py
```

- Lists every `dyno*.csv` in the current folder; **space** to tick one or more
  runs, **enter** to confirm, `Ctrl+C`/`Esc` to quit.
- For each run it bins samples by RPM (50 rpm bins), takes the max per bin
  (peak-hold like a real dyno), drops the last sample of each bin, filters out
  idle/decel samples (torque < 10 Nm, power < 1 HP) and smooths with
  Savitzky–Golay.
- Prints a summary table of peak torque and peak power (with the RPM at which
  they occur), then plots torque and power on separate axes. Selecting several
  runs overlays them for comparison.
- Then asks `Alt CSV?` to look at another selection.

Tunables are the constants at the top (`RPM_BIN`, `MIN_TORQUE`, `SMOOTH_WINDOW`,
…).

**Heads-up:** the viewer requires columns named `rpm`, `torque` and `hp`.
Files from `obd_get_MAP.py` have them. Files from `inertial_method.py` use
`torque_Nm` / `P_crank_kW` instead and will be skipped with a `[skip] lipsesc
coloanele ...` message unless you rename/convert the columns (`hp = P_crank_kW *
1.35962`).

---

## Tips & caveats

- **Results are estimates.** The MAP method depends on the assumed displacement,
  efficiency table and ECU-reported load; the inertial method depends on the
  road-load fit, effective mass and the assumed driveline efficiency. Compare
  *relative* changes between runs on the same day/road rather than trusting the
  absolute numbers.
- Same conditions between runs: same gear, same road, similar IAT/coolant temp,
  same load in the car, tyre pressure, no wind.
- OBD refresh is slow (a few to a few tens of Hz depending on the adapter), so
  use a long, steady pull in a high-ish gear.
- Both dyno scripts name outputs `dyno<random>.csv`; a collision would overwrite
  an earlier run, so move runs you care about into a dated folder.
- `inertial_method.py` finds profiles with `glob("road_load*")`, which also
  matches `road_load_eval.py` itself. Only the `.csv` outputs are valid choices
  in the menu.
- Safety: do pulls only where it is legal and safe. Do not operate the laptop
  while driving; have a passenger log.
