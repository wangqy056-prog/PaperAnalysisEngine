"""评级引擎 - 五维量化评级公式实现"""

import math
import re
from typing import Dict, Optional


# ==================== 期刊权重表 ====================

JOURNAL_WEIGHTS = {
    # 顶级期刊
    "nature": 1.5, "science": 1.5, "cell": 1.5,
    # 高影响力
    "nature machine intelligence": 1.2, "nature methods": 1.2,
    "nature communications": 1.2, "nature physics": 1.2,
    "nature chemistry": 1.2, "nature materials": 1.2,
    "science advances": 1.2, "science robotics": 1.2,
    "proceedings of the ieee": 1.2,
    # 中等
    "ieee transactions": 1.0, "acm": 1.0, "pnas": 1.0,
    "physical review letters": 1.0, "journal of chemical physics": 1.0,
    # 预印本
    "arxiv": 0.7,
    # 默认
}


def get_journal_weight(journal: Optional[str]) -> float:
    """获取期刊权重"""
    if not journal:
        return 0.5
    j = journal.lower().strip()
    for key, weight in JOURNAL_WEIGHTS.items():
        if key in j:
            return weight
    return 0.5


# ==================== TRL 估算 ====================

TRL_KEYWORDS = {
    9: ["commercialized", "mass production", "deployed at scale"],
    8: ["commercial", "production line", "pilot plant"],
    7: ["demonstration", "field test", "real-world"],
    6: ["prototype", "engineering model", "testbed"],
    5: ["laboratory validation", "lab test", "bench test"],
    4: ["experimental validation", "proof of concept", "feasibility"],
    3: ["experimental study", "preliminary experiment"],
    2: ["theory", "theoretical framework", "conceptual"],
    1: ["basic research", "fundamental", "observation"],
}


def estimate_trl(paper: Dict) -> int:
    """估算技术成熟度等级 (1-9)"""
    abstract = (paper.get("abstract") or "").lower()
    title = (paper.get("title") or "").lower()
    text = f"{title} {abstract}"

    for trl_level, keywords in sorted(TRL_KEYWORDS.items(), reverse=True):
        for kw in keywords:
            if kw in text:
                return trl_level

    # 默认值：基于年份
    year = paper.get("year") or 2020
    if year >= 2024:
        return 5
    elif year >= 2020:
        return 4
    else:
        return 3


# ==================== 五维评级公式 ====================

def calc_academic_impact(paper: Dict) -> float:
    """
    学术影响力 = (C × T_decay × J_weight + R_rank × 25 + SS × 0.2) / 150 × 100

    • C = 引用量
    • T_decay = e^(-0.1 × 年数差)，10年衰减一半
    • J_weight = 期刊权重
    • R_rank = 领域排名评分（简化为引用量估算）
    • SS = 影响力评分（简化为引用量映射）
    """
    current_year = 2026
    paper_year = paper.get("year") or current_year
    citations = paper.get("citations") or 0

    # 时间衰减
    years_diff = max(0, current_year - paper_year)
    t_decay = math.exp(-0.1 * years_diff)

    # 期刊权重
    j_weight = get_journal_weight(paper.get("journal"))

    # 引用量评分
    citation_score = citations * t_decay * j_weight

    # 领域排名（简化：引用量映射到0-25）
    rank_score = min(25, citations / 100 * 5)

    # 影响力评分（简化：引用量映射到0-20）
    ss_score = min(100, citations * 2)

    # 综合计算
    z = 150  # 标准化因子
    score = (citation_score + rank_score * 25 + ss_score * 0.2) / z * 100

    return round(min(100, max(0, score)), 1)


