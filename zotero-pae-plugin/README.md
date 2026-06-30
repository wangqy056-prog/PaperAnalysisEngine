# PAE Rating for Zotero

在 Zotero 7 中自动显示论文 PAE 五维评级徽章。

## 安装

### 方式 1：开发者模式（开发期）

1. 打开 Zotero 7
2. 编辑 → 首选项 → 高级 → 编辑器
3. 搜索 `extensions.zotero.allowUnverifiedExtensions`，设为 `true`
4. 工具 → 插件 → 齿轮图标 → "Install Add-on From File"
5. 选择本目录下的 `manifest.json`（或将整个目录打包为 .zip 后改名为 .xpi）

### 方式 2：正式发布（待 XPI 打包）

```bash
# 在本目录下打包
zip -r pae-rating.xpi manifest.json bootstrap.js chrome.manifest scripts/ defaults/
```

然后通过 Zotero 插件页面安装 .xpi 文件。

## 配置

安装后修改 `about:config` 中以下偏好：

| 偏好键 | 默认值 | 说明 |
|--------|--------|------|
| `extensions.pae-rating.api` | `http://localhost:8001/api` | PAE API 地址 |
| `extensions.pae-rating.auto-query` | `true` | 添加条目时自动查询 |
| `extensions.pae-rating.request-interval` | `2000` | 请求间隔（毫秒） |
| `extensions.pae-rating.show-badge` | `true` | 是否显示评级徽章 |

## 使用

### 自动模式

启用后，往 Zotero 添加论文（手动/浏览器抓取/批量导入）时，插件自动：
1. 提取论文 DOI
2. 调用 PAE API 查询评级
3. 给条目添加彩色徽章标签 `PAE:S` / `PAE:A` / `PAE:B` / `PAE:C` / `PAE:D`

评级颜色：
- 🔴 S（红色）- 顶级论文
- 🟠 A（橙色）- 优秀
- 🟡 B（黄色）- 良好
- 🟢 C（绿色）- 中等
- 🔵 D（蓝色）- 较低

### 手动模式

右键点击 Zotero 条目树中的论文 → "查询 PAE 评级"

## 注意事项

- **Zotero 7 only**（不兼容 Zotero 6）
- 论文必须**先在 PAE 中导入并评级**，否则 API 返回 404
- 批量导入时自动限速（2 秒 1 个请求），100 篇论文约需 3 分钟
- 重复查询相同 DOI 会命中本地缓存，不重复发请求

## 故障排查

| 问题 | 解决方案 |
|------|---------|
| 标签没出现 | 检查 PAE 后端是否运行 `curl http://localhost:8001/api/stats` |
| 404 错误 | 论文未在 PAE 数据库，先在 PAE Web UI 搜索导入 |
| DOI 为空 | Zotero 条目缺少 DOI，手动补全或使用 arXiv ID（暂不支持） |
| 标签颜色不对 | 检查 `Zotero.Tags.setColor` 是否被调用，查看 Zotero 调试日志 |

## 开发

修改 `bootstrap.js` 后，在 Zotero 中重启插件即可生效：
工具 → 插件 → 找到 "PAE Rating" → 禁用 → 启用

调试日志：
```
Zotero 帮助 → 调试输出日志记录 → 查看 → 搜索 "[PAE]"
```
