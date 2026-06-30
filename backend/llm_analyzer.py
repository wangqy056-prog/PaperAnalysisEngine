"""LLM 智能分析模块 - 接入 DeepSeek V4 Flash + Groq Llama 3.3 70B + 智谱 GLM-4-Flash

功能:
1. AI 摘要 - 智能生成论文摘要
2. 中文翻译 - 英文摘要翻译为中文
3. 通俗解读 - 外行人也能看懂的论文总结
4. 价值评估 - 学术价值与商业价值分析
5. 功能说明 - 论文技术可以用来做什么
6. 综合分析 - 一键完成以上所有分析
"""

import os
import sys
import json
import time
import requests
from pathlib import Path
from typing import Dict, Optional

# 加载 .env 文件（从项目根目录读取）
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(env_path)
except ImportError:
    pass

# ==================== 配置 ====================
# API Key 从环境变量读取，不在源码中硬编码
# 开发环境：在 .env 文件中设置
# 生产环境：通过 Docker / 服务器环境变量设置

# DeepSeek V4 Flash（主力模型）
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-flash"

# Groq Llama 3.3 70B（高速免费模型）
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = "llama-3.3-70b-versatile"

# 智谱 GLM-4-Flash（备用模型，完全免费）
GLM_API_KEY = os.environ.get("GLM_API_KEY")
GLM_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
GLM_MODEL = "glm-4-flash"

# 当前使用的模型
CURRENT_PROVIDER = os.environ.get("LLM_PROVIDER", "deepseek")  # "deepseek" / "groq" / "glm"


# ==================== API 调用 ====================

