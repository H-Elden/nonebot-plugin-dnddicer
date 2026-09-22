import DefaultTheme from 'vitepress/theme'
import './style.css'

// 自定义主题：只做样式扩展（聊天气泡容器等），其余沿用 VitePress 默认主题
export default {
  extends: DefaultTheme,
}
