# Source Generated with Decompyle++
# File: simulation.cpython-312.pyc (Python 3.12)

'''
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
'''
import csv
import math
import random
import sys
from agents import ACAgent, LightingAgent, CostAgent, ComfortAgent
from coordinator import Coordinator
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding = 'utf-8')
DATA_LABEL = 'simulation-estimated'
ZONES = [
    {
        'id': 'classroom_1',
        'label': 'فصل دراسي ١',
        'zone_type': 'normal',
        'pattern': 'classroom',
        'size_m2': 70,
        'thermal_capacity': 8,
        'has_windows': True },
    {
        'id': 'classroom_2',
        'label': 'فصل دراسي ٢',
        'zone_type': 'normal',
        'pattern': 'classroom',
        'size_m2': 70,
        'thermal_capacity': 8,
        'has_windows': True },
    {
        'id': 'office_1',
        'label': 'مكتب إداري',
        'zone_type': 'normal',
        'pattern': 'office',
        'size_m2': 35,
        'thermal_capacity': 5,
        'has_windows': True },
    {
        'id': 'corridor_1',
        'label': 'ممر رئيسي',
        'zone_type': 'normal',
        'pattern': 'corridor',
        'size_m2': 50,
        'thermal_capacity': 6,
        'has_windows': False },
    {
        'id': 'or_1',
        'label': 'غرفة عمليات (منطقة حرجة)',
        'zone_type': 'critical',
        'pattern': 'critical',
        'size_m2': 25,
        'thermal_capacity': 3,
        'has_windows': False,
        'required_temp': 20 }]
WEEKEND_DAYS = {
    5,
    6}

def is_weekend(day_index):
    return day_index in WEEKEND_DAYS

LEAK_BASE = 1.2
OCC_GAIN_BASE = 3
AC_MAX_RATE = 40
ENERGY_PER_DEGREE_PER_50M2 = 0.8
LIGHTING_KW_PER_M2 = 0.012

def step_temperature(current_temp, outdoor_temp, occupied, setpoint, thermal_capacity):
    leak_rate = LEAK_BASE / thermal_capacity
    occ_gain = OCC_GAIN_BASE / thermal_capacity
    drift_temp = current_temp + leak_rate * (outdoor_temp - current_temp) + occ_gain if occupied else 0
    max_delta = AC_MAX_RATE / thermal_capacity
    desired_delta = setpoint - drift_temp
    actual_delta = max(-max_delta, min(max_delta, desired_delta))
    next_temp = drift_temp + actual_delta
    return (next_temp, abs(actual_delta))


def ac_energy_kwh(size_m2, delta_achieved):
    return ENERGY_PER_DEGREE_PER_50M2 * (size_m2 / 50) * delta_achieved


def lighting_energy_kwh(size_m2, level):
    return LIGHTING_KW_PER_M2 * size_m2 * level


def occupancy_probability(pattern, hour, day_index):
    if pattern == 'critical':
        if is_weekend(day_index):
            return 0.1
        if  <= 8, hour or 8, hour < 16:
            return 0.6
            return 0.05
        return 0.05
    if is_weekend(day_index):
        return 0.03
    if pattern == 'classroom':
        if  <= 7, hour or 7, hour < 8:
            return 0.5
        if  <= 8, hour or 8, hour < 12:
            return 0.95
        if  <= 12, hour or 12, hour < 13:
            return 0.35
        if  <= 13, hour or 13, hour < 16:
            return 0.9
        if  <= 16, hour or 16, hour < 17:
            return 0.4
            return 0.02
        return 0.02
    if pattern == 'office':
        if  <= 7, hour or 7, hour < 8:
            return 0.4
        if  <= 8, hour or 8, hour < 12:
            return 0.9
        if  <= 12, hour or 12, hour < 13:
            return 0.55
        if  <= 13, hour or 13, hour < 17:
            return 0.85
        if  <= 17, hour or 17, hour < 18:
            return 0.3
            return 0.02
        return 0.02
    if pattern == 'corridor':
        if hour in (7, 12, 13, 16, 17):
            return 0.6
        if  <= 8, hour or 8, hour < 17:
            return 0.2
            return 0.02
        return 0.02
    return 0.02


def generate_environment(seed, total_hours, zones):
    '''يبني بيئة المحاكاة مرة واحدة فقط: نفس الإشغال ونفس الطقس يُستخدمان لاحقًا
    في كلا السيناريوهين (baseline و sarab) لضمان أن الفرق بينهما ناتج عن
    طريقة التحكم فقط.'''
    rng = random.Random(seed)
    num_days = total_hours // 24 + 1