def calc_commercial_potential(paper: Dict, patent_count: int = 0,
                               market_size: float = 0, competition: str = "medium") -> float:
    """
    商业潜力 = (TRL×4 + Patent_score + Market_score + Competition_score) × T_factor

    • TRL = 技术成熟度等级 (1-9)
    • Patent_score = min(25, ln(专利数+1) × 10)
    • Market_score = 市场规模评分
    • Competition_score = 竞争格局评分
    • T_factor = 时间修正因子
    """
    trl = estimate_trl(paper)
    trl_score = trl * 4  # TRL 9 → 36

    # 专利评分
    patent_score = min(25, math.log(patent_count + 1) * 10)

    # 市场规模评分
    if market_size >= 10_000_000_000:
        market_score = 20
    elif market_size >= 1_000_000_000:
        market_score = 15
    elif market_size >= 100_000_000:
        market_score = 10
    else:
        market_score = 5

    # 竞争格局评分
    comp_scores = {"low": 15, "medium": 10, "high": 5}
    comp_score = comp_scores.get(competition, 10)

    # 时间修正因子
    if trl >= 7:
        t_factor = 1.2
    elif trl <= 3:
        t_factor = 0.8
    else:
        t_factor = 1.0

    # 综合计算
    score = (trl_score + patent_score + market_score + comp_score) * t_factor

    return round(min(100, max(0, score)), 1)


def calc_innovation_index(paper: Dict, llm_scores: Optional[Dict] = None) -> float:
    """
    创新指数 = 原创性×35 + 方法创新×25 + 理论贡献×20 + 实验验证×20

    各子评分通过关键词分析或LLM分析得出 (0-1)
    """
    abstract = (paper.get("abstract") or "").lower()
    title = (paper.get("title") or "").lower()
    text = f"{title} {abstract}"

    if llm_scores:
        originality = llm_scores.get("originality", 0.5)
        method_innovation = llm_scores.get("method_innovation", 0.5)
        theory_contribution = llm_scores.get("theory_contribution", 0.5)
    else:
        # 关键词估算
        novel_keywords = ["novel", "new", "first", "unprecedented", "breakthrough", "innovative"]
        originality = 0.8 if any(kw in text for kw in novel_keywords) else 0.4

        method_keywords = ["method", "approach", "algorithm", "framework", "architecture", "pipeline"]
        method_innovation = 0.7 if any(kw in text for kw in method_keywords) else 0.4

        theory_keywords = ["theory", "theorem", "proof", "mathematical", "formal", "analytical"]
        theory_contribution = 0.6 if any(kw in text for kw in theory_keywords) else 0.3

    # 实验验证评分
    exp_keywords = {
        "validated": 0.9, "tested": 0.8, "experiment": 0.8,
        "simulated": 0.6, "evaluated": 0.6, "measured": 0.7,
        "demonstrated": 0.7,
    }
    experimental_validation = 0.2
    for kw, score in exp_keywords.items():
        if kw in text:
            experimental_validation = max(experimental_validation, score)
            break

    # 综合计算
    score = (
        originality * 35 +
        method_innovation * 25 +
        theory_contribution * 20 +
        experimental_validation * 20
    )

    return round(min(100, max(0, score)), 1)


def calc_reproducibility(paper: Dict) -> float:
    """
    可复现性 = Σ(各项检查得分)

    • 数据公开: +30
    • 代码公开: +25
    • 实验细节: +25
    • 可复现标记: +20
    """
    abstract = (paper.get("abstract") or "").lower()
    text = abstract

    # 解析所有可用文本
    pdf_url = paper.get("pdf_url") or ""
    url = paper.get("url") or ""

    score = 0

    # 1. 数据公开检查
    data_keywords = ["data available", "dataset", "open data", "publicly available", "data repository"]
    if any(kw in text for kw in data_keywords):
        score += 30
    elif "data" in text:
        score += 15

    # 2. 代码公开检查
    code_keywords = ["github.com", "code available", "open source", "source code", "github.io", "gitlab"]
    all_text = f"{text} {url} {pdf_url}"
    if any(kw in all_text for kw in code_keywords):
        score += 25
    elif "implementation" in text or "code" in text:
        score += 12

    # 3. 实验细节检查
    if "method" in text and "parameter" in text:
        score += 25
    elif "method" in text or "experiment" in text:
        score += 15

    # 4. 可复现标记检查
    repro_keywords = ["replicable", "reproducible", "reproducibility", "replication"]
    if any(kw in text for kw in repro_keywords):
        score += 20
    elif "open source" in text:
        score += 10

    return min(100, score)


