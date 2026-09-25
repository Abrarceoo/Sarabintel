# -*- coding: utf-8 -*-
"""
سراب - المرحلة الأولى: الوكلاء الأربعة
كل وكيل له ثلاث دوال فقط: observe (يقرأ نطاقه الخاص فقط) و propose (يقترح حلاً
مع تبرير وهامش مرونة) و evaluate (يقيّم اقتراح وكيل آخر من وجهة نظره الخاصة).

شكل الاقتراح الموحّد الذي ترجعه propose() في كل وكيل:
{
    "agent": اسم الوكيل,
    "zone": معرف المنطقة,
    "domain": "ac_setpoint" أو "lighting_level"  (المجال المتفاوض عليه),
    "value": القيمة المقترحة (رقم) أو None إذا كانت تُحسب من delta لاحقًا,
    "delta": فرق نسبي (آلية احتياطية إذا اقترح وكيل ما قيمة نسبية لا مطلقة؛ لا
             يستخدمها حاليًا أي من الوكلاء الأربعة بعد إصلاح وكيل التكلفة ليقترح
             قيمته المطلقة بالنسبة للحد الأقصى الصلب مباشرة - انظر CostAgent),
    "justification": تبرير نصي,
    "flexibility_margin": هامش المرونة الذي يقبله الوكيل,
    "context": معلومات إضافية قد يحتاجها وكيل آخر أثناء evaluate(),
}
"""

# ---- ثوابت وكيل التكييف ----
AC_IDEAL_TEMP_OCCUPIED = 23.0   # الدرجة المثالية للراحة عند وجود إشغال
AC_BASE_MARGIN = 1.0            # هامش مرونة أساسي مقبول دائمًا (بصرف النظر عن السعر)
AC_PEAK_CONCESSION_LIMIT = 3.0  # أقصى تنازل يقبل وكيل التكييف تقييمه إيجابيًا وقت الذروة
AC_UNOCCUPIED_MARGIN = 15.0     #


COST_PEAK_SAFETY_MARGIN = 0.5    
COST_OFFPEAK_SAFETY_MARGIN = 1.5  


COMFORT_NORMAL_IDEAL = 24.0        
COMFORT_NORMAL_HARD_LIMIT = 26.0   
COMFORT_CRITICAL_DEFAULT_TEMP = 20.0 


class ACAgent:
    """وكيل التكييف: يراقب حرارة وإشغال منطقته فقط، هدفه الراحة الحرارية."""

    def __init__(self, zone_id):
        self.name = "ACAgent"
        self.zone_id = zone_id
        self._ideal = AC_IDEAL_TEMP_OCCUPIED
        self._margin = AC_BASE_MARGIN

    def observe(self, state):
       
        zone = state["zones"][self.zone_id]
        return {
            "temperature": zone["temperature"],
            "occupancy": zone["occupancy"],
        }

    def propose(self, obs):
        occupied = obs["occupancy"]
        if occupied:
            ideal = AC_IDEAL_TEMP_OCCUPIED
            margin = AC_BASE_MARGIN
            justification = (
                "المنطقة مشغولة ودرجة الحرارة الحالية {:.1f}° مئوية، "
                "الهدف الوصول إلى {:.1f}° لراحة الشاغلين"
            ).format(obs["temperature"], ideal)
        else:
            
            ideal = obs["temperature"]
            margin = AC_UNOCCUPIED_MARGIN
            justification = "المنطقة غير مشغولة، لا حاجة ملحّة لضبط دقيق لدرجة الحرارة"

       
        self._ideal = ideal
        self._margin = margin

        return {
            "agent": self.name,
            "zone": self.zone_id,
            "domain": "ac_setpoint",
            "value": ideal,
            "justification": justification,
            "flexibility_margin": margin,
            "context": {"occupancy": occupied},
        }

    def evaluate(self, proposal):
        if proposal.get("domain") != "ac_setpoint":
            return {"score": 50.0, "hard_violation": False, "reason": "خارج نطاق اهتمام وكيل التكييف"}

        candidate = proposal.get("value")
        ctx = proposal.get("context", {})
        relaxed = ctx.get("relaxed", False)
        is_peak = ctx.get("is_peak", False)

        distance = abs(candidate - self._ideal)
        tight_margin = self._margin * (2.0 if relaxed else 1.0)
        peak_limit = AC_PEAK_CONCESSION_LIMIT * (2.0 if relaxed else 1.0)

        if distance <= tight_margin:
            score = 100.0 - distance * 5.0
            reason = "الفرق {:.1f}° ضمن الهامش الأساسي المقبول دائمًا".format(distance)
        elif is_peak and distance <= peak_limit:
         
            score = 100.0 - distance * 10.0
            reason = "سعر الكهرباء مرتفع والتنازل ({:.1f}°) صغير، لذا يتنازل وكيل التكييف".format(distance)
        else:
            score = max(0.0, 40.0 - distance * 15.0)
            reason = "الفرق {:.1f}° كبير جدًا ولا يُقبل حتى وقت الذروة".format(distance)

        score = max(0.0, min(100.0, score))
        return {"score": score, "hard_violation": False, "reason": reason}


