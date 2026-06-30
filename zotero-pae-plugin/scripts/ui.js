/**
 * PAE Rating for Zotero - UI 辅助
 *
 * 处理评级标签的添加/移除/着色
 */

const GRADE_COLORS = {
  S: '#ff4444',  // 红色
  A: '#ff8800',  // 橙色
  B: '#ffcc00',  // 黄色
  C: '#88cc00',  // 绿色
  D: '#88aaff',  // 蓝色
};

/**
 * 给 Zotero 条目添加 PAE 评级标签
 * @param {ZoteroItem} item - Zotero 条目
 * @param {Object} ratingData - PAE API 返回的评级数据
 */
function addRatingTag(item, ratingData) {
  if (!ratingData || !ratingData.grade) return;

  const grade = ratingData.grade;
  const tagName = `PAE:${grade}`;
  const color = GRADE_COLORS[grade] || '#aaaaaa';

  // 移除旧的 PAE 标签（避免重复）
  const existingTags = item.getTags();
  const oldTags = existingTags
    .filter(t => t.tag && t.tag.startsWith('PAE:'))
    .map(t => t.tag);
  if (oldTags.length) {
    item.removeTags(oldTags);
  }

  // 添加新标签
  try {
    item.addTag(tagName);
    item.saveTx();

    // 设置标签颜色（在条目树中显示彩色徽章）
    Zotero.Tags.setColor(item.libraryID, tagName, color);

    Zotero.debug(`[PAE UI] 条目 ${item.key} 标签已更新：${tagName}`);
  } catch (e) {
    Zotero.debug(`[PAE UI] 添加标签失败：${e.message}`);
  }
}

/**
 * 移除条目上的所有 PAE 标签
 */
function removeRatingTags(item) {
  const existingTags = item.getTags();
  const paeTags = existingTags
    .filter(t => t.tag && t.tag.startsWith('PAE:'))
    .map(t => t.tag);
  if (paeTags.length) {
    item.removeTags(paeTags);
    item.saveTx();
  }
}

var EXPORTED_SYMBOLS = ['addRatingTag', 'removeRatingTags', 'GRADE_COLORS'];
