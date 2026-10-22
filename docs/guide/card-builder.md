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

<ClientOnly>
  <CardBuilderExport />
</ClientOnly>

## 使用说明

<details class="cb-doc">
<summary>第一次使用？点开看三步建卡、导入与复制规则</summary>

**三步建卡**：① 从上到下填表，等级在职业前，填完等级就能看到子职门槛；② 首次建卡复制「整卡命令」发到群里；③ 之后只改某一段时，点该字段标题旁的「复制本段」，单独发送即可。

**超过 4500 字**：整卡命令（含 `.角色卡记录`）不超过 4500 字时一次复制；超过时页面会自动按段拆成多个部分，每部分一个复制按钮。请先发第 1 部分（含等级与属性），再按顺序发后面的部分。

**导入已有的卡**：点「导入卡文本」，把 `.角色卡`、`.角色卡模板` 的整段回复，或一条 / 多条 `.角色卡记录` 命令粘进去。模板末尾的提示会自动忽略；解析失败会指出是哪一段。导入会覆盖当前表单。

**卡文本对照**：各段语法、上限与示例见[角色卡与属性](./character-card.md#段落一览)。先攻、被动察觉由骰娘按属性、等级、熟练与额外加值计算，下一级经验按等级计算，都不需要写进命令；旧写法仍可解析。

**复制与兼容**：两个文档站都走 HTTPS，复制按钮优先使用浏览器剪贴板接口，失败时退回旧式复制；仍失败会提示「复制失败」，可以手动从「查看命令文本」里选中复制。Firefox 对剪贴板限制较多，必要时请手动复制。

**立绘与卡图**：立绘裁切已并入本页「立绘」章节；裁好后复制图片，到群里与 `.立绘` 同条消息发送。角色卡图与立绘的完整口径见[角色卡图与立绘](./card-image.md)。
</details>
