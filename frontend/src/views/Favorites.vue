<template>
  <div v-loading="loading">
    <h2>📁 收藏夹</h2>

    <el-row :gutter="16">
      <el-col :xs="24" :md="8" :lg="6">
        <el-card shadow="hover">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span>收藏夹列表</span>
              <el-button size="small" type="primary" @click="openCreate">+ 新建</el-button>
            </div>
          </template>
          <div v-loading="colLoading">
            <el-empty v-if="!collections.length" description="还没有收藏夹" :image-size="60" />
            <div
              v-for="c in collections"
              :key="c.id"
              class="col-item"
              :class="{ active: selectedColId === c.id }"
              @click="onSelectCollection(c)"
            >
              <div class="col-name">
                <el-icon><Folder /></el-icon>
                <span>{{ c.name }}</span>
              </div>
              <div class="col-desc" v-if="c.description">{{ c.description }}</div>
              <el-button
                size="small"
                type="danger"
                text
                @click.stop="onDeleteCollection(c)"
              >删除</el-button>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :xs="24" :md="16" :lg="18">
        <el-card shadow="hover">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span>{{ currentCol ? `论文列表 - ${currentCol.name}` : '请选择收藏夹' }}</span>
              <span v-if="papers.length" style="color:#909399; font-size: 12px;">共 {{ papers.length }} 篇</span>
            </div>
          </template>
          <el-empty v-if="!selectedColId" description="请选择左侧收藏夹" />
          <el-empty v-else-if="!papers.length" description="该收藏夹中暂无论文" />

          <el-table v-else :data="papers" stripe>
            <el-table-column prop="title" label="标题" min-width="240" show-overflow-tooltip />
            <el-table-column prop="year" label="年份" width="80" align="center" />
            <el-table-column label="操作" width="200" align="center">
              <template #default="{ row }">
                <el-button size="small" @click="openNotesDialog(row)">编辑笔记</el-button>
                <el-button size="small" type="primary" @click="goDetail(row)">查看</el-button>
                <el-button size="small" type="danger" @click="onRemovePaper(row)">移除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <el-dialog v-model="createDialog" title="新建收藏夹" width="420px">
      <el-form :model="createForm" label-width="80px">
        <el-form-item label="名称" required>
          <el-input v-model="createForm.name" placeholder="收藏夹名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="createForm.description" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialog = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="onCreateCollection">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="notesDialog" title="编辑笔记" width="480px">
      <el-input v-model="notesContent" type="textarea" :rows="6" placeholder="为这篇论文添加笔记..." />
      <template #footer>
        <el-button @click="notesDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingNotes" @click="onSaveNotes">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getCollections, createCollection, deleteCollection,
  getPapersInCollection, removeFromCollection, updateNotes,
} from '../api'

const router = useRouter()
const loading = ref(false)
const colLoading = ref(false)
const collections = ref([])
const selectedColId = ref(null)
const currentCol = ref(null)
const papers = ref([])

const createDialog = ref(false)
const creating = ref(false)
const createForm = reactive({ name: '', description: '' })

const notesDialog = ref(false)
const savingNotes = ref(false)
const notesContent = ref('')
const editingPaperId = ref(null)

const loadCollections = async () => {
  colLoading.value = true
  try {
    const { data } = await getCollections()
    collections.value = Array.isArray(data) ? data : (data.collections || [])
    if (collections.value.length && !selectedColId.value) {
      onSelectCollection(collections.value[0])
    }
  } catch (e) {
    ElMessage.error('加载收藏夹失败')
  } finally {
    colLoading.value = false
  }
}

const onSelectCollection = async (c) => {
  selectedColId.value = c.id
  currentCol.value = c
  loading.value = true
  try {
    const { data } = await getPapersInCollection(c.id)
    papers.value = Array.isArray(data) ? data : (data.papers || [])
  } catch (e) {
    ElMessage.error('加载论文列表失败')
    papers.value = []
  } finally {
    loading.value = false
  }
}

const openCreate = () => {
  createForm.name = ''
  createForm.description = ''
  createDialog.value = true
}

const onCreateCollection = async () => {
  if (!createForm.name.trim()) {
    ElMessage.warning('请输入收藏夹名称')
    return
  }
  creating.value = true
  try {
    await createCollection(createForm.name, createForm.description)
    ElMessage.success('创建成功')
    createDialog.value = false
    loadCollections()
  } catch (e) {
    ElMessage.error('创建失败：' + (e.message || '未知错误'))
  } finally {
    creating.value = false
  }
}

const onDeleteCollection = (c) => {
  ElMessageBox.confirm(`确定删除收藏夹「${c.name}」？`, '提示', { type: 'warning' })
    .then(async () => {
      try {
        await deleteCollection(c.id)
        ElMessage.success('已删除')
        if (selectedColId.value === c.id) {
          selectedColId.value = null
          currentCol.value = null
          papers.value = []
        }
        loadCollections()
      } catch (e) {
        ElMessage.error('删除失败')
      }
    })
    .catch(() => {})
}

const onRemovePaper = (row) => {
  ElMessageBox.confirm(`确定从收藏夹移除「${row.title}」？`, '提示', { type: 'warning' })
    .then(async () => {
      try {
        await removeFromCollection(selectedColId.value, row.paper_id)
        ElMessage.success('已移除')
        if (currentCol.value) onSelectCollection(currentCol.value)
      } catch (e) {
        ElMessage.error('移除失败')
      }
    })
    .catch(() => {})
}

const openNotesDialog = (row) => {
  editingPaperId.value = row.paper_id
  notesContent.value = row.notes || ''
  notesDialog.value = true
}

const onSaveNotes = async () => {
  savingNotes.value = true
  try {
    await updateNotes(selectedColId.value, editingPaperId.value, notesContent.value)
    ElMessage.success('笔记已保存')
    notesDialog.value = false
    if (currentCol.value) onSelectCollection(currentCol.value)
  } catch (e) {
    ElMessage.error('保存失败')
  } finally {
    savingNotes.value = false
  }
}

const goDetail = (row) => {
  if (row.paper_id) router.push(`/paper/${row.paper_id}`)
}

onMounted(loadCollections)
</script>

<style scoped>
.col-item {
  padding: 10px;
  border-radius: 4px;
  cursor: pointer;
  margin-bottom: 6px;
  border: 1px solid #ebeef5;
  transition: all 0.2s;
}
.col-item:hover {
  background: #f5f7fa;
}
.col-item.active {
  background: #ecf5ff;
  border-color: #409eff;
}
.col-name {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
}
.col-desc {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
  margin-bottom: 4px;
}
</style>
