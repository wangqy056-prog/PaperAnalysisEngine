"""Paper Analysis Engine - Configuration"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class RatingConfig:
    """评级体系配置 - 参考 ICAS 双坐标系设计"""

    # === 权重分配 ===
    ACADEMIC_WEIGHT: float = 0.30  # 学术影响力
    COMMERCIAL_WEIGHT: float = 0.25  # 商业转化潜力
    INNOVATION_WEIGHT: float = 0.20  # 创新指数
    REPRODUCIBILITY_WEIGHT: float = 0.15  # 可复现性
    COMBO_WEIGHT: float = 0.10  # 组合价值

    # === 等级阈值（左闭右开，校准后适配实际数据分布） ===
    GRADE_THRESHOLDS: Dict[str, tuple] = field(default_factory=lambda: {
        "S": (50, 101),  # 顶级突破
        "A": (45, 50),   # 高影响力
        "B": (38, 45),   # 中等影响力
        "C": (30, 38),   # 低影响力
        "D": (0, 30),    # 无显著价值
    })

    # === 引用量时间衰减 ===
    # λ = ln(2) / half_life_years
    CITATION_HALF_LIFE: float = 5.0  # 引用量半衰期（年）
    CITATION_DECAY_LAMBDA: float = 0.693 / 5.0  # 衰减系数

    # === 期刊/会议分级 ===
    TOP_JOURNALS: List[str] = field(default_factory=lambda: [
        # 顶级综合期刊
        "nature", "science", "cell", "nejm", "the lancet",
        "pnas", "nature communications", "science advances",
        # 顶级 CS/AI 会议
        "neurips", "icml", "iclr", "cvpr", "iccv", "eccv",
        "acl", "emnlp", "naacl", "aaai", "ijcai",
        "siggraph", "sosp", "osdi", "stoc", "focs",
    ])
    HIGH_IMPACT_JOURNALS: List[str] = field(default_factory=lambda: [
        "nature medicine", "nature biotechnology", "nature methods",
        "cell stem cell", "immunity", "cancer cell", "jama",
        # CS/AI 高影响会议/期刊
        "ijcv", "tpami", "jmlr", "ieee access",
        "icdm", "wsdm", "kdd", "sigmod", "vldb",
    ])

    # === API 配置 ===
    SEMANTIC_SCHOLAR_BASE: str = "https://api.semanticscholar.org/graph/v1"
    OPENALEX_BASE: str = "https://api.openalex.org"
    ARXIV_BASE: str = "https://export.arxiv.org/api"

    # === 数据库 ===
    DB_PATH: str = "data/papers.db"


# 全局配置实例
config = RatingConfig()
