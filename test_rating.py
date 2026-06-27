"""评级引擎测试 - 使用模拟论文验证五大维度"""
from engine.database import db
from engine.rating import engine

db.init_db()

# 测试论文 1: Attention Is All You Need (顶级)
p1 = {
    "id": "test-attention",
    "title": "Attention Is All You Need",
    "abstract": "We propose the Transformer architecture based solely on attention mechanisms. "
                "Code available at github.com/tensorflow/tensor2tensor. Extensive experiments "
                "on WMT 2014 English-to-German and English-to-French translation tasks.",
    "authors": [{"name": "Ashish Vaswani"}],
    "journal": "Neural Information Processing Systems (NeurIPS)",
    "year": 2017,
    "citations": 120000,
    "reference_count": 40,
    "field": "machine learning",
    "source": "manual",
    "source_id": "attention",
}
db.insert_paper(p1)
r1 = engine.calculate(p1)

# 测试论文 2: 普通论文
p2 = {
    "id": "test-regular",
    "title": "A Study on Graph Neural Networks for Social Networks",
    "abstract": "We apply GNNs to social network analysis. Experiments show promising results.",
    "authors": [{"name": "Jane Smith"}],
    "journal": "IEEE Access",
    "year": 2023,
    "citations": 12,
    "reference_count": 25,
    "field": "computer science",
    "source": "manual",
    "source_id": "gnn",
}
db.insert_paper(p2)
r2 = engine.calculate(p2)

# 测试论文 3: 新论文（高创新潜力）
p3 = {
    "id": "test-novel",
    "title": "A Novel Quantum-Inspired Framework for Protein Folding",
    "abstract": "We present a first-of-its-kind quantum-inspired approach to predict protein structures. "
                "Our state-of-the-art method outperforms AlphaFold on novel protein families. "
                "Code and dataset publicly available at github.",
    "authors": [{"name": "Alice Chen"}],
    "journal": "Nature",
    "year": 2025,
    "citations": 8,
    "reference_count": 35,
    "field": "biotechnology, quantum computing",
    "source": "manual",
    "source_id": "quantum-protein",
}
db.insert_paper(p3)
r3 = engine.calculate(p3)

# 输出
for i, (r, p) in enumerate(zip([r1, r2, r3], [p1, p2, p3]), 1):
    print(f"{'='*60}")
    print(f"论文 {i}: {p['title'][:50]}")
    print(f"年份: {p['year']}  |  引用: {p['citations']}  |  期刊: {p['journal']}")
    print(f"综合评分: {r.overall_score:.1f}  [{r.grade}级]")
    print(f"  学术影响力:  {r.academic_impact:.1f}")
    print(f"  商业转化潜力: {r.commercial_potential:.1f}")
    print(f"  创新指数:    {r.innovation_index:.1f}")
    print(f"  可复现性:    {r.reproducibility:.1f}")
    print(f"  组合价值:    {r.combo_value:.1f}")
    print(f"  时间衰减:    {r.decay_adjustment:.1f}")
print(f"{'='*60}")
