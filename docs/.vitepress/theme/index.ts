import DefaultTheme from 'vitepress/theme'
import CardBuilderExport from './components/CardBuilderExport.vue'
import CardBuilderGroup from './components/CardBuilderGroup.vue'
import CardBuilderToolbar from './components/CardBuilderToolbar.vue'
import CardPreview from './components/CardPreview.vue'
import PortraitEditor from './components/PortraitEditor.vue'
import './style.css'

// 自定义主题：样式扩展（聊天气泡容器、网页建卡器）+ 注册建卡器组件。
// 建卡器按章节拆成多个组件，章节标题由 Markdown 提供，右侧目录才能跳转。
export default {
  extends: DefaultTheme,
  enhanceApp({ app }) {
    app.component('CardBuilderToolbar', CardBuilderToolbar)
    app.component('CardBuilderGroup', CardBuilderGroup)
    app.component('CardBuilderExport', CardBuilderExport)
    app.component('CardPreview', CardPreview)
    app.component('PortraitEditor', PortraitEditor)
  },
}