# WARNING: Decompyle incomplete

(PEAK_START, PEAK_END) = (12, 17)
PEAK_PRICE = 0.32
OFFPEAK_PRICE = 0.18

def tariff_for_hour(hour):
    PEAK_PRICE if is_peak else OFFPEAK_PRICE = None if  <= PEAK_START, hour else None, PEAK_START, hour < PEAK_END
    return (is_peak, price)

BASELINE_OCCUPIED_TEMP = 22
BASELINE_SETBACK_TEMP = 26
(BASELINE_START, BASELINE_END) = (7, 18)

def baseline_decision(zone, hour, day_index):
    if zone['zone_type'] == 'critical':
        return (zone['required_temp'], 1)
    if not None(day_index):
        if not  <= BASELINE_START, hour or BASELINE_START, hour < BASELINE_END:
            return (BASELINE_SETBACK_TEMP, 0)
    return (BASELINE_SETBACK_TEMP, 0)
    return (BASELINE_OCCUPIED_TEMP, 1)


def build_coordinators_per_zone(zones):
    coordinators = { }
    for z in zones:
        zone_agents = [
            ACAgent(z['id']),
            LightingAgent(z['id']),
            CostAgent(z['id']),
            ComfortAgent(z['id'], zone_type = z['zone_type'], critical_required_temp = z.get('required_temp'))]
        coordinators[z['id']] = Coordinator(zone_agents)
    return coordinators


def run_scenario(name, zones, total_hours, outdoor_temps, occupancy, natural_light, controller):
    pass
# WARNING: Decompyle incomplete


def print_report(baseline_summary, sarab_summary):
    b_kwh = baseline_summary['total_kwh']
    s_kwh = sarab_summary['total_kwh']
    diff_pct = ((b_kwh - s_kwh) / b_kwh) * 100 if b_kwh else 0
    print('========================================================================')
    print('تقرير محاكاة سراب - أسبوع كامل (٧ أيام) [{}]'.format(DATA_LABEL))
    print('كل الأرقام أدناه تقدير من المحاكاة، وليست قياسًا فعليًا من مبنى حقيقي')
    print('========================================================================')
    print('النظام التقليدي (جدول ثابت):')
    print('  إجمالي الطاقة (kWh) [{}]: {:.2f}'.format(DATA_LABEL, b_kwh))
    print()
    print('نظام سراب (وكلاء + تفاوض):')
    print('  إجمالي الطاقة (kWh) [{}]: {:.2f}'.format(DATA_LABEL, s_kwh))
    print('  نسبة الفرق مقارنة بالنظام التقليدي [{}]: {:.1f}%'.format(DATA_LABEL, diff_pct))
    print('  عدد القرارات المستقلة عبر الأسبوع (تفاوض فعلي لكل ساعة/منطقة/مجال): {}'.format(sarab_summary['decisions_count']))
    print()
    print('مخالفات القيود الصلبة الفعلية بعد التحديث الفيزيائي (يجب أن تكون صفرًا):')
    print('  baseline: {}'.format(baseline_summary['violations']))
    print('  sarab   : {}'.format(sarab_summary['violations']))
    print()
    print('عدد مرات فوز كل وكيل خلال الأسبوع (يثبت أن التفاوض يبقى حقيقيًا')
    print('على مدى أسبوع كامل، وليس فقط في اختباري الحالة الأصليين):')
    for agent_name, count in sorted(sarab_summary['win_counts'].items(), key = (lambda kv: -kv[1])):
        label = agent_name if agent_name else '(لا يوجد حل حتى بعد توسعة الهامش)'
        print('    {:<14s}: {}'.format(label, count))
    print('========================================================================')


def write_csv(rows, path):
    fieldnames = list(rows[0].keys())
# WARNING: Decompyle incomplete


def main():
    seed = 42
    days = 7
    total_hours = days * 24
    (outdoor_temps, occupancy, natural_light) = generate_environment(seed, total_hours, ZONES)
    (baseline_rows, baseline_summary) = run_scenario('baseline', ZONES, total_hours, outdoor_temps, occupancy, natural_light, controller = 'baseline')
    (sarab_rows, sarab_summary) = run_scenario('sarab', ZONES, total_hours, outdoor_temps, occupancy, natural_light, controller = 'sarab')
    all_rows = baseline_rows + sarab_rows
    write_csv(all_rows, 'simulation_log.csv')
    print_report(baseline_summary, sarab_summary)
    print('السجل الساعي الكامل [{}] محفوظ في simulation_log.csv'.format(DATA_LABEL))

if __name__ == '__main__':
    main()
    return None