class LightingAgent:
    """وكيل الإضاءة: يراقب الإشغال والإضاءة الطبيعية فقط، يتنازل كليًا في الفراغ."""

    def __init__(self, zone_id):
        self.name = "LightingAgent"
        self.zone_id = zone_id
        self._level = 1.0

    def observe(self, state):
        zone = state["zones"][self.zone_id]
        return {
            "occupancy": zone["occupancy"],
            "natural_light": zone.get("natural_light", False),
        }

    def propose(self, obs):
        if not obs["occupancy"]:
            level = 0.0
            margin = 1.0
            justification = "المنطقة فارغة، يتنازل وكيل الإضاءة بالكامل ويطفئ الإضاءة لتوفير الطاقة"
        elif obs["natural_light"]:
            level = 0.4
            margin = 0.4
            justification = "توجد إضاءة طبيعية كافية، فتُخفَّض الإضاءة الاصطناعية جزئيًا"
        else:
            level = 1.0
            margin = 0.2
            justification = "المنطقة مشغولة ولا توجد إضاءة طبيعية، الإضاءة الكاملة مطلوبة"

        self._level = level

        return {
            "agent": self.name,
            "zone": self.zone_id,
            "domain": "lighting_level",
            "value": level,
            "justification": justification,
            "flexibility_margin": margin,
            "context": {"occupancy": obs["occupancy"], "natural_light": obs["natural_light"]},
        }

    def evaluate(self, proposal):
        if proposal.get("domain") != "lighting_level":
            return {"score": 50.0, "hard_violation": False, "reason": "خارج نطاق اهتمام وكيل الإضاءة"}

        candidate = proposal.get("value", 0.0)
        distance = abs(candidate - self._level)
        score = max(0.0, 100.0 - distance * 100.0)
        return {"score": score, "hard_violation": False, "reason": "مقارنة مباشرة بمستوى الإضاءة المفضل لديه"}