def _call_deepseek(messages: list, temperature: float = 0.3, max_tokens: int = 2000) -> Optional[str]:
    """调用 DeepSeek V4 Flash API"""
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }

    try:
        resp = requests.post(
            f"{DEEPSEEK_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        else:
            print(f"  [DeepSeek] API错误: {resp.status_code} - {resp.text[:200]}")
            return None
    except Exception as e:
        print(f"  [DeepSeek] 请求失败: {e}")
        return None


def _call_glm(messages: list, temperature: float = 0.3, max_tokens: int = 2000) -> Optional[str]:
    """调用智谱 GLM-4-Flash API"""
    headers = {
        "Authorization": f"Bearer {GLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }

    try:
        resp = requests.post(
            f"{GLM_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        else:
            print(f"  [GLM] API错误: {resp.status_code} - {resp.text[:200]}")
            return None
    except Exception as e:
        print(f"  [GLM] 请求失败: {e}")
        return None


def _call_groq(messages: list, temperature: float = 0.3, max_tokens: int = 2000) -> Optional[str]:
    """调用 Groq Llama 3.3 70B API（OpenAI 兼容）"""
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }

    try:
        resp = requests.post(
            f"{GROQ_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        else:
            print(f"  [Groq] API错误: {resp.status_code} - {resp.text[:200]}")
            return None
    except Exception as e:
        print(f"  [Groq] 请求失败: {e}")
        return None


def call_llm(messages: list, temperature: float = 0.3, max_tokens: int = 2000) -> Optional[str]:
    """调用 LLM，自动选择模型，失败时依次切换备用模型"""
    fallback_chain = {
        "deepseek": [_call_deepseek, _call_groq, _call_glm],
        "groq": [_call_groq, _call_deepseek, _call_glm],
        "glm": [_call_glm, _call_deepseek, _call_groq],
    }
    providers = fallback_chain.get(CURRENT_PROVIDER, [_call_deepseek, _call_groq, _call_glm])
    provider_names = {
        _call_deepseek: "DeepSeek V4 Flash",
        _call_groq: "Groq Llama 3.3 70B",
        _call_glm: "GLM-4-Flash",
    }

    for i, provider in enumerate(providers):
        result = provider(messages, temperature, max_tokens)
        if result:
            return result
        if i < len(providers) - 1:
            next_name = provider_names[providers[i + 1]]
            print(f"  [LLM] 切换到备用模型 {next_name}...")

    return None


def switch_provider(provider: str = "deepseek"):
    """切换 LLM 提供商"""
    global CURRENT_PROVIDER
    if provider in ("deepseek", "groq", "glm"):
        CURRENT_PROVIDER = provider
        name_map = {
            "deepseek": "DeepSeek V4 Flash",
            "groq": "Groq Llama 3.3 70B",
            "glm": "GLM-4-Flash",
        }
        name = name_map.get(provider, provider)
        print(f"  [LLM] 已切换到 {name}")
    else:
        print(f"  [LLM] 未知提供商: {provider}")


# ==================== 工具函数 ====================

def _norm(paper: Dict) -> Dict:
    """标准化 paper 字段，确保所有字符串字段不为 None"""
    normalized = dict(paper)
    for key in ("title", "abstract", "journal", "doi", "url", "pdf_url", "source"):
        val = normalized.get(key)
        if val is None:
            normalized[key] = ""
    normalized.setdefault("year", "N/A")
    normalized.setdefault("citations", 0)
    return normalized


# ==================== 分析功能 ====================

def summarize_paper(paper: Dict) -> str:
    """AI 生成论文摘要"""
    p = _norm(paper)
    title = p["title"]
    abstract = p["abstract"]
    journal = p["journal"]
    year = p["year"]

    if not abstract:
        return "无法生成摘要：论文没有摘要信息"

    prompt = f"""请为以下学术论文生成一段简洁的中文摘要（200-300字），突出核心贡献和关键发现：

标题：{title}
期刊：{journal} ({year})
摘要：{abstract[:2000]}

要求：
1. 用中文输出
2. 突出研究目标、方法、关键结果和意义
3. 语言简洁专业
"""

    messages = [{"role": "user", "content": prompt}]
    return call_llm(messages, temperature=0.3, max_tokens=500) or "摘要生成失败"


def translate_abstract(paper: Dict) -> str:
    """翻译英文摘要为中文"""
    p = _norm(paper)
    title = p["title"]
    abstract = p["abstract"]

    if not abstract:
        return "无法翻译：论文没有摘要信息"

    # 如果摘要已经是中文，直接返回
    if any('\u4e00' <= ch <= '\u9fff' for ch in abstract[:100]):
        return f"摘要已经是中文，无需翻译：\n\n{abstract}"

    prompt = f"""请将以下英文学术论文的标题和摘要翻译为中文。要求：
1. 学术用语准确
2. 语句通顺自然
3. 保留专业术语的英文原文（括号标注）

标题：{title}

摘要：
{abstract[:2000]}

请按以下格式输出：
【中文标题】
【中文摘要】
"""

    messages = [{"role": "user", "content": prompt}]
    return call_llm(messages, temperature=0.2, max_tokens=1500) or "翻译失败"


def plain_language_summary(paper: Dict) -> str:
    """生成外行人也能看懂的通俗解读"""
    p = _norm(paper)
    title = p["title"]
    abstract = p["abstract"]

    if not abstract:
        return "无法生成解读：论文没有摘要信息"

    prompt = f"""请用最通俗的语言解释这篇论文，让完全不懂这个领域的外行人也能理解。

论文标题：{title}
论文摘要：{abstract[:2000]}

请按以下格式输出：

【一句话总结】
（用一句话说清楚这篇论文做了什么）

【这是什么】
（用生活中的例子类比，解释论文研究的问题）

【怎么做的】
（用简单的语言解释方法，不用专业术语）

【有什么用】
（这项研究对普通人有什么影响）

【有趣的地方】
（这项研究最有趣或最令人惊讶的点）
"""

    messages = [{"role": "user", "content": prompt}]
    return call_llm(messages, temperature=0.5, max_tokens=1500) or "解读生成失败"


def assess_value(paper: Dict) -> str:
    """评估论文的学术价值和商业价值"""
    p = _norm(paper)
    title = p["title"]
    abstract = p["abstract"]
    journal = p["journal"]
    year = p["year"]
    citations = p["citations"]

    prompt = f"""请评估以下论文的学术价值和商业价值。

标题：{title}
期刊：{journal} ({year})
引用量：{citations}
摘要：{abstract[:2000]}

请按以下格式输出：

【学术价值评估】
- 理论贡献：（高/中/低，说明理由）
- 方法创新：（高/中/低，说明理由）
- 影响力：（基于引用量和期刊评估）

【商业价值评估】
- 技术成熟度：TRL X（1=基础研究, 9=已商业化）
- 应用场景：（列举2-3个潜在应用场景）
- 商业化时间线：（预计多久能落地）
- 市场潜力：（大/中/小，说明理由）

【投资建议】
- 推荐指数：⭐⭐⭐⭐⭐（1-5星）
- 关注理由：（简短说明）
"""

    messages = [{"role": "user", "content": prompt}]
    return call_llm(messages, temperature=0.3, max_tokens=1000) or "价值评估失败"


def functional_description(paper: Dict) -> str:
    """生成功能性说明 - 这项技术可以用来做什么"""
    p = _norm(paper)
    title = p["title"]
    abstract = p["abstract"]

    if not abstract:
        return "无法生成功能说明：论文没有摘要信息"

    prompt = f"""基于以下论文，分析这项技术/方法可以用来做什么，以及如何应用。

论文标题：{title}
论文摘要：{abstract[:2000]}

请按以下格式输出：

【核心技术】
（用一句话概括论文的核心技术/方法）

【直接应用】
1. （应用场景1：具体说明如何用）
2. （应用场景2：具体说明如何用）
3. （应用场景3：具体说明如何用）

【间接应用】
1. （通过组合或扩展，还能用在哪里）
2. （跨界应用可能性）

【限制条件】
（使用这项技术需要什么前提条件或资源）

【替代方案】
（目前有没有类似的技术，各有什么优劣）
"""

    messages = [{"role": "user", "content": prompt}]
    return call_llm(messages, temperature=0.4, max_tokens=1200) or "功能说明生成失败"


def deep_analysis(paper: Dict) -> str:
    """AI 综合深度分析（单次 LLM 调用，生成结构化综合报告）

    注意：不再是串行调用 5 个分析函数（那样会超时），而是一次性生成综合报告。
    其他 5 种分析（摘要/翻译/解读/评估/说明）已通过前端并行调用各自独立 API 完成。
    """
    p = _norm(paper)
    title = p["title"]
    abstract = p["abstract"]
    journal = p["journal"]
    year = p["year"]
    citations = p["citations"]

    if not abstract:
        return "无法生成综合分析：论文没有摘要信息"

    prompt = f"""请对以下论文进行综合性深度分析，输出一份结构化的分析报告。

标题：{title}
期刊：{journal} ({year})
引用量：{citations}
摘要：{abstract[:2000]}

请按以下格式输出（每节 2-3 句话即可）：

【一、研究背景与动机】
论文解决什么问题，为什么重要

【二、核心方法与创新点】
技术方法、关键创新

【三、实验结果分析】
关键实验数据、性能提升

【四、学术影响力评估】
对领域的影响、引用潜力

【五、商业应用前景】
可落地的应用场景、市场价值

【六、局限性与改进方向】
论文的不足、可扩展方向

【七、综合评分】
- 学术价值：X/10
- 商业潜力：X/10
- 创新指数：X/10
- 推荐等级：A/B/C/D

【八、一句话总结】
用一句话总结这篇论文的核心价值
"""

    messages = [{"role": "user", "content": prompt}]
    return call_llm(messages, temperature=0.4, max_tokens=2000) or "综合分析生成失败"


def compare_papers_ai(paper1: Dict, paper2: Dict) -> str:
    """AI 对比两篇论文"""
    p1 = _norm(paper1)
    p2 = _norm(paper2)
    p1_title = p1["title"]
    p1_abstract = p1["abstract"]
    p2_title = p2["title"]
    p2_abstract = p2["abstract"]

    prompt = f"""请对比以下两篇论文的异同和优劣。

论文A：
标题：{p1_title}
摘要：{p1_abstract[:1000]}

论文B：
标题：{p2_title}
摘要：{p2_abstract[:1000]}

请按以下格式输出：

【核心对比】
| 维度 | 论文A | 论文B |
|------|-------|-------|
| 研究目标 | ... | ... |
| 方法 | ... | ... |
| 创新点 | ... | ... |
| 应用场景 | ... | ... |

【关键差异】
（两篇论文最大的3个差异）

【互补性分析】
（两篇论文是否可以组合使用，如何组合）

【推荐】
- 优先阅读：论文A 或 论文B
- 理由：...
"""

    messages = [{"role": "user", "content": prompt}]
    return call_llm(messages, temperature=0.3, max_tokens=1500) or "对比分析失败"


# ==================== 测试 ====================

if __name__ == "__main__":
    test_paper = {
        "title": "Large language models encode clinical knowledge",
        "abstract": "Large language models (LLMs) have demonstrated remarkable capabilities in natural language understanding and generation. In this study, we evaluate the clinical knowledge encoded in LLMs by testing them on medical licensing exams across multiple countries. Our results show that LLMs can achieve passing scores on medical licensing exams, suggesting that these models encode significant clinical knowledge. We further analyze the types of questions that LLMs struggle with and identify areas for improvement. The findings have implications for the application of LLMs in clinical decision support and medical education.",
        "journal": "Nature",
        "year": 2023,
        "citations": 3202,
    }

    print("=" * 60)
    print("  LLM 分析模块测试")
    print("=" * 60)

    print("\n--- 1. 中文摘要 ---")
    print(summarize_paper(test_paper))

    print("\n--- 2. 通俗解读 ---")
    print(plain_language_summary(test_paper))

    print("\n--- 3. 价值评估 ---")
    print(assess_value(test_paper))
