# -*- coding: utf-8 -*-
"""
سراب - المرحلة الأولى: المنسّق (Coordinator)
يدير جولة تفاوض كاملة بين الوكلاء الأربعة: يجمع الاقتراحات، يمرّرها للتقييم
المتبادل بين الوكلاء، ثم يختار الحل الذي يحترم كل القيود الصلبة ويحقق أعلى
مجموع درجات. إن لم يوجد حل مقبول، يعيد المحاولة بهامش مرونة أوسع.
"""


class Coordinator:
    def __init__(self, agents):
       
        self.agents = agents

    def run_round(self, state):
        """ينفّذ جولة تفاوض كاملة على الحالة المعطاة ويرجع (القرارات، السجل)."""
        log = {"proposals": [], "evaluations": [], "decisions": {}}

     
        raw_proposals = []
        for agent in self.agents:
            obs = agent.observe(state)
            proposal = agent.propose(obs)
            raw_proposals.append(proposal)
        log["proposals"] = raw_proposals

      
        domains = {}
        for p in raw_proposals:
            key = (p["zone"], p["domain"])
            domains.setdefault(key, []).append(p)

    
        decisions = {}
        for key, proposals in domains.items():
            decisions[key] = self._negotiate_domain(proposals, log)
        log["decisions"] = decisions

        return decisions, log

    # ------------------------------------------------------------------
    def _resolve_values(self, proposals):
        """
        يحسم القيم المطلقة الناقصة. وكيل مثل التكلفة قد يقترح فرقًا نسبيًا (delta)
        فقط لأنه لا يعرف الحرارة الفعلية؛ المنسّق يحسمها هنا باستخدام اقتراح
        وكيل التكييف كقيمة مرجعية، ثم يضعها في سياق كل الاقتراحات لتُستخدم
        لاحقًا (مثلاً وكيل التكلفة يحتاجها ليحسب مقدار التوفير).
        """
        reference = next(
            (p["value"] for p in proposals if p["agent"] == "ACAgent" and p.get("value") is not None),
            None,
        )
        if reference is None:
            reference = next((p["value"] for p in proposals if p.get("value") is not None), 0.0)

        for p in proposals:
            p.setdefault("context", {})
            p["context"]["reference_ideal"] = reference
            if p.get("value") is None and p.get("delta") is not None:
                p["value"] = reference + p["delta"]

    def _weight_for(self, agent, is_peak):
        """
        وزن تأثير تقييم كل وكيل عند الجمع. وقت الذروة تكبر أولوية خفض التكلفة
        فيرتفع وزن وكيل التكلفة؛ خارج الذروة يخف ضغطه فينخفض وزنه. بقية الوكلاء
        يبقى وزنهم ثابتًا.
        """
        if agent.name == "CostAgent":
            return 1.3 if is_peak else 0.8
        return 1.0

    def _negotiate_domain(self, proposals, log, relaxed=False):
        """
        يفاوض على مجال واحد (منطقة + نطاق) بين كل الاقتراحات المتنافسة عليه:
        يحسم القيم، يجمع تقييم كل وكيل لكل اقتراح، يستبعد أي اقتراح يخرق قيدًا
        صلبًا، ثم يختار الأعلى مجموع درجات من بين الباقين. إن لم يبقَ أي اقتراح
        مقبول، يعيد المحاولة مرة واحدة بهامش مرونة أوسع (relaxed=True).
        """
        proposals = [dict(p, context=dict(p.get("context", {}))) for p in proposals]
        if relaxed:
            for p in proposals:
                p["context"]["relaxed"] = True

        self._resolve_values(proposals)

        is_peak = next((p["context"].get("is_peak") for p in proposals if "is_peak" in p.get("context", {})), False)

      
        results = []
        for candidate in proposals:
            total = 0.0
            feasible = True
            breakdown = []
            for agent in self.agents:
                verdict = agent.evaluate(candidate)
                breakdown.append({"by": agent.name, **verdict})
                if verdict["hard_violation"]:
                    feasible = False
                total += verdict["score"] * self._weight_for(agent, is_peak)
            results.append({
                "candidate": candidate,
                "total_score": total,
                "feasible": feasible,
                "breakdown": breakdown,
            })

        log["evaluations"].append({"relaxed": relaxed, "results": results})

     
        feasible_results = [r for r in results if r["feasible"]]

        if not feasible_results:
            if not relaxed:
               
                return self._negotiate_domain(proposals, log, relaxed=True)
            return {
                "zone": proposals[0]["zone"],
                "domain": proposals[0]["domain"],
                "winner": None,
                "value": None,
                "reason": "لا يوجد حل يحترم كل القيود الصلبة حتى بعد توسيع هامش المرونة",
            }

        winner = max(feasible_results, key=lambda r: r["total_score"])
        return {
            "zone": winner["candidate"]["zone"],
            "domain": winner["candidate"]["domain"],
            "winner": winner["candidate"]["agent"],
            "value": winner["candidate"]["value"],
            "justification": winner["candidate"]["justification"],
            "total_score": winner["total_score"],
            "relaxed_round": relaxed,
            "all_results": results,
        }

    # ------------------------------------------------------------------
    def format_summary(self, decisions):
        """يبني نصًا عربيًا مقروءًا: من اقترح ماذا، ومن فاز ولماذا."""
        lines = []
        for (zone, domain), decision in decisions.items():
            lines.append("== المنطقة: {} | النطاق: {} ==".format(zone, domain))
            if decision["winner"] is None:
                lines.append("  لا يوجد قرار: {}".format(decision["reason"]))
                continue
            for r in decision["all_results"]:
                c = r["candidate"]
                mark = " <== الفائز" if c["agent"] == decision["winner"] else ""
                lines.append(
                    "  اقتراح {}: قيمة={} | مجموع الدرجات={:.1f} | مقبول={}{}".format(
                        c["agent"], c["value"], r["total_score"], r["feasible"], mark
                    )
                )
                lines.append("      تبرير الاقتراح: {}".format(c["justification"]))
            lines.append(
                "  القرار النهائي: فاز {} بالقيمة {} (جولة موسّعة={})".format(
                    decision["winner"], decision["value"], decision["relaxed_round"]
                )
            )
            lines.append("  سبب الفوز: أعلى مجموع درجات بين الاقتراحات التي لم تخرق أي قيد صلب")
        return "\n".join(lines)