class CostAgent:
    """
    وكيل التكلفة: هدفه خفض الفاتورة، يخفف ضغطه خارج الذروة.
    في المناطق العادية يقترح قيمته المطلقة بالنسبة للحد الأقصى الصلب نفسه (لا
    بالنسبة لمرساة وكيل التكييف)، فيقترح أعلى نقطة ضبط ما زالت مقبولة
    (hard_limit - safety_margin). هذا يضمن أن مقترحه لا يُقصى أبدًا كقيد صلب
    قبل أن تُقارن الدرجات، ولا يتصرف كوكيل "ينتحر" باقتراح قيمة يعرف مسبقًا
    أنها ستُرفض.
    في المناطق الحرجة (كغرفة العمليات) لا توجد مساومة حقيقية أصلاً: الدرجة
    المطلوبة قيمة ثابتة لا سقف مرن يمكن الاقتراب منه لتوفير الطاقة، فيقترح
    وكيل التكلفة الدرجة المطلوبة نفسها دون أي انحراف عنها.
    """

    def __init__(self, zone_id):
        self.name = "CostAgent"
        self.zone_id = zone_id
        self._is_peak = False

    def observe(self, state):
        price = state["price"]
        zone = state["zones"][self.zone_id]
        return {
            "is_peak": price["is_peak"],
            "price_per_kwh": price["price_per_kwh"],
            "hour": price["hour"],
            "zone_type": zone.get("zone_type", "normal"),
            "required_temp": zone.get("required_temp"),
        }

    def propose(self, obs):
        self._is_peak = obs["is_peak"]

        if obs["zone_type"] == "critical":
            # لا يوجد "حد أقصى" يمكن الاقتراب منه هنا كما في المناطق العادية؛
            # الدرجة المطلوبة قيمة ثابتة لا سقف مرن، فأي طرح أقل منها يعني
            # تبريدًا إضافيًا (طاقة أكثر لا أقل). وكيل التكلفة لا يملك أي
            # مساومة حقيقية في منطقة حرجة، فيقترح الدرجة المطلوبة نفسها
            # دون اعتراض بدل صيغة (hard_limit - safety_margin) المخصّصة
            # أصلاً للمناطق العادية ذات السقف المرن.
            required = obs["required_temp"]
            justification = (
                "الساعة {} - منطقة حرجة، لا مجال لتخفيض التكلفة على حساب درجة "
                "الحرارة الثابتة المطلوبة ({:.1f}°)، فلا يقترح وكيل التكلفة أي "
                "انحراف عنها"
            ).format(obs["hour"], required)
            return {
                "agent": self.name,
                "zone": self.zone_id,
                "domain": "ac_setpoint",
                "value": required,
                "justification": justification,
                "flexibility_margin": 0.0,
                "context": {"is_peak": obs["is_peak"], "price_per_kwh": obs["price_per_kwh"]},
            }

        hard_limit = COMFORT_NORMAL_HARD_LIMIT

        if obs["is_peak"]:
            safety_margin = COST_PEAK_SAFETY_MARGIN
            margin = 1.0  # ضغط قوي وقت الذروة، هامش تراجع صغير
        else:
            safety_margin = COST_OFFPEAK_SAFETY_MARGIN
            margin = 3.0  # خارج الذروة يتنازل بسهولة أكبر

        target = hard_limit - safety_margin

        if obs["is_peak"]:
            justification = (
                "الساعة {} ضمن ساعات الذروة وسعر الكيلوواط {}، يقترح وكيل التكلفة "
                "أعلى نقطة ضبط ما زالت آمنة ({:.1f}°) بمسافة أمان {:.1f}° عن الحد "
                "الأقصى الصلب، لتقليل حمل التبريد دون كسر أي قيد"
            ).format(obs["hour"], obs["price_per_kwh"], target, safety_margin)
        else:
            justification = (
                "الساعة {} خارج ساعات الذروة، يخفف وكيل التكلفة ضغطه ويقترح "
                "نقطة ضبط أقرب لحد الراحة المفضل ({:.1f}°) بدل الضغط القوي"
            ).format(obs["hour"], target)

        return {
            "agent": self.name,
            "zone": self.zone_id,
            "domain": "ac_setpoint",
            "value": target,
            "justification": justification,
            "flexibility_margin": margin,
            "context": {"is_peak": obs["is_peak"], "price_per_kwh": obs["price_per_kwh"]},
        }

    def evaluate(self, proposal):
        if proposal.get("domain") != "ac_setpoint":
            return {"score": 50.0, "hard_violation": False, "reason": "خارج نطاق اهتمام وكيل التكلفة"}

        candidate = proposal.get("value")
        ctx = proposal.get("context", {})
        reference = ctx.get("reference_ideal", candidate)
        savings = candidate - reference  

        if self._is_peak:
            score = max(0.0, min(100.0, savings * 30.0))
            reason = "وقت الذروة: التوفير المقترح {:.1f}° يمنح نقاطًا أعلى كلما زاد".format(savings)
        else:
            score = max(0.0, min(100.0, 50.0 + savings * 10.0))
            reason = "خارج الذروة: ضغط وكيل التكلفة أخف ولا يمانع القيم القريبة من المرجع"

        return {"score": score, "hard_violation": False, "reason": reason}


