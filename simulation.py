# -*- coding: utf-8 -*-
"""
سراب - المرحلة الثانية: بيئة المحاكاة (التوأم الرقمي)

هذا الملف لا يعيد كتابة الوكلاء أو المنسّق من المرحلة الأولى، بل يستخدمهما
كما هما (agents.py و coordinator.py) ويبني حولهما بيئة محاكاة كاملة:
مبنى بعدة مناطق، نموذج حراري بسيط، مولّد إشغال واقعي، وبيانات خارجية
(تعرفة كهرباء + حرارة خارجية). ثم يشغّل سيناريوهين على نفس "التوأم الرقمي"
وبنفس البذرة العشوائية (seed=42) حتى يكون الفرق بينهما ناتجًا عن طريقة
التحكم فقط، لا عن اختلاف الظروف:

  1) baseline: جدول تحكم ثابت (الطريقة التقليدية المستخدمة في المباني اليوم)
  2) sarab   : وكلاء ومنسّق المرحلة الأولى يتفاوضون كل ساعة

كل الأرقام الناتجة هنا هي "تقدير محاكاة" (simulation-estimated) وليست
قياسًا فعليًا من مبنى حقيقي.
"""

import csv
import math
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
DATA_DIR = REPO_ROOT / "data"

from agents import ACAgent, LightingAgent, CostAgent, ComfortAgent
from coordinator import Coordinator


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DATA_LABEL = "simulation-estimated"  
ZONES = [
    {
        "id": "classroom_1", "label": "فصل دراسي ١",
        "zone_type": "normal", "pattern": "classroom",
        "size_m2": 70, "thermal_capacity": 8.0, "has_windows": True,
    },
    {
        "id": "classroom_2", "label": "فصل دراسي ٢",
        "zone_type": "normal", "pattern": "classroom",
        "size_m2": 70, "thermal_capacity": 8.0, "has_windows": True,
    },
    {
        "id": "office_1", "label": "مكتب إداري",
        "zone_type": "normal", "pattern": "office",
        "size_m2": 35, "thermal_capacity": 5.0, "has_windows": True,
    },
    {
        "id": "corridor_1", "label": "ممر رئيسي",
        "zone_type": "normal", "pattern": "corridor",
        "size_m2": 50, "thermal_capacity": 6.0, "has_windows": False,
    },
    {
        "id": "or_1", "label": "غرفة عمليات (منطقة حرجة)",
        "zone_type": "critical", "pattern": "critical",
        "size_m2": 25, "thermal_capacity": 3.0, "has_windows": False,
        "required_temp": 20.0,
    },
]

WEEKEND_DAYS = {5, 6}  

def is_weekend(day_index):
    return day_index in WEEKEND_DAYS



LEAK_BASE = 1.2          # قوة التسرب الحراري الأساسية (تُقسم على السعة الحرارية)
OCC_GAIN_BASE = 3.0      # حرارة مكتسبة من الإشغال (تُقسم على السعة الحرارية)
AC_MAX_RATE = 40.0       # أقصى قدرة تصحيح للمكيف في الساعة (تُقسم على السعة الحرارية)

ENERGY_PER_DEGREE_PER_50M2 = 0.8  # kWh لكل درجة تصحيح فعلي، لمنطقة مرجعية 50م²
LIGHTING_KW_PER_M2 = 0.012        # كثافة حمل إضاءة تقريبية لكل م²


def step_temperature(current_temp, outdoor_temp, occupied, setpoint, thermal_capacity):
    leak_rate = LEAK_BASE / thermal_capacity
    occ_gain = OCC_GAIN_BASE / thermal_capacity
    drift_temp = (
        current_temp
        + leak_rate * (outdoor_temp - current_temp)
        + (occ_gain if occupied else 0.0)
    )

    max_delta = AC_MAX_RATE / thermal_capacity
    desired_delta = setpoint - drift_temp
    actual_delta = max(-max_delta, min(max_delta, desired_delta))
    next_temp = drift_temp + actual_delta

    return next_temp, abs(actual_delta)


