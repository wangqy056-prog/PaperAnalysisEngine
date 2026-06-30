// PAE Rating for Zotero - 默认偏好设置
//
// 用户可在 Zotero about:config 中修改以下设置：

// PAE API 地址（默认本地，部署后改为公网地址）
pref('extensions.pae-rating.api', 'http://localhost:8001/api');

// 是否在添加条目时自动查询评级
pref('extensions.pae-rating.auto-query', true);

// 请求间隔（毫秒，避免打爆 API）
pref('extensions.pae-rating.request-interval', 2000);

// 是否显示评级徽章（关闭则只查询不标注）
pref('extensions.pae-rating.show-badge', true);
