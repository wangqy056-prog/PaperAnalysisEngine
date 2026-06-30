/**
 * PAE Rating for Zotero - Bootstrap 入口
 *
 * 功能：在 Zotero 保存论文条目时，自动调用 PAE API 查询评级，
 *      并给条目添加彩色评分徽章（S/A/B/C/D）。
 *
 * Zotero 7+ only（基于 WebExtensions API）
 */

// PAE API 基础地址（用户可在 preferences 中修改）
const DEFAULT_PAE_API = 'http://localhost:8001/api';

// 评级颜色映射（与 PAE 前端 gradeColor 一致）
const GRADE_COLORS = {
  S: '#ff4444',  // 红色 - 顶级
  A: '#ff8800',  // 橙色 - 优秀
  B: '#ffcc00',  // 黄色 - 良好
  C: '#88cc00',  // 绿色 - 中等
  D: '#88aaff',  // 蓝色 - 较低
};

// 请求队列（避免批量导入时打爆 API，2 秒 1 个请求）
const REQUEST_INTERVAL_MS = 2000;
let lastRequestTime = 0;
const pendingQueue = [];
let queueRunning = false;

// 已查询过的 DOI 缓存（避免重复查询）
const doiCache = new Map();

/**
 * 获取 PAE API 地址（从 Zotero preferences 读取，默认本地）
 */
function getPaeApi() {
  try {
    return Zotero.Prefs.get('extensions.pae-rating.api') || DEFAULT_PAE_API;
  } catch (e) {
    return DEFAULT_PAE_API;
  }
}

/**
 * 查询论文评级（通过 DOI）
 */
async function queryRatingByDOI(doi) {
  if (!doi) return null;

  // 命中缓存直接返回
  if (doiCache.has(doi)) {
    return doiCache.get(doi);
  }

  // 限速：确保两次请求间隔至少 2 秒
  const now = Date.now();
  const elapsed = now - lastRequestTime;
  if (elapsed < REQUEST_INTERVAL_MS) {
    await new Promise(resolve => setTimeout(resolve, REQUEST_INTERVAL_MS - elapsed));
  }
  lastRequestTime = Date.now();

  const apiBase = getPaeApi();
  const url = `${apiBase}/paper/by-doi/${encodeURIComponent(doi)}/rating`;

  try {
    const res = await fetch(url, {
      method: 'GET',
      headers: { 'Accept': 'application/json' },
    });

    if (res.status === 404) {
      // 论文不在数据库，缓存 null 避免重复查询
      doiCache.set(doi, null);
      return null;
    }
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    const data = await res.json();
    doiCache.set(doi, data);
    return data;
  } catch (e) {
    Zotero.debug(`[PAE] 查询 DOI ${doi} 失败：${e.message}`);
    return null;
  }
}

/**
 * 给 Zotero 条目添加评级标签
 */
function addRatingTag(item, ratingData) {
  if (!ratingData || !ratingData.grade) return;

  const grade = ratingData.grade;
  const tagName = `PAE:${grade}`;
  const color = GRADE_COLORS[grade] || '#aaaaaa';

  // 避免重复添加
  const existingTags = item.getTags();
  if (existingTags.some(t => t.tag && t.tag.startsWith('PAE:'))) {
    // 移除旧的 PAE 标签
    item.removeTags(existingTags.filter(t => t.tag && t.tag.startsWith('PAE:')).map(t => t.tag));
  }

  // 添加新标签（Zotero 7 用 addTag）
  try {
    item.addTag(tagName);
    item.saveTx();

    // 设置标签颜色（通过 Zotero 标签颜色 API）
    const libraryID = item.libraryID;
    Zotero.Tags.setColor(libraryID, tagName, color);
    Zotero.debug(`[PAE] 已给条目 ${item.key} 添加评级标签 ${tagName} (color: ${color})`);
  } catch (e) {
    Zotero.debug(`[PAE] 添加标签失败：${e.message}`);
  }
}

/**
 * 处理单个条目：查询评级 + 标注标签
 */
async function processItem(item) {
  try {
    // 只处理期刊文章、会议论文等有 DOI 的条目
    if (!item.isRegularItem()) return;

    const doi = item.getField('DOI');
    if (!doi) {
      Zotero.debug(`[PAE] 条目 ${item.key} 无 DOI，跳过`);
      return;
    }

    Zotero.debug(`[PAE] 查询条目 ${item.key} DOI: ${doi}`);
    const ratingData = await queryRatingByDOI(doi);

    if (ratingData) {
      addRatingTag(item, ratingData);
    } else {
      Zotero.debug(`[PAE] DOI ${doi} 不在 PAE 数据库中（请先在 PAE 搜索导入）`);
    }
  } catch (e) {
    Zotero.debug(`[PAE] 处理条目失败：${e.message}`);
  }
}

/**
 * 请求队列处理器（串行处理，避免并发）
 */
async function processQueue() {
  if (queueRunning) return;
  queueRunning = true;

  while (pendingQueue.length > 0) {
    const item = pendingQueue.shift();
    await processItem(item);
  }

  queueRunning = false;
}

/**
 * 入队条目（批量导入时自动限速）
 */
function enqueueItem(item) {
  pendingQueue.push(item);
  processQueue();
}

/**
 * 监听条目添加事件
 */
function onItemAdded(event) {
  const item = event && event.data;
  if (!item) return;

  // 延迟 500ms 等待元数据填充（特别是 DOI）
  setTimeout(() => {
    // 重新获取完整的 item 对象
    const zoteroItem = Zotero.Items.get(item.id) || item;
    enqueueItem(zoteroItem);
  }, 500);
}

/**
 * 注册命令：手动查询选中条目的评级
 */
function registerCommands() {
  try {
    // 在条目右键菜单添加"查询 PAE 评级"按钮
    Zotero.ItemTree.addContextMenuOption({
      id: 'pae-query-rating',
      label: '查询 PAE 评级',
      onExecute: async (items) => {
        if (!items || !items.length) return;
        for (const item of items) {
          await processItem(item);
        }
        Zotero.debug(`[PAE] 已查询 ${items.length} 个条目的评级`);
      },
    });
  } catch (e) {
    Zotero.debug(`[PAE] 注册右键菜单失败：${e.message}`);
  }
}

// ==================== Zotero 7 生命周期钩子 ====================

/**
 * 插件加载（Zotero 启动或插件启用时）
 */
async function startup({ id, version, rootURI }) {
  Zotero.debug(`[PAE] 插件启动 v${version}`);

  // 注册事件监听
  Zotero.Notifier.registerObserver(
    { notify: (event, type, ids, extraData) => {
        if (event === 'add' && type === 'item') {
          ids.forEach(id => {
            const item = Zotero.Items.get(id);
            if (item) enqueueItem(item);
          });
        }
      }
    },
    ['item'],
    'pae-rating'
  );

  // 注册右键菜单命令
  registerCommands();

  Zotero.debug('[PAE] 插件启动完成，等待新条目添加...');
}

/**
 * 插件卸载
 */
function shutdown({ reason, _rootURI }) {
  Zotero.debug(`[PAE] 插件卸载 (reason: ${reason})`);
  // 清空队列和缓存
  pendingQueue.length = 0;
  doiCache.clear();
}

/**
 * 插件安装
 */
async function install({ id, version, _rootURI }) {
  Zotero.debug(`[PAE] 插件安装 v${version}`);
}

// 导出钩子（Zotero 7 bootstrap.js 规范）
var EXPORTED_SYMBOLS = ['startup', 'shutdown', 'install'];
