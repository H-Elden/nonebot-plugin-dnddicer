# 网页建卡器

在浏览器里填写，内容不会上传；填完复制命令到群里。右侧目录可以直接跳到身份、属性、战斗、法术等章节，字段旁的「复制本段」用于建卡后只改某一段。

<ClientOnly>
  <CardBuilderToolbar />
</ClientOnly>

## 身份

<ClientOnly>
  <CardBuilderGroup group-id="identity" />
</ClientOnly>

## 属性与检定

<ClientOnly>
  <CardBuilderGroup group-id="core" />
</ClientOnly>

## 战斗

<ClientOnly>
  <CardBuilderGroup group-id="combat" />
</ClientOnly>

## 特性与专长

<ClientOnly>
  <CardBuilderGroup group-id="traits" />
</ClientOnly>

## 法术

<ClientOnly>
  <CardBuilderGroup group-id="spells" />
</ClientOnly>

## 装备

<ClientOnly>
  <CardBuilderGroup group-id="gear" />
</ClientOnly>

## 其他

<ClientOnly>
  <CardBuilderGroup group-id="other" />
</ClientOnly>

## 立绘

<ClientOnly>
  <PortraitEditor />
</ClientOnly>

## 角色卡预览

<ClientOnly>
  <CardPreview />
</ClientOnly>

## 导出命令

导出前先填「卡名」：它是卡库里的标识（≤20 字，不能含空格、`$`、`@`），与卡内的 `$姓名$` 分开；同一卡库内重名会被骰娘拒绝。群聊新建成功后会自动绑定本群，私聊建卡后需用 `.角色卡绑定 <卡名> <群号>` 绑定到跑团群。

<ClientOnly>
  <CardBuilderExport />
</ClientOnly>

## 使用说明

<details class="cb-doc">
<summary>第一次使用？点开看三步建卡、导入与复制规则</summary>

**三步建卡**：① 先填「卡名」，再从上到下填表（等级在职业前，填完等级就能看到子职门槛）；② 首次建卡复制「整卡命令」（`.角色卡新建 <卡名>`）发到群里；③ 之后只改某一段时，点该字段标题旁的「复制本段」（`.角色卡修改 <卡名> <段条目>`），单独发送即可。

**超过 4500 字**：整卡命令不超过 4500 字时一次复制（`.角色卡新建 <卡名> <完整卡>`）；超过时页面会自动按段拆成多个部分，第 1 部分用 `.角色卡新建 <卡名>`（含姓名、等级与属性），后续部分用 `.角色卡修改 <卡名>`。请按顺序发送。

**导入已有的卡**：点「导入卡文本」，把 `.角色卡导出` 的整段回复，或一条 / 多条 `.角色卡新建` / `.角色卡修改` 命令粘进去。解析失败会指出是哪一段。导入会覆盖当前表单。

**卡文本对照**：各段语法、上限与示例见[角色卡与属性](./character-card.md#段落一览)。先攻、被动察觉由骰娘按属性、等级、熟练、半熟练与额外加值计算，下一级经验按等级计算，都不需要写进命令；旧写法仍可解析。

**半熟练**：在「属性」与「熟练」之间按特性选择。5e 可点「万事通（全部 · 向下取整）」或「运动健将（力敏体 · 向上取整）」；5r 可点「万事通（技能 · 向下取整）」。选中后胶囊右边会显示该来源的半熟练加值；半熟练只在没有熟练或专精时生效。具体口径见[角色卡与属性 - 半熟练](./character-card.md#半熟练)。

**复制与兼容**：两个文档站都走 HTTPS，复制按钮优先使用浏览器剪贴板接口，失败时退回旧式复制；仍失败会提示「复制失败」，可以手动从「查看命令文本」里选中复制。Firefox 对剪贴板限制较多，必要时请手动复制。

**立绘与卡图**：立绘裁切已并入本页「立绘」章节；裁好后复制图片，到群里与 `.立绘` 同条消息发送。角色卡图与立绘的完整口径见[角色卡图与立绘](./card-image.md)。
</details>