def calc_combo_value(paper: Dict, related_papers: Optional[list] = None) -> float:
    """
    组合价值 = 方法互补×30 + 场景扩展×25 + 技术叠加×25 + 商业协同×20

    第一阶段默认值50，后续结合其他论文分析
    """
    if not related_papers:
        # 基于论文特征估算
        abstract = (paper.get("abstract") or "").lower()

        # 方法多样性
        methods = ["machine learning", "statistical", "experimental", "simulation",
                    "analytical", "empirical", "theoretical"]
        method_count = sum(1 for m in methods if m in abstract)
        complementarity = min(1.0, method_count / 2)

        # 场景覆盖
        scenarios = ["medical", "finance", "manufacturing", "energy", "transportation",
                     "healthcare", "education", "security"]
        scenario_count = sum(1 for s in scenarios if s in abstract)
        scenario_expansion = min(1.0, scenario_count / 2)

        # 技术叠加
        if "combined" in abstract or "integrated" in abstract or "hybrid" in abstract:
            synergy_effect = 0.8
        else:
            synergy_effect = 0.4

        # 商业协同
        if "application" in abstract or "deployment" in abstract or "practical" in abstract:
            commercial_synergy = 0.7
        else:
            commercial_synergy = 0.3

        score = (
            complementarity * 30 +
            scenario_expansion * 25 +
            synergy_effect * 25 +
            commercial_synergy * 20
        )
    else:
        # 多论文组合分析（第二阶段实现）
        score = 50

    return round(min(100, max(0, score)), 1)


# ==================== 综合评级 ====================

def rate_paper(paper: Dict, patent_count: int = 0,
               market_size: float = 0, competition: str = "medium") -> Dict:
    """
    对论文进行五维评级

    返回:
    {
        "academic_impact": float,
        "commercial_potential": float,
        "innovation_index": float,
        "reproducibility": float,
        "combo_value": float,
        "overall_score": float,
        "rating_level": str,  # S/A/B/C/D
    }
    """
    ratings = {
        "academic_impact": calc_academic_impact(paper),
        "commercial_potential": calc_commercial_potential(paper, patent_count, market_size, competition),
        "innovation_index": calc_innovation_index(paper),
        "reproducibility": calc_reproducibility(paper),
        "combo_value": calc_combo_value(paper),
    }

    # 综合评分（加权平均）
    overall = (
        ratings["academic_impact"] * 0.30 +
        ratings["commercial_potential"] * 0.25 +
        ratings["innovation_index"] * 0.20 +
        ratings["reproducibility"] * 0.15 +
        ratings["combo_value"] * 0.10
    )

    ratings["overall_score"] = round(overall, 1)

    # 评级等级
    if overall >= 90:
        ratings["rating_level"] = "S"
    elif overall >= 75:
        ratings["rating_level"] = "A"
    elif overall >= 60:
        ratings["rating_level"] = "B"
    elif overall >= 40:
        ratings["rating_level"] = "C"
    else:
        ratings["rating_level"] = "D"

    return ratings


def predict_commercialization(paper: Dict) -> Dict:
    """预测商业化时间线"""
    trl = estimate_trl(paper)

    # 基础时间估算
    if trl <= 3:
        base_time = "5-10年"
    elif trl <= 6:
        base_time = "3-5年"
    elif trl <= 8:
        base_time = "1-3年"
    else:
        base_time = "0-1年"

    # 加速/减速因子
    factors = []
    abstract = (paper.get("abstract") or "").lower()

    if "patent" in abstract:
        factors.append("有专利布局，可能加速商业化")
    if "funding" in abstract or "investment" in abstract:
        factors.append("有资金支持，可能加速")
    if "competition" in abstract or "competitive" in abstract:
        factors.append("竞争存在，可能加快节奏")

    confidence = "高" if trl >= 7 else "中" if trl >= 4 else "低"

    return {
        "trl": trl,
        "base_time": base_time,
        "factors": factors,
        "confidence": confidence,
    }


