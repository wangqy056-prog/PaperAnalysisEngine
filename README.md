# 📊 Paper Analysis Engine

> **为学术论文提供智能评级、商业化预测与知识图谱的一站式分析平台**

[![License](https://img.shields.io/github/license/PaperAnalysisEngine/PaperAnalysisEngine.svg)](https://github.com/PaperAnalysisEngine/PaperAnalysisEngine/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green.svg)](https://fastapi.tiangolo.com/)
[![Vue 3](https://img.shields.io/badge/Vue-3.4+-brightgreen.svg)](https://vuejs.org/)
[![Docker](https://img.shields.io/badge/Docker-24.0+-blue.svg)](https://www.docker.com/)

---

## ✨ 核心功能

| 功能 | 描述 |
|------|------|
| 🎯 **五维智能评级** | 学术影响力、商业潜力、创新指数、可复现性、组合价值，一键评分 |
| 📈 **商业化预测** | TRL 技术成熟度评估、预计商业化时间、置信度分析 |
| 🔍 **智能搜索** | 支持 OpenAlex、arXiv、领研网多数据源搜索与导入 |
| 🕸️ **知识图谱** | 领域共现、作者合作、关键词共现、论文相似、引用网络五种图谱 |
| 🤖 **AI 深度分析** | 摘要生成、中文翻译、通俗解读、价值评估、功能说明、综合分析 |
| 📱 **响应式 UI** | Vue 3 + Element Plus，支持桌面端与移动端 |
| 🐳 **一键部署** | Docker + docker-compose，5 分钟启动完整应用 |

---

## 🚀 快速开始

### 环境要求

- Docker 24.0+
- Docker Compose 2.0+

### 1. 配置 API Key

复制 `.env.example` 为 `.env` 并填入你的 API Key：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```env
# 智谱 GLM-4-Flash（主模型，完全免费）
GLM_API_KEY=your_glm_api_key

# Groq Llama 3.3 70B（备模型，免费限额）
GROQ_API_KEY=your_groq_api_key

# DeepSeek V4 Flash（末选，付费）
DEEPSEEK_API_KEY=your_deepseek_api_key
```

### 2. 一键启动

```bash
docker-compose up --build
```

### 3. 访问应用

- **前端页面**: http://localhost:5173
- **API 文档**: http://localhost:8001/docs
- **后端状态**: http://localhost:8001/

---

## 📖 使用方式

### Web UI

启动后访问 http://localhost:5173，支持以下功能：

1. **仪表盘** - 论文统计、评级分布、热门领域
2. **搜索论文** - 关键词搜索、按年份/引用量筛选
3. **排行榜** - 按综合评分、学术影响力、商业潜力排名
4. **AI 分析** - 单篇分析、双篇对比、模型切换
5. **知识图谱** - 五种图谱可视化
6. **领研网** - 最新中文论文抓取
7. **批量导入** - 按主题/分类批量导入

### CLI 命令

```bash
# 进入后端容器
docker exec -it paper-analysis-backend bash

# 按主题导入论文
python import_papers.py topic "quantum computing" -n 30

# 通过 DOI 导入单篇论文
python import_papers.py doi 10.1038/nature12345

# 搜索论文
python cli.py search "machine learning"

# 导出论文（CSV/JSON/BibTeX）
python cli.py export --format csv

# 趋势统计
python cli.py trends --year

# 组合分析
python cli.py combine --min-synergy 30
```

---

## 🏗️ 技术架构

```
┌─────────────────────────────────────────────────────────────┐
│                      Frontend (Vue 3)                      │
│  Element Plus  |  ECharts  |  vis-network  |  Axios        │
└───────────────────────┬─────────────────────────────────────┘
                        │ HTTP/JSON API
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                     Backend (FastAPI)                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │   API    │ │  LLM     │ │ Rating   │ │ Graph    │       │
│  │  Router  │ │Analyzer  │ │ Engine   │ │ Builder  │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
└───────────────────────┬─────────────────────────────────────┘
                        │ SQLite
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                     Database (SQLite)                       │
│  papers | ratings | tags | favorites | search_history       │
└─────────────────────────────────────────────────────────────┘
```

### 架构统一说明

| 层级 | 主实现 | 兼容层/包装层 | 说明 |
|------|--------|-------------|------|
| **DB 层** | `backend/db.py` | `engine/database.py` | engine 侧为薄兼容层，委托 backend 实现 |
| **评级引擎** | `engine/rating.py` | `backend/rating_engine.py` | backend 侧为薄包装层，调用 engine 算法 |
| **API 客户端** | `backend/paper_fetcher.py` | `engine/api_client.py` | engine 侧复用 backend 的重试逻辑 |
| **LLM 调用** | `backend/llm_analyzer.py` | - | 自动 fallback 链：glm→groq→deepseek（省钱优先） |

> ⚠️ **Streamlit UI 已废弃**：`backend/app.py` 保留供参考，新功能请使用 Vue + FastAPI 开发。完整副本见 `archive/backend_streamlit.py`。

### 技术栈

| 层级 | 技术 | 版本 |
|------|------|------|
| **后端** | FastAPI | 0.110+ |
| **前端** | Vue 3 | 3.4+ |
| **UI 框架** | Element Plus | 2.7+ |
| **图表** | ECharts | 5.5+ |
| **图谱** | vis-network | 9.1+ |
| **LLM** | 智谱 GLM-4-Flash（主） | - |
| **LLM** | Groq Llama 3.3 70B（备） | - |
| **LLM** | DeepSeek V4 Flash（末选） | - |
| **数据库** | SQLite | - |
| **部署** | Docker + docker-compose | 24.0+ |

---

## 🔌 API 端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/stats` | GET | 获取统计信息 |
| `/api/ratings` | GET | 获取评级排行榜 |
| `/api/papers/search` | GET | 搜索论文 |
| `/api/papers/{id}` | GET | 获取论文详情 |
| `/api/papers/import` | POST | 导入论文 |
| `/api/ai/summary` | POST | AI 摘要 |
| `/api/ai/translate` | POST | 中文翻译 |
| `/api/ai/deep-analysis` | POST | 综合分析 |
| `/api/knowledge-graph/{type}` | GET | 获取知识图谱 |
| `/api/linkresearcher` | GET | 领研网论文 |

完整 API 文档：http://localhost:8001/docs

---

## 📁 项目结构

```
Paper_Analysis_Engine/
├── LICENSE                    # AGPL 许可证
├── .env.example              # 环境变量模板
├── docker-compose.yml        # Docker Compose 配置
├── requirements.txt          # 根目录依赖（同步自 backend/）
├── main.py                   # CLI 入口
├── archive/                  # 归档目录（Streamlit 备份）
│   └── backend_streamlit.py  # 废弃的 Streamlit UI 副本
├── backend/
│   ├── Dockerfile           # 后端 Docker 配置
│   ├── requirements.txt     # Python 依赖
│   ├── api/
│   │   └── main.py          # FastAPI 入口
│   ├── db.py                # SQLite 数据库操作（主实现）
│   ├── llm_analyzer.py      # LLM 分析模块（fallback 链）
│   ├── rating_engine.py     # 评级引擎（薄包装层）
│   ├── knowledge_graph.py   # 知识图谱构建
│   ├── paper_fetcher.py     # 论文抓取器（主实现）
│   └── linkresearcher_spider.py  # 领研网爬虫
├── engine/
│   ├── rating.py            # 评级算法（主实现）
│   ├── database.py          # DB 兼容层
│   └── api_client.py        # API 客户端（薄包装层）
├── frontend/
│   ├── Dockerfile           # 前端 Docker 配置
│   ├── nginx.conf           # Nginx 反向代理
│   ├── package.json         # Node.js 依赖
│   ├── vite.config.js       # Vite 配置
│   └── src/
│       ├── main.js          # Vue 入口
│       ├── router/          # Vue Router
│       ├── views/           # 页面组件
│       ├── api/             # API 封装
│       └── components/      # 通用组件
└── docs/                     # 公开文档
```

---

## 📊 评级算法

### 五维评级公式

| 维度 | 权重 | 计算公式 |
|------|------|---------|
| 学术影响力 | 30% | `(引用量 × 时间衰减 × 期刊权重 + 领域排名 + 影响力评分) / 标准化因子` |
| 商业潜力 | 25% | `(TRL×4 + 专利评分 + 市场规模评分 + 竞争格局评分) × 时间修正因子` |
| 创新指数 | 20% | `原创性×35 + 方法创新×25 + 理论贡献×20 + 实验验证×20` |
| 可复现性 | 15% | `数据公开(30) + 代码公开(25) + 实验细节(25) + 可复现标记(20)` |
| 组合价值 | 10% | `方法互补×30 + 场景扩展×25 + 技术叠加×25 + 商业协同×20` |

### 评级等级

| 等级 | 综合评分 | 含义 |
|------|---------|------|
| S | ≥ 50 | 顶级论文，具有重大突破 |
| A | 45-49 | 优秀论文，具有较高影响力 |
| B | 38-44 | 良好论文，具有一定价值 |
| C | 30-37 | 中等论文，需要进一步验证 |
| D | < 30 | 较低价值，建议谨慎引用 |

---

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

### 开发流程

1. Fork 本仓库
2. 创建功能分支：`git checkout -b feature/xxx`
3. 提交代码：`git commit -m "feat: xxx"`
4. 推送到分支：`git push origin feature/xxx`
5. 创建 Pull Request

### 代码规范

- Python：遵循 PEP 8
- Vue：遵循 Airbnb JavaScript 风格
- 提交信息：`feat: xxx` / `fix: xxx` / `docs: xxx` / `refactor: xxx`

---

## 📄 许可证

本项目采用 **GNU Affero General Public License v3.0** 许可证。详见 [LICENSE](LICENSE)。

---

## 📧 联系我们

如有问题或合作意向，欢迎通过以下方式联系：

- GitHub Issues: https://github.com/PaperAnalysisEngine/PaperAnalysisEngine/issues
- 邮件: contact@paperanalysis.engine

---

**Made with ❤️ by Paper Analysis Engine Team**
