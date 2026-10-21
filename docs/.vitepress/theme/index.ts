import DefaultTheme from 'vitepress/theme'
import CardBuilder from './components/CardBuilder.vue'
import './style.css'

// 自定义主题：样式扩展（聊天气泡容器、网页建卡器）+ 注册建卡器页面组件
export default {
  extends: DefaultTheme,
  enhanceApp({ app }) {
    app.component('CardBuilder', CardBuilder)
  },
}
