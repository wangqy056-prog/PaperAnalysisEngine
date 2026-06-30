import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'dashboard', component: () => import('../views/Dashboard.vue'), meta: { title: '仪表盘', icon: 'Odometer' } },
  { path: '/search', name: 'search', component: () => import('../views/Search.vue'), meta: { title: '搜索论文', icon: 'Search' } },
  { path: '/paper/:id', name: 'paperDetail', component: () => import('../views/PaperDetail.vue'), meta: { title: '论文详情', hidden: true } },
  { path: '/leaderboard', name: 'leaderboard', component: () => import('../views/Leaderboard.vue'), meta: { title: '排行榜', icon: 'Trophy' } },
  { path: '/linkresearcher', name: 'linkresearcher', component: () => import('../views/Linkresearcher.vue'), meta: { title: '领研网', icon: 'Document' } },
  { path: '/batch-import', name: 'batchImport', component: () => import('../views/BatchImport.vue'), meta: { title: '批量导入', icon: 'Upload' } },
  { path: '/knowledge-graph', name: 'knowledgeGraph', component: () => import('../views/KnowledgeGraph.vue'), meta: { title: '知识图谱', icon: 'Share' } },
  { path: '/ai-analysis', name: 'aiAnalysis', component: () => import('../views/AIAnalysis.vue'), meta: { title: 'AI 分析', icon: 'MagicStick' } },
  { path: '/recommendations', name: 'recommendations', component: () => import('../views/Recommendations.vue'), meta: { title: '论文推荐', icon: 'Star' } },
  { path: '/favorites', name: 'favorites', component: () => import('../views/Favorites.vue'), meta: { title: '收藏夹', icon: 'Collection' } },
  { path: '/reports', name: 'reports', component: () => import('../views/Reports.vue'), meta: { title: '导出报告', icon: 'Printer' } },
  { path: '/push', name: 'push', component: () => import('../views/Push.vue'), meta: { title: '定时推送', icon: 'Bell' } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.afterEach((to) => {
  document.title = `${to.meta.title || '论文分析引擎'} - 论文分析引擎`
  // 切换路由时滚动到顶部
  window.scrollTo(0, 0)
})

export default router