# ==================== 标签生成 ====================

def generate_tags(paper: Dict) -> list:
    """基于关键词生成标签"""
    abstract = (paper.get("abstract") or "").lower()
    title = (paper.get("title") or "").lower()
    text = f"{title} {abstract}"

    tags = []

    # 学科标签
    disciplines = {
        "计算机科学": ["computer", "algorithm", "software", "machine learning", "deep learning", "neural"],
        "物理学": ["physics", "quantum", "particle", "energy", "material"],
        "生物学": ["biology", "cell", "gene", "protein", "biological", "biomedical"],
        "化学": ["chemistry", "chemical", "molecular", "synthesis", "catalyst"],
        "医学": ["medical", "clinical", "patient", "treatment", "disease", "therapy"],
        "工程学": ["engineering", "mechanical", "electrical", "structural"],
    }

    for discipline, keywords in disciplines.items():
        if any(kw in text for kw in keywords):
            tags.append({"name": discipline, "category": "discipline", "confidence": 0.9})

    # 技术标签
    tech_keywords = {
        "LLM": ["large language model", "llm", "gpt", "transformer", "bert"],
        "计算机视觉": ["computer vision", "image", "object detection", "segmentation", "cnn"],
        "量子计算": ["quantum computing", "qubit", "quantum circuit"],
        "固态电池": ["solid-state battery", "solid electrolyte"],
        "钙钛矿": ["perovskite", "solar cell"],
        "自动驾驶": ["autonomous driving", "self-driving", "autonomous vehicle"],
        "机器人": ["robot", "robotics", "manipulation"],
        "纳米技术": ["nanotechnology", "nanoparticle", "nanostructure"],
    }

    for tech, keywords in tech_keywords.items():
        if any(kw in text for kw in keywords):
            tags.append({"name": tech, "category": "technology", "confidence": 0.85})

    # 创新类型标签
    if "review" in text or "survey" in text:
        tags.append({"name": "综述", "category": "innovation_type", "confidence": 0.9})
    elif "theory" in text or "theoretical" in text:
        tags.append({"name": "基础研究", "category": "innovation_type", "confidence": 0.8})
    elif "experiment" in text or "validated" in text:
        tags.append({"name": "应用研究", "category": "innovation_type", "confidence": 0.8})
    else:
        tags.append({"name": "工程实现", "category": "innovation_type", "confidence": 0.6})

    # TRL标签
    trl = estimate_trl(paper)
    if trl <= 3:
        trl_label = "基础研究阶段"
    elif trl <= 6:
        trl_label = "技术开发阶段"
    else:
        trl_label = "商业化阶段"
    tags.append({"name": f"TRL {trl} - {trl_label}", "category": "trl", "confidence": 0.7})

    return tags


if __name__ == "__main__":
    # 测试评级
    test_paper = {
        "title": "A Novel Approach to Large Language Model Training",
        "abstract": "We propose a novel method for training large language models (LLMs) using a new algorithm. "
                    "The approach is validated through extensive experiments. Code available at github.com/test/repo. "
                    "Dataset is publicly available. The method demonstrates significant improvements in efficiency.",
        "journal": "Nature",
        "year": 2025,
        "citations": 500,
    }

    ratings = rate_paper(test_paper)
    print("评级结果:")
    for k, v in ratings.items():
        print(f"  {k}: {v}")

    print(f"\n商业化预测: {predict_commercialization(test_paper)}")
    print(f"\n标签: {generate_tags(test_paper)}")