def ac_energy_kwh(size_m2, delta_achieved):
    return ENERGY_PER_DEGREE_PER_50M2 * (size_m2 / 50.0) * delta_achieved


def lighting_energy_kwh(size_m2, level):
    return LIGHTING_KW_PER_M2 * size_m2 * level



def occupancy_probability(pattern, hour, day_index):
    if pattern == "critical":
        # جدول عمليات مستقل عن نمط الدوام العادي؛ هذا لا يغيّر متطلب الحرارة
        # الثابت لأن وكيل الراحة يتجاهل الإشغال في المناطق الحرجة أصلاً
        if is_weekend(day_index):
            return 0.10
        if 8 <= hour < 16:
            return 0.60
        return 0.05

    if is_weekend(day_index):
        return 0.03

    if pattern == "classroom":
        if 7 <= hour < 8:
            return 0.50
        if 8 <= hour < 12:
            return 0.95
        if 12 <= hour < 13:
            return 0.35  # فجوة منتصف النهار
        if 13 <= hour < 16:
            return 0.90
        if 16 <= hour < 17:
            return 0.40
        return 0.02

    if pattern == "office":
        if 7 <= hour < 8:
            return 0.40
        if 8 <= hour < 12:
            return 0.90
        if 12 <= hour < 13:
            return 0.55  # غداء متفرق، ليس فجوة كاملة كالفصول
        if 13 <= hour < 17:
            return 0.85
        if 17 <= hour < 18:
            return 0.30
        return 0.02

    if pattern == "corridor":
        if hour in (7, 12, 13, 16, 17):
            return 0.60  # أوقات الحركة (دخول/خروج/غداء)
        if 8 <= hour < 17:
            return 0.20
        return 0.02

    return 0.02


def generate_environment(seed, total_hours, zones):
    """يبني بيئة المحاكاة مرة واحدة فقط: نفس الإشغال ونفس الطقس يُستخدمان لاحقًا
    في كلا السيناريوهين (baseline و sarab) لضمان أن الفرق بينهما ناتج عن
    طريقة التحكم فقط."""
    rng = random.Random(seed)

    num_days = total_hours // 24 + 1
    daily_outdoor_offset = [rng.uniform(-1.5, 1.5) for _ in range(num_days)]

    outdoor_temps = []
    occupancy = []
    natural_light = []

    for h in range(total_hours):
        hour = h % 24
        day = h // 24

     
        base_curve = 33.5 + 8.5 * math.cos(2 * math.pi * (hour - 15) / 24)
        outdoor = base_curve + daily_outdoor_offset[day] + rng.uniform(-0.4, 0.4)
        outdoor_temps.append(outdoor)

        hour_occ = {}
        hour_light = {}
        for z in zones:
            p = occupancy_probability(z["pattern"], hour, day)
            hour_occ[z["id"]] = rng.random() < p
            hour_light[z["id"]] = bool(z["has_windows"] and 6 <= hour < 18)
        occupancy.append(hour_occ)
        natural_light.append(hour_light)

    return outdoor_temps, occupancy, natural_light



PEAK_START, PEAK_END = 12, 17   # ساعات الذروة: من الظهر حتى الساعة الخامسة عصرًا
PEAK_PRICE = 0.32               # سعر الكيلوواط ساعة وقت الذروة
OFFPEAK_PRICE = 0.18            # سعر الكيلوواط ساعة خارج الذروة


def tariff_for_hour(hour):
    is_peak = PEAK_START <= hour < PEAK_END
    price = PEAK_PRICE if is_peak else OFFPEAK_PRICE
    return is_peak, price



BASELINE_OCCUPIED_TEMP = 22.0
BASELINE_SETBACK_TEMP = 26.0
BASELINE_START, BASELINE_END = 7, 18


