"""
dyno_plot.py — vizualizare rulari dyno (CSV cu coloanele: rpm, torque, hp).

- binning pe RPM + max per bin (peak hold, ca pe un dyno real)
- netezire Savitzky-Golay in loc de fit polinomial de ordin 2
- cuplu si putere pe axe separate (scale diferite!)
- marcheaza si adnoteaza varfurile
- poti selecta mai multe rulari simultan pentru comparatie
"""

from __future__ import annotations

import glob
import sys

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import questionary as qst
from scipy.signal import savgol_filter


RPM_BIN = 50          # latimea unui bin de RPM
DROP_LAST_PER_BIN = True   # arunca ultima proba din fiecare bin (tranzitie)
MIN_TORQUE = 10.0     # Nm — filtreaza mostrele de ralanti / decelerare
MIN_HP = 1.0
SMOOTH_WINDOW = 9     # nr. de bin-uri pentru Savitzky-Golay (impar)
SMOOTH_ORDER = 2

PAIRS = [("#1f77b4", "#d62728"), ("#2ca02c", "#ff7f0e"),
         ("#9467bd", "#8c564b"), ("#17becf", "#e377c2")]



def load_run(path: str) -> pd.DataFrame:
    """Citeste un CSV, binuieste pe RPM, ia maximul per bin si netezeste."""
    df = pd.read_csv(path)

    missing = {"rpm", "torque", "hp"} - set(df.columns)
    if missing:
        raise ValueError(f"{path}: lipsesc coloanele {sorted(missing)}")

    df = df.dropna(subset=["rpm", "torque", "hp"]).sort_values("rpm")
    df["rpm_bin"] = (df["rpm"] // RPM_BIN) * RPM_BIN

    if DROP_LAST_PER_BIN:
        df = df.groupby("rpm_bin").head(-1)

    binned = (df.groupby("rpm_bin", as_index=False)
                .agg(torque=("torque", "max"), hp=("hp", "max"))
                .sort_values("rpm_bin")
                .reset_index(drop=True))

    binned = binned[(binned["torque"] > MIN_TORQUE) & (binned["hp"] > MIN_HP)]
    binned = binned.reset_index(drop=True)

    if binned.empty:
        raise ValueError(f"{path}: nu a ramas nimic dupa filtrare")

    n = len(binned)
    win = min(SMOOTH_WINDOW, n if n % 2 else n - 1)
    if win > SMOOTH_ORDER + 1:
        binned["torque_s"] = savgol_filter(binned["torque"], win, SMOOTH_ORDER)
        binned["hp_s"] = savgol_filter(binned["hp"], win, SMOOTH_ORDER)
    else:
        binned["torque_s"] = binned["torque"]
        binned["hp_s"] = binned["hp"]

    return binned


def peaks(binned: pd.DataFrame) -> dict:
    it = binned["torque_s"].idxmax()
    ip = binned["hp_s"].idxmax()
    return {
        "trq": binned.at[it, "torque_s"], "trq_rpm": binned.at[it, "rpm_bin"],
        "hp": binned.at[ip, "hp_s"], "hp_rpm": binned.at[ip, "rpm_bin"],
        "trq_raw": binned["torque"].max(), "hp_raw": binned["hp"].max(),
    }


def print_summary(runs: dict[str, pd.DataFrame]) -> None:
    print()
    print(f"{'rulare':<28}{'cuplu max':>22}{'putere max':>22}")
    print("-" * 72)
    for name, b in runs.items():
        p = peaks(b)
        print(f"{name:<28}"
              f"{p['trq']:>9.1f} Nm @ {p['trq_rpm']:>5.0f} rpm"
              f"{p['hp']:>9.1f} CP @ {p['hp_rpm']:>5.0f} rpm")
    print("-" * 72)
    print("(valori de pe curba netezita; max brut per bin: "
          + ", ".join(f"{n}: {peaks(b)['trq_raw']:.1f} Nm / {peaks(b)['hp_raw']:.1f} CP"
                      for n, b in runs.items()) + ")")
    print()


def plot_runs(runs: dict[str, pd.DataFrame]) -> None:
    plt.style.use("seaborn-v0_8-darkgrid")
    fig, ax_t = plt.subplots(figsize=(11, 6.5))
    ax_p = ax_t.twinx()
    ax_p.grid(False)

    single = len(runs) == 1
    handles = []

    for i, (name, b) in enumerate(runs.items()):
        c_t, c_p = PAIRS[i % len(PAIRS)]
        tag = "" if single else f" — {name}"

        # puncte brute (binuite), discrete
        ax_t.scatter(b.rpm_bin, b.torque, s=10, color=c_t, alpha=.25, zorder=2)
        ax_p.scatter(b.rpm_bin, b.hp, s=10, color=c_p, alpha=.25, zorder=2)

        # curbe netezite
        lt, = ax_t.plot(b.rpm_bin, b.torque_s, color=c_t, lw=2.4,
                        label=f"Cuplu (Nm){tag}", zorder=3)
        lp, = ax_p.plot(b.rpm_bin, b.hp_s, color=c_p, lw=2.4, ls="--",
                        label=f"Putere (CP){tag}", zorder=3)
        handles += [lt, lp]

        p = peaks(b)
        ax_t.plot(p["trq_rpm"], p["trq"], "o", ms=8, mfc="none", mew=2,
                  color=c_t, zorder=4)
        ax_p.plot(p["hp_rpm"], p["hp"], "o", ms=8, mfc="none", mew=2,
                  color=c_p, zorder=4)

        if single:
            ax_t.annotate(f"{p['trq']:.0f} Nm @ {p['trq_rpm']:.0f}",
                          xy=(p["trq_rpm"], p["trq"]), xytext=(8, -18),
                          textcoords="offset points", color=c_t,
                          fontweight="bold",
                          bbox=dict(fc="white", ec=c_t, alpha=.85, pad=2))
            ax_p.annotate(f"{p['hp']:.0f} CP @ {p['hp_rpm']:.0f}",
                          xy=(p["hp_rpm"], p["hp"]), xytext=(8, -18),
                          textcoords="offset points", color=c_p,
                          fontweight="bold",
                          bbox=dict(fc="white", ec=c_p, alpha=.85, pad=2))
            ax_t.axvline(p["trq_rpm"], color=c_t, alpha=.25, ls=":")
            ax_p.axvline(p["hp_rpm"], color=c_p, alpha=.25, ls=":")

    ax_t.set_xlabel("Turatie (rpm)")
    ax_t.set_ylabel("Cuplu (Nm)", color=PAIRS[0][0] if single else "black")
    ax_p.set_ylabel("Putere (CP)", color=PAIRS[0][1] if single else "black")
    if single:
        ax_t.tick_params(axis="y", colors=PAIRS[0][0])
        ax_p.tick_params(axis="y", colors=PAIRS[0][1])

    # ambele axe pornesc de la 0 => proportiile dintre curbe raman sincere
    ax_t.set_ylim(0, max(b.torque_s.max() for b in runs.values()) * 1.25)
    ax_p.set_ylim(0, max(b.hp_s.max() for b in runs.values()) * 1.25)
    ax_t.xaxis.set_major_locator(plt.MultipleLocator(500))

    title = list(runs)[0] if single else "Comparatie rulari"
    ax_t.set_title(title, fontsize=13, fontweight="bold")
    ax_t.legend(handles=handles, loc="upper left", framealpha=.9)
    fig.tight_layout()
    plt.show()


# interfata
def pick_files() -> list[str] | None:
    files = sorted(glob.glob("dyno*.csv")) or sorted(glob.glob("dyno*"))
    if not files:
        print("Niciun fisier 'dyno*' in directorul curent.")
        return None
    # Ctrl+C / Esc -> ask() intoarce None, nu arunca KeyboardInterrupt
    return qst.checkbox(
        "Selecteaza una sau mai multe rulari (space = bifezi, enter = ok)",
        choices=files,
    ).ask()


def main() -> int:
    while True:
        chosen = pick_files()
        if not chosen:            # None (Ctrl+C) sau lista goala
            return 0

        runs = {}
        for path in chosen:
            try:
                runs[path] = load_run(path)
            except Exception as e:
                print(f"[skip] {e}")

        if runs:
            print_summary(runs)
            plot_runs(runs)

        again = qst.confirm("Alt CSV?", default=True).ask()
        if not again:
            return 0


if __name__ == "__main__":
    sys.exit(main())