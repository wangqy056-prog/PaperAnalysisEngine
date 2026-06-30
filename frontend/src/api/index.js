import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 120000,  // LLM 调用可能较慢（综合分析 max_tokens=2000），给 120 秒
})

// ==================== 统计 ====================
export const getStats = () => api.get('/stats')
export const getRatings = (limit = 100) => api.get(`/ratings?limit=${limit}`)

// ==================== 论文 ====================
export const searchPapers = (q, limit = 20, yearFrom = 1990, minCitations = 0) =>
  api.get(`/papers/search?q=${encodeURIComponent(q)}&limit=${limit}&year_from=${yearFrom}&min_citations=${minCitations}`)

export const searchOnline = (query, limit = 20, sources = ['oa', 'arxiv']) =>
  api.post('/papers/search-online', { query, limit, sources })

export const getPaper = (paperId) => api.get(`/papers/${paperId}`)

export const importPaper = (paper) => api.post('/papers/import', paper)

export const batchImportByTitles = (titles, source = 'oa') =>
  api.post('/papers/batch-import-titles', { titles, source })

export const deletePaper = (paperId) => api.delete(`/papers/${paperId}`)

// ==================== 领研网 ====================
export const getLinkresearcher = (pages = 1, refresh = false) =>
  api.get(`/linkresearcher?pages=${pages}${refresh ? '&refresh=true' : ''}`)
export const importFromLinkresearcher = (paperTitle) =>
  api.post('/linkresearcher/import', { paper_title: paperTitle })

// ==================== 多主题导入 ====================
export const getTopicLibrary = () => api.get('/batch-import/topics')
export const runBatchImport = (categories, perTopic = 20, sources = ['oa']) =>
  api.post('/batch-import/run', { categories, per_topic: perTopic, sources })

// ==================== 知识图谱 ====================
export const getKnowledgeGraph = (graphType, limit = 50, threshold = 1) =>
  api.get(`/knowledge-graph/${graphType}?limit=${limit}&threshold=${threshold}`)
export const getKnowledgeGraphSummary = () => api.get('/knowledge-graph')

// ==================== AI 分析 ====================
export const aiSummary = (paperId) => api.post('/ai/summary', { paper_id: paperId })
export const aiTranslate = (paperId) => api.post('/ai/translate', { paper_id: paperId })
export const aiPlainSummary = (paperId) => api.post('/ai/plain-summary', { paper_id: paperId })
export const aiAssess = (paperId) => api.post('/ai/assess', { paper_id: paperId })
export const aiFunctional = (paperId) => api.post('/ai/functional', { paper_id: paperId })
export const aiDeepAnalysis = (paperId) => api.post('/ai/deep-analysis', { paper_id: paperId })
export const aiCompare = (paperId1, paperId2) =>
  api.post('/ai/compare', { paper_id_1: paperId1, paper_id_2: paperId2 })
export const aiSwitchProvider = (provider) => api.post('/ai/switch-provider', { provider })
export const aiGetProvider = () => api.get('/ai/provider')

// ==================== 推荐 ====================
export const getRecommendations = (strategy = 'hybrid', limit = 10) =>
  api.get(`/recommendations?strategy=${strategy}&limit=${limit}`)
export const recordView = (paperId) => api.post('/recommendations/view', { paper_id: paperId })
export const recordRating = (paperId, rating, comment = '') =>
  api.post('/recommendations/rate', { paper_id: paperId, rating, comment })
export const getUserProfile = () => api.get('/recommendations/profile')

// ==================== 收藏夹 ====================
export const getCollections = () => api.get('/favorites/collections')
export const createCollection = (name, description = '') =>
  api.post('/favorites/collections', { name, description })
export const deleteCollection = (collectionId) => api.delete(`/favorites/collections/${collectionId}`)
export const getPapersInCollection = (collectionId, limit = 100, order = 'added_at_desc') =>
  api.get(`/favorites/collections/${collectionId}/papers?limit=${limit}&order=${order}`)
export const addToCollection = (collectionId, paperId, notes = '') =>
  api.post(`/favorites/collections/${collectionId}/papers`, { paper_id: paperId, notes })
export const removeFromCollection = (collectionId, paperId) =>
  api.delete(`/favorites/collections/${collectionId}/papers/${paperId}`)
export const updateNotes = (collectionId, paperId, notes) =>
  api.put(`/favorites/collections/${collectionId}/papers/${paperId}/notes`, { notes })
export const searchInFavorites = (q, collectionId = 1) =>
  api.get(`/favorites/search?q=${encodeURIComponent(q)}&collection_id=${collectionId}`)

// ==================== 报告 ====================
export const generateReport = (reportType, format = 'markdown', paperId = null, collectionId = null, query = null) =>
  api.post('/reports/generate', {
    report_type: reportType,
    format,
    paper_id: paperId,
    collection_id: collectionId,
    query,
  })

// ==================== 推送 ====================
export const getPushSubscriptions = () => api.get('/push/subscriptions')
export const createPushSubscription = (name, method, config, strategy = 'trending') =>
  api.post('/push/subscriptions', { name, method, config, strategy })
export const deletePushSubscription = (subId) => api.delete(`/push/subscriptions/${subId}`)
export const getPushHistory = (limit = 20) => api.get(`/push/history?limit=${limit}`)
export const testPush = (subId) => api.post(`/push/test/${subId}`)

export default api
