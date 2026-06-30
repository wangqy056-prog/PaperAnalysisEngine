<template>
  <div v-loading="loading">
    <el-page-header @back="$router.back()" style="margin-bottom: 16px">
      <template #content>论文详情</template>
    </el-page-header>

    <el-empty v-if="!loading && !paper" description="论文不存在或加载失败" />

    <template v-if="paper">
      <el-card shadow="hover" style="margin-bottom: 20px">
        <h2 style="margin-top: 0">{{ paper.title }}</h2>
        <div v-if="paper.authors?.length" style="color: #606266; margin-bottom: 12px;">
          <el-icon><User /></el-icon>
          {{ paper.authors.join(', ') }}
        </div>
        <el-descriptions :column="3" border>
          <el-descriptions-item label="论文 ID">
            <span style="font-family: monospace; color:#409eff;">{{ paper.id }}</span>
            <el-button size="small" text @click.stop="copyId">
              <el-icon><CopyDocument /></el-icon>
            </el-button>
          </el-descriptions-item>
          <el-descriptions-item label="期刊">{{ paper.journal || '-' }}</el-descriptions-item>
          <el-descriptions-item label="年份">{{ paper.year || '-' }}</el-descriptions-item>
          <el-descriptions-item label="引用数">{{ paper.citations ?? 0 }}</el-descriptions-item>
          <el-descriptions-item label="DOI">{{ paper.doi || '-' }}</el-descriptions-item>
          <el-descriptions-item label="类型">{{ paper.paper_type || '-' }}</el-descriptions-item>
          <el-descriptions-item label="评级">
            <el-tag v-if="paper.grade || paper.rating_level" :color="gradeColor(paper.grade || paper.rating_level)" effect="dark">{{ paper.grade || paper.rating_level }}</el-tag>
            <span v-else>-</span>
          </el-descriptions-item>
        </el-descriptions>

        <div v-if="paper.abstract" style="margin-top: 16px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <h4 style="margin: 0;">摘要</h4>
            <el-button size="small" type="warning" :loading="translating" @click="onTranslate">
              <el-icon><MagicStick /></el-icon> {{ translatedAbstract ? '重新翻译' : '翻译为中文' }}
            </el-button>
          </div>
          <p style="color: #303133; line-height: 1.7;">{{ paper.abstract }}</p>
          <el-card v-if="translating" shadow="never" style="margin-top: 12px; background: #f5f7fa;">
            <div v-loading="true" style="height: 60px;"></div>
          </el-card>
          <el-card v-else-if="translatedAbstract" shadow="never" style="margin-top: 12px; background: #f5f7fa; border-left: 3px solid #409eff;">
            <div style="font-weight: bold; margin-bottom: 6px; color: #409eff;">🌐 中文翻译</div>
            <p style="color: #303133; line-height: 1.7; margin: 0;">{{ translatedAbstract }}</p>
          </el-card>
        </div>

        <div v-if="paper.tags?.length" style="margin-top: 16px;">
          <h4>标签</h4>
          <el-tag v-for="tag in paper.tags" :key="tag" style="margin-right: 6px; margin-bottom: 6px;">{{ tag }}</el-tag>
        </div>

        <div style="margin-top: 16px;">
          <el-button type="primary" @click="showFavDialog = true">
            <el-icon><Star /></el-icon> 收藏到收藏夹
          </el-button>
          <el-button type="warning" @click="goAIAnalysis">
            <el-icon><MagicStick /></el-icon> AI 分析
          </el-button>
          <el-button type="success" :loading="downloadingScorecard" @click="downloadScorecard">
            <el-icon><Download /></el-icon> 生成评分卡 / 分享
          </el-button>
          <el-button v-if="paper.url" type="info" @click="openUrl(paper.url)">
            <el-icon><Link /></el-icon> 查看原文
          </el-button>
        </div>

        <!-- 评分卡预览弹窗 -->
        <el-dialog v-model="showScorecard" title="论文评分卡（可分享）" width="600px" align-center>
          <div style="text-align: center;">
            <img v-if="scorecardUrl" :src="scorecardUrl" alt="论文评分卡"
                 style="max-width: 100%; border: 1px solid #ebeef5; border-radius: 4px;" />
            <div v-loading="downloadingScorecard" v-else style="height: 400px;"></div>
          </div>
          <template #footer>
            <el-button @click="showScorecard = false">关闭</el-button>
            <a v-if="scorecardUrl" :href="scorecardUrl" :download="scorecardFilename">
              <el-button type="primary">
                <el-icon><Download /></el-icon> 下载 PNG
              </el-button>
            </a>
          </template>
        </el-dialog>
      </el-card>

      <el-row :gutter="20">
        <el-col :xs="24" :md="12">
          <el-card shadow="hover">
            <template #header>五维评级雷达图</template>
            <v-chart v-if="rating" :option="radarOption" style="height: 320px" autoresize />
            <el-empty v-else description="暂无评级数据" :image-size="80" />
          </el-card>
        </el-col>
        <el-col :xs="24" :md="12">
          <el-card shadow="hover">
            <template #header>商业化预测</template>
            <div v-if="paper.commercial_prediction">
              <el-progress
                :percentage="Math.round((paper.commercial_score ?? 0) * 100)"
                :color="paper.commercial_score >= 0.7 ? '#67c23a' : (paper.commercial_score >= 0.4 ? '#e6a23c' : '#f56c6c')"
              />
              <p style="margin-top: 12px; line-height: 1.7;">{{ paper.commercial_prediction }}</p>
            </div>
            <el-empty v-else description="暂无商业化预测" :image-size="80" />
          </el-card>
        </el-col>
      </el-row>
    </template>

    <el-dialog v-model="showFavDialog" title="选择收藏夹" width="480px">
      <div v-loading="favLoading">
        <el-radio-group v-model="selectedCollection" style="display: flex; flex-direction: column; gap: 10px;">
          <el-radio v-for="c in collections" :key="c.id" :label="c.id" style="margin: 0;">
            {{ c.name }} <span style="color:#909399; font-size: 12px;">({{ c.description }})</span>
          </el-radio>
        </el-radio-group>
        <el-empty v-if="!collections.length" description="还没有收藏夹" :image-size="60" />
      </div>
      <el-input v-model="favNotes" type="textarea" :rows="3" placeholder="收藏笔记（可选）" style="margin-top: 12px;" />
      <template #footer>
        <el-button @click="showFavDialog = false">取消</el-button>
        <el-button type="primary" :loading="adding" @click="onAddToCollection">确认收藏</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { RadarChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent, TitleComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import { getPaper, getCollections, addToCollection, aiTranslate } from '../api'

use([CanvasRenderer, RadarChart, TooltipComponent, LegendComponent, TitleComponent])

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const paper = ref(null)
const rating = ref(null)

const showFavDialog = ref(false)
const favLoading = ref(false)
const collections = ref([])
const selectedCollection = ref(null)
const favNotes = ref('')
const adding = ref(false)

// 中文翻译
const translating = ref(false)
const translatedAbstract = ref('')

// 评分卡
const showScorecard = ref(false)
const scorecardUrl = ref('')
const scorecardFilename = ref('')
const downloadingScorecard = ref(false)

const gradeColor = (grade) => {
  return { S: '#ff4444', A: '#ff8800', B: '#ffcc00', C: '#88cc00', D: '#88aaff', E: '#aaaaaa' }[grade] || '#aaa'
}

const loadPaper = async (id) => {
  loading.value = true
  try {
    const { data } = await getPaper(id)
    paper.value = data
    rating.value = data.rating || data.ratings?.[0] || null
    // 切换论文时清空之前的翻译
    translatedAbstract.value = ''
  } catch (e) {
    ElMessage.error('加载论文失败：' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

// 调用 AI 翻译英文摘要为中文
const onTranslate = async () => {
  if (!paper.value?.id) return
  translating.value = true
  translatedAbstract.value = ''
  try {
    const { data } = await aiTranslate(paper.value.id)
    translatedAbstract.value = data.result || data.content || data.translation || (typeof data === 'string' ? data : JSON.stringify(data))
  } catch (e) {
    ElMessage.error('翻译失败：' + (e.message || '未知错误'))
  } finally {
    translating.value = false
  }
}

const loadCollections = async () => {
  favLoading.value = true
  try {
    const { data } = await getCollections()
    collections.value = Array.isArray(data) ? data : (data.collections || [])
    if (collections.value.length && !selectedCollection.value) {
      selectedCollection.value = collections.value[0].id
    }
  } catch (e) {
    ElMessage.error('加载收藏夹失败')
  } finally {
    favLoading.value = false
  }
}

const onAddToCollection = async () => {
  if (!selectedCollection.value) {
    ElMessage.warning('请选择一个收藏夹')
    return
  }
  adding.value = true
  try {
    await addToCollection(selectedCollection.value, route.params.id, favNotes.value)
    ElMessage.success('已加入收藏夹')
    showFavDialog.value = false
    favNotes.value = ''
  } catch (e) {
    ElMessage.error('收藏失败：' + (e.message || '未知错误'))
  } finally {
    adding.value = false
  }
}

const openUrl = (url) => window.open(url, '_blank')

// 跳转到 AI 分析页面并自动填入当前论文 ID
const goAIAnalysis = () => {
  if (!paper.value?.id) return
  router.push({ path: '/ai-analysis', query: { id: paper.value.id } })
}

// 复制论文 ID 到剪贴板
const copyId = async () => {
  if (!paper.value?.id) return
  try {
    await navigator.clipboard.writeText(paper.value.id)
    ElMessage.success('已复制论文 ID')
  } catch {
    ElMessage.error('复制失败')
  }
}

// 生成并下载论文评分卡 PNG
const downloadScorecard = async () => {
  if (!paper.value?.id) return
  downloadingScorecard.value = true
  showScorecard.value = true
  scorecardUrl.value = ''
  try {
    const res = await fetch(`/api/papers/${paper.value.id}/scorecard`)
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || `HTTP ${res.status}`)
    }
    const blob = await res.blob()
    // 释放旧的 URL 避免内存泄漏
    if (scorecardUrl.value) URL.revokeObjectURL(scorecardUrl.value)
    scorecardUrl.value = URL.createObjectURL(blob)
    const grade = paper.value.grade || paper.value.rating_level || 'C'
    scorecardFilename.value = `PAE_${paper.value.id}_${grade}.png`
    ElMessage.success('评分卡生成成功，可下载分享')
  } catch (e) {
    ElMessage.error('评分卡生成失败：' + (e.message || '未知错误'))
    showScorecard.value = false
  } finally {
    downloadingScorecard.value = false
  }
}

watch(showFavDialog, (v) => {
  if (v && !collections.value.length) loadCollections()
})

const radarOption = computed(() => {
  if (!rating.value) return {}
  const dims = ['academic_impact', 'commercial_potential', 'innovation_index', 'reproducibility', 'combo_value']
  const labels = ['学术影响力', '商业潜力', '创新指数', '可复现性', '组合价值']
  const values = dims.map(d => rating.value[d] ?? 0)
  return {
    tooltip: {},
    radar: { indicator: labels.map(l => ({ name: l, max: 100 })), radius: 110 },
    series: [{
      type: 'radar',
      data: [{ value: values, name: '评级', areaStyle: { color: 'rgba(64,158,255,0.3)' } }],
    }],
  }
})

onMounted(() => loadPaper(route.params.id))
watch(() => route.params.id, (id) => { if (id) loadPaper(id) })
</script>