def baseline_decision(zone, hour, day_index):
    if zone["zone_type"] == "critical":
        # حتى النظام التقليدي يُبقي غرفة العمليات على درجتها المطلوبة دائمًا
        return zone["required_temp"], 1.0
    if is_weekend(day_index) or not (BASELINE_START <= hour < BASELINE_END):
        return BASELINE_SETBACK_TEMP, 0.0
    return BASELINE_OCCUPIED_TEMP, 1.0


def build_coordinators_per_zone(zones):
    coordinators = {}
    for z in zones:
        zone_agents = [
            ACAgent(z["id"]),
            LightingAgent(z["id"]),
            CostAgent(z["id"]),
            ComfortAgent(z["id"], zone_type=z["zone_type"], critical_required_temp=z.get("required_temp")),
        ]
        coordinators[z["id"]] = Coordinator(zone_agents)
    return coordinators


def run_scenario(name, zones, total_hours, outdoor_temps, occupancy, natural_light, controller):
    temps = {
        z["id"]: (z["required_temp"] if z["zone_type"] == "critical" else 25.0)
        for z in zones
    }

    rows = []
    total_kwh = 0.0
    decisions_count = 0
    win_counts = {}
    violations = 0

    coordinators = build_coordinators_per_zone(zones) if controller == "sarab" else None

    for h in range(total_hours):
        hour = h % 24
        day = h // 24
        outdoor = outdoor_temps[h]
        is_peak, price = tariff_for_hour(hour)

        for z in zones:
            zid = z["id"]
            ac_winner = None
            light_winner = None

            if controller == "sarab":
                # كل منطقة تتفاوض بمعزل تام عن غيرها (منسّق مستقل لكل منطقة)
                state = {
                    "zones": {
                        zid: {
                            "temperature": temps[zid],
                            "occupancy": occupancy[h][zid],
                            "natural_light": natural_light[h][zid],
                            "zone_type": z["zone_type"],
                            "required_temp": z.get("required_temp", 20.0),
                        }
                    },
                    "price": {"is_peak": is_peak, "price_per_kwh": price, "hour": hour},
                }
                decisions, _log = coordinators[zid].run_round(state)

                ac_decision = decisions.get((zid, "ac_setpoint"))
                light_decision = decisions.get((zid, "lighting_level"))

                setpoint = ac_decision["value"] if ac_decision and ac_decision["value"] is not None else temps[zid]
                lighting_level = light_decision["value"] if light_decision and light_decision["value"] is not None else 0.0

                if ac_decision is not None:
                    decisions_count += 1
                    ac_winner = ac_decision["winner"]
                    win_counts[ac_winner] = win_counts.get(ac_winner, 0) + 1
                if light_decision is not None:
                    decisions_count += 1
                    light_winner = light_decision["winner"]
                    win_counts[light_winner] = win_counts.get(light_winner, 0) + 1
            else:
                setpoint, lighting_level = baseline_decision(z, hour, day)

            occ = occupancy[h][zid]
            next_temp, delta_achieved = step_temperature(
                temps[zid], outdoor, occ, setpoint, z["thermal_capacity"]
            )
            ac_kwh = ac_energy_kwh(z["size_m2"], delta_achieved)
            light_kwh = lighting_energy_kwh(z["size_m2"], lighting_level)
            hour_total_kwh = ac_kwh + light_kwh
            total_kwh += hour_total_kwh

            # فحص فعلي على نتيجة الحرارة بعد التحديث الفيزيائي، وليس فقط على
            # القيمة التي اختارها التفاوض - هذا يثبت أن الالتزام يصمد فعليًا
            if z["zone_type"] == "critical":
                if abs(next_temp - z["required_temp"]) > 0.5:
                    violations += 1
            else:
                if next_temp > 27.0:
                    violations += 1

            rows.append({
                "label": DATA_LABEL,
                "scenario": name,
                "day": day,
                "hour": hour,
                "zone_id": zid,
                "zone_type": z["zone_type"],
                "occupancy": int(occ),
                "natural_light": int(natural_light[h][zid]),
                "outdoor_temp_c": round(outdoor, 2),
                "price_per_kwh": price,
                "is_peak": int(is_peak),
                "ac_setpoint_c": round(setpoint, 2),
                "temperature_after_c": round(next_temp, 2),
                "ac_kwh": round(ac_kwh, 4),
                "lighting_level": round(lighting_level, 2),
                "lighting_kwh": round(light_kwh, 4),
                "total_kwh": round(hour_total_kwh, 4),
                "ac_winner": ac_winner or "",
                "lighting_winner": light_winner or "",
            })

            temps[zid] = next_temp

    summary = {
        "scenario": name,
        "total_kwh": total_kwh,
        "decisions_count": decisions_count,
        "win_counts": win_counts,
        "violations": violations,
    }
    return rows, summary


