<script lang="tsx" setup>
import { ref, onMounted } from 'vue'
import { useMessage } from 'naive-ui'
import * as GlobalAPI from '@/api'
import { useUserStore } from '@/store'
import { useRouter } from 'vue-router'

// 定义表单数据
const form = ref({
  username: 'admin',
  password: '123456',
})
const formRef = ref(null)
const message = useMessage()
const router = useRouter()
const userStore = useUserStore()

onMounted(() => {
  // 获取用户信息，如果已经登录，则直接跳转首页
  if (userStore.isLoggedIn) {
    router.push('/')
  }
})

// 登录处理函数
const handleLogin = () => {
  if (form.value.username && form.value.password) {
    GlobalAPI.login(form.value.username, form.value.password).then(
      async (res) => {
        if (res.body) {
          const responseData = await res.json() // 解析为JSON对象
          if (responseData.code === 200) {
            const user = {
              token: responseData.data.token,
            }
            // 存储用户信息到 store
            userStore.login(user)

            setTimeout(() => {
              router.push('/')
            }, 500) // 2000毫秒等于2秒
          } else {
            message.error('登录失败，请检查用户名或密码')
          }
        }
      },
    )
  } else {
    message.error('请填写完整信息')
  }
}
</script>

<template>
  <div class="login-container">
    <n-card class="login-card">
      <h2 class="login-title">用户登录</h2>
      <n-form ref="formRef" :model="form" label-placement="left">
        <n-form-item label="用户名">
          <n-input v-model:value="form.username" placeholder="请输入用户名" />
        </n-form-item>
        <n-form-item label="密码">
          <n-input v-model:value="form.password" type="password" placeholder="请输入密码" />
        </n-form-item>
        <n-form-item>
          <n-button type="primary" @click="handleLogin" class="login-button">
            登录
          </n-button>
        </n-form-item>
      </n-form>
    </n-card>
  </div>
</template>

<style lang="scss" scoped>
.login-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background-color: #f5f5f5;
}

.login-card {
  width: 400px;
  padding: 20px;
}

.login-title {
  text-align: center;
  margin-bottom: 20px;
}

.login-button {
  width: 100%;
}
</style>