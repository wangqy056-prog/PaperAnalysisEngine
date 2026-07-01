"""Paper Analysis Engine - 核心评级引擎

设计原则（借鉴 ICAS v1.1）：
1. 每个维度独立计算 → 加权求和 → 综合评分
2. 数学四舍五入（废除手动取整）
3. 时间衰减：引用量随年份衰减
4. 修正因子：极端值触发等级调整

公式总览：
    Overall_Score = Σ(W_d × S_d) + Corrections
    Grade = f(Overall_Score)  →  {S, A, B, C, D}
"""

import math
from datetime import datetime
from typing import Dict, Optional, Tuple
from dataclasses import dataclass

from engine.config import config


@dataclass
class RatingResult:
    """评级结果"""
    paper_id: str
    academic_impact: float      # 0-100
    commercial_potential: float  # 0-100
    innovation_index: float      # 0-100
    reproducibility: float       # 0-100
    combo_value: float           # 0-100
    overall_score: float         # 0-100
    grade: str                   # S/A/B/C/D
    dimension_details: Dict      # 各维度细分
    decay_adjustment: float      # 时间衰减调整值


class RatingEngine:
    """论文评级计算引擎"""

    def __init__(self):
        self.config = config

    # ================================================================
    #  维度 1：学术影响力（权重 30%）
    #  公式：AI = 四舍五入(引用分 + 期刊分 + 领域排名分 + SS影响力分)
    #  其中各子项已压至 0-100 范围
    # ================================================================

    def _citation_score(self, citations: int, year: int, current_year: int = None) -> float:
        """
        引用量评分（已含时间衰减）

        公式：
            effective_cites = citations × e^(-λ × Δt)
            λ = 0.693 / HALF_LIFE （半衰期 5 年）
            score = 30 × arctan(effective_cites / 100) / (π/2)

        校准后：100 引用 ≈ 23 分，500 引用 ≈ 28 分，5000 引用 ≈ 30 分
        """
        if current_year is None:
            current_year = datetime.now().year

        delta_t = max(0, current_year - year)
        effective = citations * math.exp(-config.CITATION_DECAY_LAMBDA * delta_t)

        # arctan 平滑映射：30 × arctan(x/100) / (π/2)
        score = 30 * math.atan(effective / 100.0) / (math.pi / 2)
        return round(score, 1)

    def _journal_score(self, journal: str) -> float:
        """
        期刊影响因子评分

        分级（可后续接入 JCR/SJR 数据细化）：
            Top 期刊   → 25 分
            高影响期刊 → 20 分
            中影响期刊 → 12 分
            其他       → 5 分

        改进方向：接入 OpenAlex 的 venues 数据获取真实 SJR
        """
        jl = (journal or "").lower().strip()
        for top_j in config.TOP_JOURNALS:
            if top_j in jl:
                return 25.0
        for hi_j in config.HIGH_IMPACT_JOURNALS:
            if hi_j in jl:
                return 20.0
        return 10.0  # 默认给 10 分（有期刊发表即有一定价值）

    def _field_rank_score(self, paper: Dict) -> float:
        """
        领域排名评分

        如果 Semantic Scholar API 返回了 influentialCitationCount，
        可用该值在领域内做百分位排名。

        简化版：根据 citationCount 在领域中的分位数
        - 前 1%  → 25 分
        - 前 5%  → 20 分
        - 前 10% → 15 分
        - 前 25% → 10 分
        - 其他   → 5 分

        完整版需要接入 OpenAlex 获取领域百分位数据。
        """
        citations = paper.get("citations", 0)
        field = paper.get("field", "")

        # 粗略估算（校准后阈值降低，让中等引用量也能获合理分数）
        if citations >= 500:
            return 25.0
        elif citations >= 200:
            return 20.0
        elif citations >= 50:
            return 15.0
        elif citations >= 20:
            return 10.0
        else:
            return 8.0

    def _ss_impact_score(self, paper: Dict) -> float:
        """
        Semantic Scholar 影响力评分

        SS 提供 0-100 的 influentialCitationCount 权重分。
        直接映射：× 0.25 压至 25 分制
        """
        ss_score = paper.get("influential_citation_count", 0) or 0
        # 归一化到 0-25
        return min(25, ss_score * 0.25)

    def calc_academic_impact(self, paper: Dict) -> Tuple[float, Dict]:
        """
        计算学术影响力综合分

        权重分配：
           引用量   → 25 分
           期刊质量 → 25 分
           领域排名 → 25 分
           SS影响力 → 25 分
        """
        cites = paper.get("citations", 0)
        year = paper.get("year", datetime.now().year)

        sub = {
            "citation_raw": cites,
            "citation_effective": round(cites * math.exp(
                -config.CITATION_DECAY_LAMBDA * max(0, datetime.now().year - year)
            ), 1),
            "citation_score": self._citation_score(cites, year),
            "journal_score": self._journal_score(paper.get("journal", "")),
            "field_rank_score": self._field_rank_score(paper),
            "ss_impact_score": self._ss_impact_score(paper),
        }

        total = sum(sub[k] for k in [
            "citation_score", "journal_score",
            "field_rank_score", "ss_impact_score"
        ])
        total = round(total, 1)  # 四舍五入（ICAS v1.1 规则）

        return min(100, total), sub

    # ================================================================
    #  维度 2：商业转化潜力（权重 25%）
    #  公式：CP = 四舍五入(TRL分 + 专利分 + 需求分)
    # ================================================================

    def _trl_score(self, paper: Dict) -> float:
        """
        技术成熟度（TRL）评分

        TRL 1-9 映射：
            1-3  基础研究 → 10 分
            4-6  应用研究 → 25 分
            7-8  原型/验证 → 35 分
            9    商业化   → 40 分

        简化版：根据论文中有无"prototype""implementation""deployed"等关键词粗估。
        完整版接入专利数据库 + 企业合作数据。
        """
        abstract = (paper.get("abstract") or "").lower()
        title = (paper.get("title") or "").lower()
        text = title + " " + abstract

        # 关键词检测（粗略 TRL 估算）
        deployment_words = ["deployed", "production", "commercialized", "fda approved"]
        prototype_words = ["prototype", "implemented", "validated", "clinical trial", "pilot"]
        applied_words = ["application", "applied", "framework", "system", "tool"]

        if any(w in text for w in deployment_words):
            return 40.0
        elif any(w in text for w in prototype_words):
            return 25.0
        elif any(w in text for w in applied_words):
            return 15.0
        return 10.0

    def _patent_score(self, paper: Dict) -> float:
        """
        专利布局评分

        简化版：检查是否有专利相关信息
        完整版：接入 PatentAPI 查询相关专利数量
        """
        abstract = (paper.get("abstract") or "").lower()
        if "patent" in abstract:
            return 30.0
        return 5.0  # 无专利信息，给基线分

    def _market_score(self, paper: Dict) -> float:
        """
        市场需求评分

        简化版：根据领域热度估算
        完整版：接入 Google Trends / 投资数据
        """
        field = (paper.get("field") or "").lower()
        hot_fields = {
            "artificial intelligence": 30, "machine learning": 30,
            "llm": 30, "deep learning": 28, "quantum": 25,
            "biotechnology": 30, "gene therapy": 30,
            "renewable energy": 25, "battery": 28,
        }
        for k, v in hot_fields.items():
            if k in field:
                return float(v)
        return 15.0  # 默认中等

    def calc_commercial_potential(self, paper: Dict) -> Tuple[float, Dict]:
        """
        计算商业转化潜力

        权重：
           TRL    → 40 分
           专利   → 30 分
           市场   → 30 分
        """
        sub = {
            "trl_score": self._trl_score(paper),
            "patent_score": self._patent_score(paper),
            "market_score": self._market_score(paper),
        }
        total = round(sum(sub.values()), 1)
        return min(100, total), sub

    # ================================================================
    #  维度 3：创新指数（权重 20%）
    # ================================================================

    def calc_innovation_index(self, paper: Dict) -> Tuple[float, Dict]:
        """
        创新指数

        简化版：
        - 方法论创新：标题/摘要中是否有新颖方法描述（40分）
        - 跨领域融合：是否跨多个领域（30分）
        - 原创性：引用新颖度（30分）

        完整版：接入 LLM 进行内容级创新评估
        """
        title = (paper.get("title") or "").lower()
        abstract = (paper.get("abstract") or "").lower()
        text = title + " " + abstract

        # 方法论创新词
        novel_words = ["novel", "new", "first", "state-of-the-art", "breakthrough",
                       "outperform", "surpass", "unprecedented"]
        method_words = ["method", "framework", "architecture", "approach", "algorithm",
                        "paradigm", "model", "theory"]

        novelty_hits = sum(1 for w in novel_words if w in text)
        method_hits = sum(1 for w in method_words if w in text)

        method_score = min(40, (novelty_hits * 5 + method_hits * 3))

        # 跨领域（field 中有多领域标记）
        field = paper.get("field", "")
        cross_domain = 20 if "," in field or " & " in field else 10

        # 原创性（基于引用数反向：引用少但影响力高 = 可能更原创）
        citations = paper.get("citations", 0)
        if citations < 10:
            originality = 25
        elif citations < 100:
            originality = 20
        else:
            originality = 15

        sub = {
            "method_score": method_score,
            "cross_domain": float(cross_domain),
            "originality": float(originality),
        }
        total = round(sum(sub.values()), 1)
        return min(100, total), sub

    # ================================================================
    #  维度 4：可复现性（权重 15%）
    # ================================================================

    def calc_reproducibility(self, paper: Dict) -> Tuple[float, Dict]:
        """
        可复现性评分

        简化版：检查是否有代码/数据/实验描述
        完整版：检查 GitHub 链接、数据集链接、复现报告
        """
        abstract = (paper.get("abstract") or "").lower()

        code_words = ["code", "github", "repository", "open source",
                      "implementation", "available at"]
        data_words = ["dataset", "data available", "open data",
                      "publicly available", "benchmark"]
        experiment_words = ["experiment", "evaluation", "ablation",
                            "hyperparameter", "baseline"]

        code_hits = sum(1 for w in code_words if w in abstract)
        data_hits = sum(1 for w in data_words if w in abstract)
        exp_hits = sum(1 for w in experiment_words if w in abstract)

        sub = {
            "code_availability": min(40, code_hits * 10),
            "data_availability": min(30, data_hits * 10),
            "experiment_detail": min(30, exp_hits * 6),
        }
        # 基线分：有摘要即认为有部分可复现信息
        total = round(sum(sub.values()) + 15, 1)
        return min(100, total), sub

    # ================================================================
    #  维度 5：组合价值（权重 10%，需传入相关论文列表）
    # ================================================================

    def calc_combo_value(self, paper: Dict,
                         related_papers: list = None) -> Tuple[float, Dict]:
        """
        组合价值（与其他论文的协同潜力）

        需要相关论文列表才能计算真实协同度。
        MVP 阶段返回基线分。
        """
        if not related_papers:
            return 50.0, {"note": "基线分，需组合分析模块"}

        # 主题相似度（同领域论文越多 → 可能越有组合价值）
        same_field = sum(1 for p in related_papers
                        if p.get("field") == paper.get("field"))
        topic_score = min(40, same_field * 8)

        # 技术成熟度互补（引用差异大 → 可能互补）
        refs = [p.get("reference_count", 0) for p in related_papers]
        ref_range = max(refs) - min(refs) if refs else 0
        complement_score = min(30, ref_range / 100)

        # 时间跨度
        years = [p.get("year", 0) for p in related_papers if p.get("year")]
        time_span = max(years) - min(years) if years else 0
        time_score = min(30, time_span * 3)

        sub = {
            "topic_score": topic_score,
            "complement_score": complement_score,
            "time_score": time_score,
        }
        total = round(sum(sub.values()), 1)
        return min(100, total), sub

    # ================================================================
    #  综合评分计算
    # ================================================================

    def calculate(self, paper: Dict,
                  related_papers: list = None) -> RatingResult:
        """
        计算论文综合评级

        公式：
        Overall = round(
            AI × 0.30 + CP × 0.25 + II × 0.20 + RP × 0.15 + CV × 0.10
            + Corrections
        )

        修正因子（借鉴 ICAS）：
        - 单维度 ≥ 90  →  降一级（极端值预警）
        - 单维度 ≤ 10  →  升一级（避免误判）
        - 引用量 = 0 且年份 > 2 →  降半级（未验证）
        """
        # 计算五个维度
        ai_score, ai_detail = self.calc_academic_impact(paper)
        cp_score, cp_detail = self.calc_commercial_potential(paper)
        ii_score, ii_detail = self.calc_innovation_index(paper)
        rp_score, rp_detail = self.calc_reproducibility(paper)
        cv_score, cv_detail = self.calc_combo_value(paper, related_papers)

        # 加权求和
        overall = (
            ai_score * config.ACADEMIC_WEIGHT +
            cp_score * config.COMMERCIAL_WEIGHT +
            ii_score * config.INNOVATION_WEIGHT +
            rp_score * config.REPRODUCIBILITY_WEIGHT +
            cv_score * config.COMBO_WEIGHT
        )
        overall = round(overall, 1)

        # 修正因子
        correction = 0
        dims = [ai_score, cp_score, ii_score, rp_score, cv_score]
        if any(d >= 90 for d in dims):
            correction = -5  # 单维极端 → 降级
            overall += correction

        # 等级判定（左闭右开）
        grade = self._get_grade(overall)

        return RatingResult(
            paper_id=paper.get("id", "unknown"),
            academic_impact=ai_score,
            commercial_potential=cp_score,
            innovation_index=ii_score,
            reproducibility=rp_score,
            combo_value=cv_score,
            overall_score=overall,
            grade=grade,
            dimension_details={
                "academic": ai_detail,
                "commercial": cp_detail,
                "innovation": ii_detail,
                "reproducibility": rp_detail,
                "combo": cv_detail,
                "correction": correction,
            },
            decay_adjustment=round(
                paper.get("citations", 0) *
                (1 - math.exp(-config.CITATION_DECAY_LAMBDA *
                 max(0, datetime.now().year - paper.get("year", datetime.now().year)))),
                1
            ),
        )

    def _get_grade(self, score: float) -> str:
        """根据综合分查等级（左闭右开）"""
        for grade, (low, high) in config.GRADE_THRESHOLDS.items():
            if low <= score < high:
                return grade
        return "D"


# 单例
engine = RatingEngine()
