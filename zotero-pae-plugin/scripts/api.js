/**
 * PAE Rating for Zotero - API 封装层
 *
 * 与后端 /api/paper/by-doi/{doi}/rating 端点交互
 */

const PAE_API_BASE = () => {
  try {
    return Zotero.Prefs.get('extensions.pae-rating.api') || 'http://localhost:8001/api';
  } catch (e) {
    return 'http://localhost:8001/api';
  }
};

/**
 * 通过 DOI 查询论文评级
 * @param {string} doi - 论文 DOI
 * @returns {Promise<Object|null>} 评级数据，未找到返回 null
 */
async function queryRatingByDOI(doi) {
  if (!doi) return null;

  const url = `${PAE_API_BASE()}/paper/by-doi/${encodeURIComponent(doi)}/rating`;

  try {
    const res = await fetch(url, {
      method: 'GET',
      headers: { 'Accept': 'application/json' },
    });

    if (res.status === 404) return null;
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    return await res.json();
  } catch (e) {
    Zotero.debug(`[PAE API] 查询失败：${e.message}`);
    return null;
  }
}

/**
 * 批量查询（带限速）
 * @param {Array<{doi: string, callback: Function}>} tasks
 */
async function batchQuery(tasks) {
  const interval = Zotero.Prefs.get('extensions.pae-rating.request-interval') || 2000;
  for (const task of tasks) {
    const result = await queryRatingByDOI(task.doi);
    task.callback(result);
    await new Promise(resolve => setTimeout(resolve, interval));
  }
}

// 导出（Zotero 7 用 Components.utils.exportFunction 或直接挂全局）
var EXPORTED_SYMBOLS = ['queryRatingByDOI', 'batchQuery'];