# =============================================================================
# التقرير النهائي (كل الأرقام: تقدير محاكاة وليست قياسًا فعليًا)
# =============================================================================
def print_report(baseline_summary, sarab_summary):
    b_kwh = baseline_summary["total_kwh"]
    s_kwh = sarab_summary["total_kwh"]
    diff_pct = ((b_kwh - s_kwh) / b_kwh * 100.0) if b_kwh else 0.0

    print("=" * 72)
    print("تقرير محاكاة سرب - أسبوع كامل (٧ أيام) [{}]".format(DATA_LABEL))
    print("كل الأرقام أدناه تقدير من المحاكاة، وليست قياسًا فعليًا من مبنى حقيقي")
    print("=" * 72)
    print("النظام التقليدي (جدول ثابت):")
    print("  إجمالي الطاقة (kWh) [{}]: {:.2f}".format(DATA_LABEL, b_kwh))
    print()
    print("نظام سراب (وكلاء + تفاوض):")
    print("  إجمالي الطاقة (kWh) [{}]: {:.2f}".format(DATA_LABEL, s_kwh))
    print("  نسبة الفرق مقارنة بالنظام التقليدي [{}]: {:.1f}%".format(DATA_LABEL, diff_pct))
    print("  عدد القرارات المستقلة عبر الأسبوع (تفاوض فعلي لكل ساعة/منطقة/مجال): {}".format(
        sarab_summary["decisions_count"]))
    print()
    print("مخالفات القيود الصلبة الفعلية بعد التحديث الفيزيائي (يجب أن تكون صفرًا):")
    print("  baseline: {}".format(baseline_summary["violations"]))
    print("  sarab   : {}".format(sarab_summary["violations"]))
    print()
    print("عدد مرات فوز كل وكيل خلال الأسبوع (يثبت أن التفاوض يبقى حقيقيًا")
    print("على مدى أسبوع كامل، وليس فقط في اختباري الحالة الأصليين):")
    for agent_name, count in sorted(sarab_summary["win_counts"].items(), key=lambda kv: -kv[1]):
        label = agent_name if agent_name else "(لا يوجد حل حتى بعد توسعة الهامش)"
        print("    {:<14s}: {}".format(label, count))
    print("=" * 72)


def write_csv(rows, path):
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    seed = 42
    days = 7
    total_hours = days * 24

    outdoor_temps, occupancy, natural_light = generate_environment(seed, total_hours, ZONES)

    baseline_rows, baseline_summary = run_scenario(
        "baseline", ZONES, total_hours, outdoor_temps, occupancy, natural_light, controller="baseline"
    )
    sarab_rows, sarab_summary = run_scenario(
        "sarab", ZONES, total_hours, outdoor_temps, occupancy, natural_light, controller="sarab"
    )

    all_rows = baseline_rows + sarab_rows
    DATA_DIR.mkdir(exist_ok=True)
    log_path = DATA_DIR / "simulation_log.csv"
    write_csv(all_rows, str(log_path))

    print_report(baseline_summary, sarab_summary)
    print("السجل الساعي الكامل [{}] محفوظ في {}".format(DATA_LABEL, log_path))


if __name__ == "__main__":
    main()
