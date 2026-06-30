<template>
  <div v-loading="loading">
    <h2>⭐ 论文推荐</h2>

    <el-row :gutter="20">
      <el-col :xs="24" :md="8">
        <el-card shadow="hover" style="margin-bottom: 20px">
          <template #header>推荐设置</template>
          <el-form :model="form" label-width="90px">
            <el-form-item label="推荐策略">
              <el-select v-model="form.strategy" @change="loadRecommendations">
                <el-option label="混合推荐" value="hybrid" />
                <el-option label="内容推荐" value="content" />
                <el-option label="评分推荐" value="rating" />
                <el-option label="热门推荐" value="popular" />
                <el-option label="最新推荐" value="latest" />
              </el-select>
            </el-form-item>
            <el-form-item label="推荐数量">
              <el-slider v-model="form.limit" :min="5" :max="50" :step="5" show-input @change="loadRecommendations" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="loadRecommendations" :loading="loading">刷新推荐</el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card shadow="hover" v-if="userProfile">
          <template #header>用户画像</template>
          <el-descriptions :column="1" size="small" border>
            <el-descriptions-item label="浏览论文数">{{ userProfile.view_count || 0 }}</el-descriptions-item>
            <el-descriptions-item label="评分论文数">{{ userProfile.rating_count || 0 }}</el-descriptions-item>
          </el-descriptions>
          <div v-if="userProfile.preferred_fields?.length" style="margin-top: 12px;">
            <div style="margin-bottom: 6px; color:#606266;">偏好领域：</div>
            <el-tag v-for="f in userProfile.preferred_fields" :key="f" style="margin: 2px;">{{ f }}</el-tag>
          </div>
          <div v-if="userProfile.preferred_authors?.length" style="margin-top: 12px;">
            <div style="margin-bottom: 6px; color:#606266;">偏好作者：</div>
            <el-tag v-for="a in userProfile.preferred_authors" :key="a" type="success" style="margin: 2px;">{{ a }}</el-tag>
          </div>
        </el-card>
      </el-col>

      <el-col :xs="24" :md="16">
        <el-empty v-if="!loading && !recommendations.length" description="暂无推荐结果" />
        <div v-for="(rec, idx) in recommendations" :key="idx" style="margin-bottom: 12px;">
          <el-card shadow="hover" class="rec-card" @click="goDetail(rec)">
            <div class="rec-header">
              <span class="rec-title">{{ rec.title || rec.paper?.title }}</span>
              <el-tag v-if="rec.score !== undefined" type="warning" effect="dark">
                评分 {{ formatScore(rec.score) }}
              </el-tag>
            </div>
            <div class="rec-meta">
              <span v-if="authorsList(rec).length">
                {{ authorsList(rec).slice(0, 3).join(', ') }}
              </span>
              <el-tag size="small" v-if="rec.year || rec.paper?.year">{{ rec.year || rec.paper?.year }}</el-tag>
              <el-tag size="small" type="info" v-if="rec.journal || rec.paper?.journal">{{ rec.journal || rec.paper?.journal }}</el-tag>
            </div>
            <div class="rec-footer">
              <span class="rec-id">ID: {{ (rec.paper_id || rec.id || rec.paper?.paper_id || rec.paper?.id || '').substring(0, 20) }}</span>
              <el-button size="small" type="warning" link @click.stop="goAIAnalysis(rec)">AI 分析</el-button>
            </div>
            <div v-if="rec.reason" class="rec-reason">
              <el-icon><InfoFilled /></el-icon>
              <span>{{ rec.reason }}</span>
            </div>
          </el-card>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getRecommendations, getUserProfile } from '../api'

const router = useRouter()
const loading = ref(false)
const recommendations = ref([])
const userProfile = ref(null)

const form = reactive({
  strategy: 'hybrid',
  limit: 10,
})

const formatScore = (s) => (typeof s === 'number' ? s.toFixed(2) : s)

// 安全提取 authors 数组（防御字符串/undefined 等异常数据）
const authorsList = (rec) => {
  const a = rec.authors || rec.paper?.authors || []
  return Array.isArray(a) ? a : []
}

const goDetail = (rec) => {
  const id = rec.paper_id || rec.paper?.paper_id || rec.id || rec.paper?.id
  if (id) router.push(`/paper/${id}`)
}

const goAIAnalysis = (rec) => {
  const id = rec.paper_id || rec.paper?.paper_id || rec.id || rec.paper?.id
  if (id) router.push({ path: '/ai-analysis', query: { id } })
}

const loadRecommendations = async () => {
  loading.value = true
  try {
    const { data } = await getRecommendations(form.strategy, form.limit)
    recommendations.value = Array.isArray(data) ? data : (data.recommendations || [])
    if (!recommendations.value.length) ElMessage.info('暂无推荐结果')
  } catch (e) {
    ElMessage.error('加载推荐失败：' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

const loadProfile = async () => {
  try {
    const { data } = await getUserProfile()
    userProfile.value = data
  } catch (e) {
    // 静默忽略
  }
}

onMounted(() => {
  loadRecommendations()
  loadProfile()
})
</script>

<style scoped>
.rec-card {
  cursor: pointer;
  transition: transform 0.2s;
}
.rec-card:hover {
  transform: translateX(4px);
}
.rec-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}
.rec-title {
  font-weight: bold;
  font-size: 15px;
  line-height: 1.4;
  flex: 1;
}
.rec-meta {
  margin-top: 8px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
  color: #606266;
  font-size: 12px;
}
.rec-reason {
  margin-top: 10px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-left: 3px solid #409eff;
  border-radius: 3px;
  font-size: 13px;
  color: #606266;
  display: flex;
  align-items: flex-start;
  gap: 6px;
  line-height: 1.5;
}
.rec-footer {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px dashed #ebeef5;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.rec-id {
  font-family: monospace;
  font-size: 11px;
  color: #909399;
}
</style>
