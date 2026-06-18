#!/usr/bin/env python3
"""
Recalculate virtual battery self-consumption from HA long-term statistics.

Uses hourly energy_out deltas × electricity tariff at that hour.
No opportunity cost subtracted — pure savings from avoided grid import.

Run on Mars: python3 recalc_self_consumption.py [path_to_db]
Default db path: /config/home-assistant_v2.db
"""

import sqlite3
import sys
from datetime import datetime, timezone

DB_PATH = sys.argv[1] if len(sys.argv) > 1 else "/config/home-assistant_v2.db"

BATTERY_SIZES = [10, 20, 30, 40]

# Sensor statistic_ids (template sensors with unique_id)
ENERGY_OUT_PATTERN = "sensor.vb_{cap}kwh_energy_out"
TARIFF_ID = "sensor.zonneplan_current_electricity_tariff"

PRICE_THRESHOLD = 0.30  # EUR/kWh


def get_metadata_id(cur, statistic_id):
    cur.execute(
        "SELECT id FROM statistics_meta WHERE statistic_id = ?", (statistic_id,)
    )
    row = cur.fetchone()
    return row[0] if row else None


def get_hourly_stats(cur, metadata_id):
    """Get hourly (start_ts, sum) from statistics table."""
    cur.execute(
        "SELECT start_ts, sum FROM statistics WHERE metadata_id = ? ORDER BY start_ts",
        (metadata_id,),
    )
    return cur.fetchall()


def get_hourly_mean(cur, metadata_id):
    """Get hourly (start_ts, mean) from statistics table."""
    cur.execute(
        "SELECT start_ts, mean FROM statistics WHERE metadata_id = ? ORDER BY start_ts",
        (metadata_id,),
    )
    return cur.fetchall()


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # List available statistic_ids for debugging
    cur.execute("SELECT statistic_id FROM statistics_meta WHERE statistic_id LIKE '%virtual_battery%' OR statistic_id LIKE '%zonneplan%' OR statistic_id LIKE '%vb_%'")
    available = [r[0] for r in cur.fetchall()]
    print("Available relevant statistics:")
    for s in sorted(available):
        print(f"  {s}")
    print()

    # Get tariff data
    tariff_meta = get_metadata_id(cur, TARIFF_ID)
    if not tariff_meta:
        print(f"ERROR: Tariff sensor '{TARIFF_ID}' not found in statistics_meta.")
        print("Check the available statistics above and adjust TARIFF_ID.")
        conn.close()
        sys.exit(1)

    tariff_data = get_hourly_mean(cur, tariff_meta)
    tariff_by_ts = {ts: mean for ts, mean in tariff_data}
    print(f"Tariff data: {len(tariff_data)} hourly records\n")

    for cap in BATTERY_SIZES:
        sensor_id = ENERGY_OUT_PATTERN.format(cap=cap)
        meta_id = get_metadata_id(cur, sensor_id)

        if not meta_id:
            print(f"--- {cap} kWh: sensor '{sensor_id}' not found, skipping ---\n")
            continue

        stats = get_hourly_stats(cur, meta_id)
        if len(stats) < 2:
            print(f"--- {cap} kWh: not enough data ({len(stats)} records) ---\n")
            continue

        total_kwh = 0.0
        total_eur = 0.0
        total_eur_high = 0.0  # price >= threshold
        total_eur_low = 0.0   # price < threshold
        total_kwh_high = 0.0
        total_kwh_low = 0.0
        hours_matched = 0
        hours_unmatched = 0

        for i in range(1, len(stats)):
            ts = stats[i][0]
            prev_sum = stats[i - 1][1] or 0
            curr_sum = stats[i][1] or 0
            delta_kwh = curr_sum - prev_sum

            if delta_kwh <= 0:
                continue

            tariff = tariff_by_ts.get(ts)
            if tariff is None:
                hours_unmatched += 1
                continue

            hours_matched += 1
            eur = delta_kwh * tariff
            total_kwh += delta_kwh
            total_eur += eur

            if tariff >= PRICE_THRESHOLD:
                total_eur_high += eur
                total_kwh_high += delta_kwh
            else:
                total_eur_low += eur
                total_kwh_low += delta_kwh

        avg_price = total_eur / total_kwh if total_kwh > 0 else 0
        avg_high = total_eur_high / total_kwh_high if total_kwh_high > 0 else 0
        avg_low = total_eur_low / total_kwh_low if total_kwh_low > 0 else 0

        ts_first = datetime.fromtimestamp(stats[0][0], tz=timezone.utc)
        ts_last = datetime.fromtimestamp(stats[-1][0], tz=timezone.utc)

        print(f"=== {cap} kWh Batterij ===")
        print(f"Periode: {ts_first:%Y-%m-%d} t/m {ts_last:%Y-%m-%d}")
        print(f"Data: {hours_matched} uren matched, {hours_unmatched} uren zonder tarief")
        print()
        print(f"Totaal ontladen:        {total_kwh:>8.2f} kWh")
        print(f"Bruto zelfconsumptie:   {total_eur:>8.2f} EUR  (gem. {avg_price:.4f} EUR/kWh)")
        print()
        print(f"  >= {PRICE_THRESHOLD} EUR/kWh:      {total_kwh_high:>8.2f} kWh = {total_eur_high:>8.2f} EUR  (gem. {avg_high:.4f} EUR/kWh)")
        print(f"  <  {PRICE_THRESHOLD} EUR/kWh:      {total_kwh_low:>8.2f} kWh = {total_eur_low:>8.2f} EUR  (gem. {avg_low:.4f} EUR/kWh)")
        print()

    conn.close()


if __name__ == "__main__":
    main()