class ComfortAgent:
    """
    وكيل الراحة: يحمل حدود الراحة لكل منطقة.
    المناطق العادية: حد أقصى صلب 26°. المناطق الحرجة (كغرف العمليات): لا يتنازل أبدًا
    عن الدرجة المطلوبة، مهما ارتفع السعر أو اتسع هامش المرونة في الجولة الثانية.
    """

    def __init__(self, zone_id, zone_type="normal", critical_required_temp=None):
        self.name = "ComfortAgent"
        self.zone_id = zone_id
        self.zone_type = zone_type
        self.required_temp = (
            critical_required_temp
            if critical_required_temp is not None
            else COMFORT_CRITICAL_DEFAULT_TEMP
        )

    def observe(self, state):
      
        zone = state["zones"][self.zone_id]
        return {
            "zone_type": zone.get("zone_type", self.zone_type),
            "required_temp": zone.get("required_temp", self.required_temp),
        }

    def propose(self, obs):
        self.zone_type = obs["zone_type"]
        self.required_temp = obs["required_temp"]

        if self.zone_type == "critical":
            value = self.required_temp
            margin = 0.0  # لا تنازل إطلاقًا
            justification = (
                "منطقة حرجة (كغرفة عمليات)، يجب أن تبقى درجة الحرارة ثابتة عند {:.1f}° "
                "ولا مجال للتفاوض مهما ارتفع سعر الكهرباء"
            ).format(value)
        else:
            value = COMFORT_NORMAL_IDEAL
            margin = COMFORT_NORMAL_HARD_LIMIT - COMFORT_NORMAL_IDEAL
            justification = (
                "منطقة عادية، الحد الأقصى المسموح به هو {:.1f}°، لكن الوضع الآمن "
                "المفضل هو {:.1f}°"
            ).format(COMFORT_NORMAL_HARD_LIMIT, value)

        return {
            "agent": self.name,
            "zone": self.zone_id,
            "domain": "ac_setpoint",
            "value": value,
            "justification": justification,
            "flexibility_margin": margin,
            "context": {"zone_type": self.zone_type},
        }

    def evaluate(self, proposal):
        if proposal.get("domain") != "ac_setpoint":
            return {"score": 50.0, "hard_violation": False, "reason": "خارج نطاق اهتمام وكيل الراحة"}

        candidate = proposal.get("value")
        ctx = proposal.get("context", {})
        relaxed = ctx.get("relaxed", False)

        if self.zone_type == "critical":
          
            if candidate == self.required_temp:
                return {
                    "score": 100.0,
                    "hard_violation": False,
                    "reason": "يطابق تمامًا الدرجة المطلوبة {:.1f}° للمنطقة الحرجة".format(self.required_temp),
                }
            return {
                "score": -1.0,
                "hard_violation": True,
                "reason": "أي انحراف عن الدرجة المطلوبة مرفوض في المناطق الحرجة مهما كان السعر",
            }

        hard_limit = COMFORT_NORMAL_HARD_LIMIT + (1.0 if relaxed else 0.0)
        if candidate > hard_limit:
            return {
                "score": -1.0,
                "hard_violation": True,
                "reason": "القيمة {:.1f}° تتجاوز الحد الأقصى المسموح {:.1f}°".format(candidate, hard_limit),
            }

        distance = candidate - COMFORT_NORMAL_IDEAL
        score = max(0.0, min(100.0, 100.0 - distance * 20.0))
        return {
            "score": score,
            "hard_violation": False,
            "reason": "القيمة ضمن الحد الآمن (الحد الأقصى الحالي {:.1f}°)".format(hard_limit),
        }
