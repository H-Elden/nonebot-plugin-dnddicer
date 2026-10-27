/**
 * 网页建卡器的 Node 往返校验（`docs:build` 前自动运行）。
 *
 * 只做纯函数校验，不启动浏览器、不依赖 Vue：
 * 1. `card-spec.json` 与 `core.mjs` 的段清单/表单顺序/回写顺序互相对齐；
 * 2. 样例卡「解析 → 回写 → 再解析」稳定，规范样例逐字不变；
 * 3. 整卡命令、分段命令都能被导入逻辑读回；
 * 4. 编辑表单后回写的内容仍可被解析，关键值与派生值不丢；
 * 5. 整卡超过 4500 字时按段拆块，第 1 块含等级与属性、每块不超限；
 * 6. 角色卡预览视图的关键字段与 HTML 转义；
 * 7. 自由文本里的结构分隔符在导出前被点名拦截，合法标点不被误伤。
 *
 * 失败时逐条打印（带样例名与段名），并以退出码 1 结束构建。
 */

import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  CARD_COMMAND,
  CARD_MODIFY_COMMAND,
  K,
  SEGMENT_KINDS,
  createCardBuilder,
} from '../theme/card-builder/core.mjs'
import {
  buildPreviewView,
  renderPreviewHtml,
} from '../theme/card-builder/preview.mjs'

const TEST_CARD_NAME = 'TestCard'
const here = path.dirname(fileURLToPath(import.meta.url))
const builderDir = path.join(here, '..', 'theme', 'card-builder')

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'))
}

let passed = 0
let failed = 0
const failures = []

function check(name, condition, detail = '') {
  if (condition) {
    passed += 1
    return
  }
  failed += 1
  failures.push(`${name}${detail ? `：${detail}` : ''}`)
}

function checkEqual(name, actual, expected) {
  check(name, actual === expected, `期望 ${JSON.stringify(expected)}，实际 ${JSON.stringify(actual)}`)
}

function checkThrows(name, fn) {
  try {
    fn()
    check(name, false, '预期抛出错误但没有')
  } catch {
    passed += 1
  }
}

function main() {
  const spec = readJson(path.join(builderDir, 'card-spec.json'))
  const fixtureData = readJson(path.join(builderDir, 'fixtures.json'))
  const cardCss = fs.readFileSync(path.join(builderDir, 'char-card.css'), 'utf8')
  const builder = createCardBuilder(spec)

  // ── 1. 清单对齐 ──────────────────────────────────────────────────────
  const specKeys = spec.segments.map((segment) => segment.key)
  const kindKeys = Object.keys(SEGMENT_KINDS)
  checkEqual('段清单数量', specKeys.length, 26)
  checkEqual('表单形态数量', kindKeys.length, 26)
  for (const key of specKeys) {
    check(`段 ${key} 有表单形态`, Boolean(SEGMENT_KINDS[key]))
  }
  for (const key of kindKeys) {
    check(`表单形态 ${key} 在清单中`, specKeys.includes(key))
  }
  checkEqual('回写顺序覆盖段清单', [...new Set(spec.output_order)].sort().join('|'), [...specKeys].sort().join('|'))
  check('回写顺序无重复', new Set(spec.output_order).size === spec.output_order.length)
  checkEqual('表单顺序覆盖段清单', [...new Set(spec.form_order)].sort().join('|'), [...specKeys].sort().join('|'))
  check('表单顺序无重复', new Set(spec.form_order).size === spec.form_order.length)
  check(
    '等级在职业之前',
    spec.form_order.indexOf('$等级$') < spec.form_order.indexOf('$职业$'),
    JSON.stringify(spec.form_order.slice(0, 6)),
  )
  checkEqual('builder.formOrder 与 spec 一致', builder.formOrder.join('|'), spec.form_order.join('|'))
  check('分组 id 非空', spec.groups.every((group) => group.id && group.label))
  checkEqual('分组数量', spec.groups.length, 7)
  check(
    '段的 group 都在分组表内',
    spec.segments.every((segment) => spec.groups.some((group) => group.id === segment.group)),
  )
  check('旧段已从清单删除', !specKeys.some((key) => ['$特性$', '$能力$', '$属性值$', '$豁免$', '$技能$'].includes(key)))
  check('没有 legacy_segments 字段', !('legacy_segments' in spec))

  // ── 2. 示例卡 = 模板样例 ────────────────────────────────────────────
  const exampleCard = builder.buildExampleCard()
  const templateFixture = fixtureData.fixtures.find((item) => item.name === 'template')
  check('存在模板样例', Boolean(templateFixture))
  checkEqual('spec 示例拼出的卡 = 模板样例', exampleCard, templateFixture.text)

  // ── 3. 各样例往返 ───────────────────────────────────────────────────
  const fixtures = fixtureData.fixtures
  check('至少 2 个样例', fixtures.length >= 2)
  for (const fixture of fixtures) {
    const name = fixture.name
    const options = { rulesVersion: fixture.rulesVersion || '5r' }
    const parsed = builder.parseCardText(fixture.text)
    check(`${name}: 解析无错误`, parsed.errors.length === 0, JSON.stringify(parsed.errors))
    check(`${name}: 段数大于 0`, parsed.found > 0)
    checkEqual(`${name}: 导入识别规则版本`, parsed.rulesVersion, options.rulesVersion)
    const serialized = builder.serializeCard(parsed.state, options)
    check(`${name}: 回写结果非空`, serialized.length > 0)
    const reparsed = builder.parseCardText(serialized)
    check(`${name}: 回写可再次解析`, reparsed.errors.length === 0, JSON.stringify(reparsed.errors))
    const reserialized = builder.serializeCard(reparsed.state, options)
    checkEqual(`${name}: 回写幂等`, reserialized, serialized)
    if (fixture.canonical) {
      checkEqual(`${name}: 规范样例逐字往返`, serialized, fixture.text)
    }
    // 输入里的每个段都应出现在回写结果里（避免某个段被解析后悄悄丢掉）
    for (const key of spec.output_order) {
      if (fixture.text.includes(`${key} `)) {
        check(`${name}: 回写包含 ${key}`, serialized.includes(`${key} `))
      }
    }
    // 每个非空段都能生成一条可单独导入的分段命令
    const commands = builder.buildSegmentCommands(parsed.state, options, TEST_CARD_NAME)
    check(`${name}: 分段命令非空`, commands.length > 0)
    for (const item of commands) {
      check(
        `${name}: 命令格式 ${item.key}`,
        item.command.startsWith(`${CARD_MODIFY_COMMAND} ${TEST_CARD_NAME} ${item.key} `),
      )
      const single = builder.parseCardText(item.command)
      check(`${name}: 单段命令可导入 ${item.key}`, single.errors.length === 0)
      check(`${name}: 单段命令只含一段 ${item.key}`, single.found === 1)
      checkEqual(
        `${name}: 单段命令内容不变 ${item.key}`,
        builder.contentFor(single.state, item.key, options),
        item.content,
      )
      check(
        `${name}: 单段命令长度 ${item.key}`,
        item.length === item.command.length,
      )
    }
    // 整卡命令可导入
    const whole = `${CARD_COMMAND} ${TEST_CARD_NAME}\n${serialized}`
    const wholeParsed = builder.parseCardText(whole)
    check(`${name}: 整卡命令可导入`, wholeParsed.errors.length === 0)
    checkEqual(`${name}: 整卡命令内容不变`, builder.serializeCard(wholeParsed.state, options), serialized)
    const wholeCommand = builder.buildWholeCommand(parsed.state, options, TEST_CARD_NAME)
    checkEqual(`${name}: 整卡命令文本`, wholeCommand.text, whole)
    checkEqual(`${name}: 整卡命令长度按整条消息`, wholeCommand.length, whole.length)
  }

  // 旧段不再兼容：导入直接报未知段
  const legacyDerived = builder.parseCardText(
    '$姓名$ 旧卡\n$等级$ 1\n$属性$ 10/10/10/10/10/10\n' +
      '$技能$ 运动:+5\n$豁免$ 力量:+2\n' +
      '$属性值$ 力量:10/+0; 敏捷:10/+0; 体质:10/+0; 智力:10/+0; 感知:10/+0; 魅力:10/+0',
  )
  check('旧派生段导入报错', legacyDerived.errors.length >= 3, JSON.stringify(legacyDerived.errors))
  check(
    '旧派生段提示未知段',
    legacyDerived.errors.every((item) => item.message.includes('未知段')),
    JSON.stringify(legacyDerived.errors),
  )
  checkThrows('单段旧特性被拒绝', () => builder.parseSegment('$特性$', '黑暗视觉'))
  checkThrows('单段旧能力被拒绝', () => builder.parseSegment('$能力$', '奥术回想:1/1短休'))

  // ── 4. 表单编辑后回写 ───────────────────────────────────────────────
  const state = builder.createState()
  checkEqual('空状态回写为空', builder.serializeCard(state), '')
  const emptyValidation = builder.validateState(state)
  check('空状态报必填错误', emptyValidation.errors.length >= 2)
  check(
    '空状态只有等级与属性两个错误',
    emptyValidation.errors.length === 2,
    JSON.stringify(emptyValidation.errors),
  )
  check(
    '空状态错误含等级与属性',
    emptyValidation.errors.some((item) => item.key === '$等级$') &&
      emptyValidation.errors.some((item) => item.key === '$属性$'),
  )
  checkEqual('空状态激励默认无', state['$进度$'].inspiration, '无')

  state[K.NAME] = '测试角色'
  state[K.RACE] = '人类'
  state[K.CLASS] = '战士'
  state[K.SUBCLASS] = '战斗大师'
  state[K.LEVEL] = '5'
  state[K.ABILITY] = ['16', '12', '14', '10', '11', '13']
  state[K.BACKGROUND]['背景'] = '士兵'
  state[K.BACKGROUND]['阵营'] = '守序善良'
  state[K.BACKGROUND]['理想'] = '5e 专属背景项'
  state[K.HP] = { cur: '44', max: '44', temp: '' }
  state[K.HP_DICE] = { num: '5', max: '5', type: '10' }
  state[K.COMBAT] = { AC: '18', 速度: '30' }
  state[K.PROGRESS] = { xp: '6500', xpNext: '99999', inspiration: '有' }
  state[K.FEATS] = [{ name: '巨武器大师', text: '可以用附赠动作再攻击一次' }]
  state[K.RACE_TRAITS] = [{ name: '黑暗视觉', text: '60 尺内微光视为明亮' }]
  state[K.CLASS_TRAITS] = [
    { level: '3', name: '战斗大师', text: '获得战技' },
    { level: '1', name: '战斗风格', text: '选择一种战斗风格' },
  ]
  state[K.WEAPON] = [
    { name: '长剑', noAttack: false, attack: '+6', damage: '1d8+3', type: '挥砍', note: '双手' },
    { name: '火焰箭', noAttack: true, attack: '', damage: '2d10', type: '火焰', note: '120尺' },
  ]
  state[K.ITEMS] = [{ name: '治疗药水', qty: '2' }]
  state[K.COINS] = { CP: '0', SP: '8', EP: '0', GP: '18', PP: '0' }
  state[K.PROF].checks['力量豁免'] = 1
  state[K.PROF].checks['运动'] = 2
  state[K.PROF].checks['先攻'] = 1
  state[K.PROF].groups['护甲'] = '轻甲·中甲·盾牌'
  state[K.PROF].groups['武器'] = '简易武器·军用武器'
  state[K.PROF].groups['工具'] = '书法工具'
  state[K.PROF].groups['语言'] = '通用语·精灵语'
  state[K.EXT] = [
    { key: '先攻', adv: '', bonus: '+2' },
    { key: '运动', adv: '优势', bonus: '+2' },
  ]
  state[K.FEATURE] = [
    {
      name: '动作如潮',
      cur: '1',
      max: '1',
      modes: {
        短休: { on: true, amount: '1' },
        长休: { on: true, amount: '' },
        两者: { on: false, amount: '' },
        手动: { on: false, amount: '' },
      },
      text: '短休回复一次',
    },
  ]
  state[K.MAGIC_ITEMS] = [
    {
      name: '防护斗篷',
      tag: '奇物，非普通（需同调）',
      text: 'AC 和豁免 +1。\n\n这件斗篷由银线织成。',
    },
  ]
  state[K.SPELL] = {
    ability: '智力',
    dc: '',
    attack: '',
    dcManual: false,
    attackManual: false,
    list: [],
  }
  state[K.SPELL_SLOTS].levels[0] = { cur: '2', max: '2' }
  state[K.COMBAT_NOTES] = ['祝福术(专注,3轮)']

  const editedValidation = builder.validateState(state)
  check('编辑后的表单无错误', editedValidation.errors.length === 0, JSON.stringify(editedValidation.errors))
  const editedText = builder.serializeCard(state)
  const editedParsed = builder.parseCardText(editedText)
  check('编辑后的卡可再次解析', editedParsed.errors.length === 0)
  checkEqual('编辑后的卡姓名保留', editedParsed.state[K.NAME], '测试角色')
  checkEqual('编辑后的卡等级保留', editedParsed.state[K.LEVEL], '5')
  checkEqual('编辑后的卡职业保留', editedParsed.state[K.CLASS], '战士')
  checkEqual('编辑后的卡武器数', editedParsed.state[K.WEAPON].length, 2)
  checkEqual('编辑后的卡专长说明', editedParsed.state[K.FEATS][0].text, '可以用附赠动作再攻击一次')
  checkEqual('编辑后的卡熟练组', editedParsed.state[K.PROF].groups['护甲'], '轻甲·中甲·盾牌')
  checkEqual('编辑后的卡限定资源', builder.contentFor(editedParsed.state, K.FEATURE), '动作如潮:1/1短休+1,长休|短休回复一次')
  const editedPreview = buildPreviewView(builder, editedParsed.state)
  checkEqual('编辑后的卡预览限定资源', editedPreview.resources[0].uses, '1/1 短休+1，长休回满')
  checkEqual('编辑后的卡战斗记录', editedParsed.state[K.COMBAT_NOTES][0], '祝福术(专注,3轮)')
  checkEqual('编辑后的卡技能专精', editedParsed.state[K.PROF].checks['运动'], 2)

  // 背景：固定键、5r 过滤 5e 专属项、未知键报错
  const fiveRText = builder.serializeCard(state, { rulesVersion: '5r' })
  const fiveEText = builder.serializeCard(state, { rulesVersion: '5e' })
  check('5r 不输出理想', !fiveRText.includes('理想:'), fiveRText)
  check('5e 输出理想', fiveEText.includes('理想:5e 专属背景项'))
  checkThrows('未知背景键被拒绝', () => builder.parseSegment(K.BACKGROUND, '故乡:无冬城'))

  // 先攻/被动察觉只读派生：先攻 = 敏捷 +1 + 熟练 +3 + 额外 +2 = +6；
  // 被动察觉 = 10 + 察觉加值（本例未熟练、感知 11，调整值 0）= 10。
  checkEqual('先攻派生值', builder.deriveInitiative(state), '+6')
  checkEqual('被动察觉派生值', builder.derivePassivePerception(state), '10')
  state[K.EXT].push({ key: '察觉', adv: '优势', bonus: '' })
  checkEqual('被动察觉优势 +5', builder.derivePassivePerception(state), '15')
  state[K.EXT].pop()
  check(
    '卡文本的战斗段不含先攻/被动察觉',
    !builder.contentFor(state, K.COMBAT).includes('先攻') &&
      !builder.contentFor(state, K.COMBAT).includes('被动察觉'),
    builder.contentFor(state, K.COMBAT),
  )
  checkEqual('熟练加值', builder.deriveProficiencyBonus(state), 3)
  checkEqual('下一级经验自动', builder.deriveXpNext(state), '14000')
  check('卡文本只写当前经验', editedText.includes('经验:6500') && !editedText.includes('经验:6500/'))
  check('卡文本不写下一级经验', !editedText.includes('99999') && !editedText.includes('14000'))

  // 职业特性按等级升序
  checkEqual(
    '职业特性按等级排序',
    builder.contentFor(state, K.CLASS_TRAITS),
    '1|战斗风格:选择一种战斗风格; 3|战斗大师:获得战技',
  )

  // 魔法物品说明转 // 分段
  checkEqual(
    '魔法物品说明分段',
    builder.contentFor(state, K.MAGIC_ITEMS),
    '防护斗篷|奇物，非普通（需同调）|AC 和豁免 +1。//这件斗篷由银线织成。',
  )

  // 装备不再有 [装备]
  check('物品无装备标记', !editedText.includes('[装备]'))
  checkThrows('物品 [装备] 被拒绝', () => builder.parseSegment(K.ITEMS, '长剑[装备]'))

  // 法术公式与手动覆盖：智力 10（+0）、5 级（熟练 +3）→ DC 11 / 攻击 +3
  checkEqual('法术 DC 公式', builder.deriveSpellStats(state).dc, '11')
  checkEqual('法术攻击公式', builder.deriveSpellStats(state).attack, '+3')
  check('卡文本自动写法术 DC', editedText.includes('豁免DC:11'))
  check('卡文本自动写法术攻击', editedText.includes('法术攻击:+3'))
  state[K.SPELL].attackManual = true
  state[K.SPELL].attack = '+8'
  checkEqual(
    '手动法术攻击保留',
    builder.contentFor(state, K.SPELL),
    '施法属性:智力; 豁免DC:11; 法术攻击:+8',
  )

  // 子职门槛：5r 3 级；5e 法师 2 级、牧师 1 级；自定义职业默认 3 级
  const gate = builder.createState()
  gate[K.LEVEL] = '2'
  gate[K.CLASS] = '法师'
  gate[K.SUBCLASS] = '塑能师'
  check('5r 2 级法师不输出子职', builder.contentFor(gate, K.SUBCLASS, { rulesVersion: '5r' }) === '')
  gate[K.LEVEL] = '3'
  check('5r 3 级法师输出子职', builder.contentFor(gate, K.SUBCLASS, { rulesVersion: '5r' }) === '塑能师')
  gate[K.LEVEL] = '1'
  check('5e 1 级法师不输出子职', builder.contentFor(gate, K.SUBCLASS, { rulesVersion: '5e' }) === '')
  gate[K.LEVEL] = '2'
  check('5e 2 级法师输出子职', builder.contentFor(gate, K.SUBCLASS, { rulesVersion: '5e' }) === '塑能师')
  gate[K.LEVEL] = '1'
  gate[K.CLASS] = '牧师'
  check('5e 1 级牧师输出子职', builder.contentFor(gate, K.SUBCLASS, { rulesVersion: '5e' }) === '塑能师')
  gate[K.CLASS] = '机关术师'
  gate[K.LEVEL] = '2'
  check('自定义职业 2 级不输出子职', builder.contentFor(gate, K.SUBCLASS, { rulesVersion: '5e' }) === '')
  checkEqual('自定义职业可解析', builder.parseSegment(K.CLASS, '机关术师'), '机关术师')

  // 派生值预览：等级 5（熟练 +3）、力量 16（+3），运动专精 → +3 + 3×2 + 2 = +11
  const derived = builder.deriveCheckValues(state)
  checkEqual('派生值：运动专精计入额外加值', derived['运动'], '+11')
  checkEqual('派生值：力量豁免', derived['力量豁免'], '+6')
  const modifiers = builder.deriveAbilityModifiers(state)
  checkEqual('派生值：力量调整', modifiers[0], '+3')
  checkEqual('派生值：智力调整', modifiers[3], '+0')

  // 故事多行保留，上限按换行不计
  const storyState = builder.createState()
  storyState[K.STORY] = '第一行\n第二行'
  checkEqual('故事换行保留', builder.contentFor(storyState, K.STORY), '第一行\n第二行')
  const storyRoundtrip = builder.parseCardText('$故事$ 第一行\n第二行')
  checkEqual('故事多行可导入', storyRoundtrip.state[K.STORY], '第一行\n第二行')
  checkThrows('故事超过 1000 字报错', () => builder.parseSegment(K.STORY, '长'.repeat(1001)))
  const storyWithNewlines = builder.createState()
  storyWithNewlines[K.STORY] = `${'长'.repeat(500)}\n${'长'.repeat(500)}`
  checkEqual(
    '故事字数不计换行',
    builder.contentFor(storyWithNewlines, K.STORY).replace(/\n/g, '').length,
    1000,
  )

  // 武器命中加值允许骰子表达式（与插件一致）
  const diceState = builder.createState()
  diceState[K.LEVEL] = '5'
  diceState[K.ABILITY] = ['10', '10', '10', '10', '10', '10']
  diceState[K.WEAPON] = [
    { name: '短剑', noAttack: false, attack: '+1d4', damage: '1d6+2', type: '穿刺', note: '' },
  ]
  check('武器命中骰子加值可导出', builder.validateState(diceState).errors.length === 0, JSON.stringify(builder.validateState(diceState).errors))
  checkEqual('武器命中骰子加值保留', builder.contentFor(diceState, K.WEAPON), '短剑+1d4|1d6+2穿刺')

  // 空的展示分组要报「不能为空」而不是「无效条目」
  const emptyGroup = builder.parseCardText(
    `${CARD_COMMAND} $等级$ 5\n${CARD_COMMAND} $属性$ 10/10/10/10/10/10\n${CARD_COMMAND} $熟练$ 武器:`,
  )
  check(
    '空熟练分组报错',
    emptyGroup.errors.some((item) => item.message.includes('不能为空')),
    JSON.stringify(emptyGroup.errors),
  )

  // 非法内容要报错而不是产出废命令
  const badState = builder.createState()
  badState[K.LEVEL] = '5'
  badState[K.ABILITY] = ['10', '10', '10', '10', '10', '10']
  badState[K.NAME] = '带$符号'
  const badValidation = builder.validateState(badState)
  check('姓名含 $ 被拦截', badValidation.errors.some((item) => item.key === K.NAME))
  badState[K.NAME] = '正常'
  badState[K.WEAPON] = [
    { name: '长剑', noAttack: false, attack: '+5', damage: '1d8+3', type: '火焰剑', note: '' },
  ]
  const weaponValidation = builder.validateState(badState)
  check('武器伤害类型写错被拦截', weaponValidation.errors.some((item) => item.key === K.WEAPON))
  badState[K.WEAPON] = [{ name: '长剑', noAttack: false, attack: '+5', damage: '1d8+3', type: '', note: '' }]
  badState[K.LEVEL] = 'abc'
  check('等级非数字被拦截', builder.validateState(badState).errors.some((item) => item.key === K.LEVEL))

  // 自由文本里的结构分隔符：导出前点名字段与符号，而不是让骰娘侧报「条目不完整」。
  const baseState = () => {
    const next = builder.createState()
    next[K.LEVEL] = '5'
    next[K.ABILITY] = ['10', '10', '10', '10', '10', '10']
    return next
  }
  const errorOf = (nextState, key) =>
    builder.validateState(nextState).errors.find((item) => item.key === key)

  const backgroundState = baseState()
  backgroundState[K.BACKGROUND]['外貌'] = '银发绿眼；嘴角有疤'
  check(
    '背景里的全角分号允许（不是分隔符）',
    !errorOf(backgroundState, K.BACKGROUND),
    JSON.stringify(backgroundState[K.BACKGROUND]),
  )
  backgroundState[K.BACKGROUND]['外貌'] = '银发绿眼; 嘴角有疤'
  const backgroundError = errorOf(backgroundState, K.BACKGROUND)
  check('背景半角分号被拦截', Boolean(backgroundError), JSON.stringify(backgroundState[K.BACKGROUND]))
  check(
    '背景分号错误点名字段',
    backgroundError?.message.includes('背景「外貌」'),
    backgroundError?.message,
  )
  check(
    '背景分号错误点名符号',
    backgroundError?.message.includes('「;」'),
    backgroundError?.message,
  )
  check(
    '背景分号错误给出替代写法',
    backgroundError?.message.includes('逗号或句号'),
    backgroundError?.message,
  )
  backgroundState[K.BACKGROUND]['外貌'] = ''
  check('背景清空后不再报错', !errorOf(backgroundState, K.BACKGROUND))
  backgroundState[K.BACKGROUND]['外貌'] = '银发绿眼，深蓝法袍'
  check('背景里的逗号允许', !errorOf(backgroundState, K.BACKGROUND))
  backgroundState[K.BACKGROUND]['外貌'] = '银发绿眼|嘴角有疤'
  check(
    '背景竖线被拦截',
    errorOf(backgroundState, K.BACKGROUND)?.message.includes('「|」'),
    errorOf(backgroundState, K.BACKGROUND)?.message,
  )
  backgroundState[K.BACKGROUND]['外貌'] = ''

  const importBackground = builder.parseCardText(
    '$背景$ 外貌:银发绿眼；嘴角有疤; 个性:喜欢追问原理',
  )
  check('导入背景保留全角分号', importBackground.errors.length === 0, JSON.stringify(importBackground.errors))
  checkEqual(
    '导入背景分号留在值里',
    importBackground.state[K.BACKGROUND]['外貌'],
    '银发绿眼；嘴角有疤',
  )

  const semicolonStoryState = baseState()
  semicolonStoryState[K.STORY] = '第一段；第二段'
  check('故事里的分号允许', !errorOf(semicolonStoryState, K.STORY))

  const featState = baseState()
  featState[K.FEATS] = [{ name: '战法师', text: '专注; 豁免优势' }]
  const featTextError = errorOf(featState, K.FEATS)
  check(
    '专长说明分号被拦截',
    featTextError?.message.includes('专长「战法师」的说明') &&
      featTextError.message.includes('「;」'),
    featTextError?.message,
  )
  featState[K.FEATS] = [{ name: '战法师：学徒', text: '' }]
  check('专长名称全角冒号允许', !errorOf(featState, K.FEATS))
  featState[K.FEATS] = [{ name: '战法师:学徒', text: '' }]
  const featNameError = errorOf(featState, K.FEATS)
  check(
    '专长名称半角冒号被拦截',
    featNameError?.message.includes('专长名称') && featNameError.message.includes('「:」'),
    featNameError?.message,
  )
  featState[K.FEATS] = [{ name: '战法师', text: '专注/豁免优势' }]
  check('专长说明里的斜杠允许', !errorOf(featState, K.FEATS))

  const raceTraitState = baseState()
  raceTraitState[K.RACE_TRAITS] = [{ name: '黑暗视觉', text: '60尺; 120尺' }]
  const raceTraitError = errorOf(raceTraitState, K.RACE_TRAITS)
  check(
    '种族特性说明分号被拦截',
    raceTraitError?.message.includes('种族特性「黑暗视觉」的说明'),
    raceTraitError?.message,
  )

  const classTraitState = baseState()
  classTraitState[K.CLASS_TRAITS] = [
    { level: '3', name: '塑能学者', text: '火球; 闪电' },
  ]
  const classTraitError = errorOf(classTraitState, K.CLASS_TRAITS)
  check(
    '职业特性说明分号被拦截',
    classTraitError?.message.includes('职业特性「塑能学者」的说明'),
    classTraitError?.message,
  )

  const featureState = baseState()
  featureState[K.FEATURE] = [
    {
      name: '奥术回想',
      cur: '1',
      max: '1',
      modes: {
        短休: { on: true, amount: '' },
        长休: { on: false, amount: '' },
        两者: { on: false, amount: '' },
        手动: { on: false, amount: '' },
      },
      text: '回复法术位; 每次短休',
    },
  ]
  const featureError = errorOf(featureState, K.FEATURE)
  check(
    '限定资源说明分号被拦截',
    featureError?.message.includes('限定资源「奥术回想」的说明') &&
      featureError.message.includes('「;」'),
    featureError?.message,
  )

  const magicItemState = baseState()
  magicItemState[K.MAGIC_ITEMS] = [
    { name: '防护斗篷', tag: '奇物', text: 'AC+1; 豁免+1' },
  ]
  const magicItemError = errorOf(magicItemState, K.MAGIC_ITEMS)
  check(
    '魔法物品说明分号被拦截',
    magicItemError?.message.includes('魔法物品「防护斗篷」的说明'),
    magicItemError?.message,
  )
  magicItemState[K.MAGIC_ITEMS] = [
    { name: '防护斗篷', tag: '奇物', text: 'AC+1|豁免+1' },
  ]
  const magicItemPipeError = errorOf(magicItemState, K.MAGIC_ITEMS)
  check(
    '魔法物品说明竖线被拦截',
    magicItemPipeError?.message.includes('「|」'),
    magicItemPipeError?.message,
  )

  const itemState = baseState()
  itemState[K.ITEMS] = [{ name: '治疗药水; 大瓶', qty: '1' }]
  const itemError = errorOf(itemState, K.ITEMS)
  check(
    '物品名称分号被拦截',
    itemError?.message.includes('物品名称') && itemError.message.includes('「;」'),
    itemError?.message,
  )

  const noteState = baseState()
  noteState[K.COMBAT_NOTES] = ['祝福术; 中毒']
  const noteError = errorOf(noteState, K.COMBAT_NOTES)
  check(
    '战斗记录分号被拦截',
    noteError?.message.includes('战斗记录') && noteError.message.includes('「;」'),
    noteError?.message,
  )

  const speedState = baseState()
  speedState[K.COMBAT]['速度'] = '30; 飞行60'
  const speedError = errorOf(speedState, K.COMBAT)
  check(
    '速度分号被拦截',
    speedError?.message.includes('速度') && speedError.message.includes('「;」'),
    speedError?.message,
  )

  const weaponNoteState = baseState()
  weaponNoteState[K.WEAPON] = [
    {
      name: '长剑',
      noAttack: false,
      attack: '+5',
      damage: '1d8+3',
      type: '挥砍',
      note: '双手, √灵巧 / 重型',
    },
  ]
  check('武器备注里的逗号与斜杠允许', !errorOf(weaponNoteState, K.WEAPON))
  weaponNoteState[K.WEAPON][0].note = '双手|灵巧'
  const weaponNoteError = errorOf(weaponNoteState, K.WEAPON)
  check(
    '武器备注竖线被拦截',
    weaponNoteError?.message.includes('武器「长剑」的备注') &&
      weaponNoteError.message.includes('「|」'),
    weaponNoteError?.message,
  )

  const spellState = baseState()
  spellState[K.SPELL] = {
    ability: '智力',
    dc: '15',
    attack: '+7',
    dcManual: true,
    attackManual: true,
    list: [
      {
        name: '火球术',
        level: '3',
        prepared: false,
        time: '1动作, 或1反应',
        range: '150尺',
        concentration: false,
        ritual: false,
        material: false,
        note: '',
      },
    ],
  }
  check('法术施法时间里的逗号允许', !errorOf(spellState, K.SPELL))
  spellState[K.SPELL].list[0].time = '1动作|或1反应'
  const spellTimeError = errorOf(spellState, K.SPELL)
  check(
    '法术施法时间竖线被拦截',
    spellTimeError?.message.includes('法术「火球术」的施法时间'),
    spellTimeError?.message,
  )
  spellState[K.SPELL].list[0].time = '1动作'
  spellState[K.SPELL].list[0].note = '8d6; 敏捷'
  const spellNoteError = errorOf(spellState, K.SPELL)
  check(
    '法术备注分号被拦截',
    spellNoteError?.message.includes('法术「火球术」的备注'),
    spellNoteError?.message,
  )

  const profState = baseState()
  profState[K.PROF].groups['工具'] = '书法工具|盗贼工具'
  const profError = errorOf(profState, K.PROF)
  check(
    '熟练分组条目的竖线被拦截',
    profError?.message.includes('熟练分组「工具」的条目'),
    profError?.message,
  )

  // 单段命令（首次建卡前后追加）能只导入这一段
  const single = builder.parseCardText(`${CARD_MODIFY_COMMAND} ${TEST_CARD_NAME} $战斗$ AC:15; 先攻:+2; 速度:30; 被动察觉:13`)
  check('单段命令解析成功', single.errors.length === 0)
  checkEqual('单段命令只识别一段', single.found, 1)
  checkEqual('单段命令战斗段 AC', single.state[K.COMBAT].AC, '15')
  check(
    '旧先攻/被动察觉写法可解析但不再导出',
    !builder.contentFor(single.state, K.COMBAT).includes('先攻') &&
      !builder.contentFor(single.state, K.COMBAT).includes('被动察觉'),
  )

  // 多条分段命令粘在一起也能导入（每条各占一行）
  const multi = builder.parseCardText(
    [
      `${CARD_MODIFY_COMMAND} ${TEST_CARD_NAME} $姓名$ 多段导入`,
      `${CARD_MODIFY_COMMAND} ${TEST_CARD_NAME} $等级$ 3`,
      `${CARD_MODIFY_COMMAND} ${TEST_CARD_NAME} $属性$ 10/11/12/13/14/15`,
    ].join('\n'),
  )
  check('多条分段命令解析成功', multi.errors.length === 0, JSON.stringify(multi.errors))
  checkEqual('多条分段命令段数', multi.found, 3)
  checkEqual('多条分段命令姓名', multi.state[K.NAME], '多段导入')
  checkEqual('多条分段命令等级', multi.state[K.LEVEL], '3')

  // ── 4500 字整卡拆分 ──────────────────────────────────────────────────
  const templateState = builder.parseCardText(templateFixture.text).state
  const whole = builder.buildWholeCommand(templateState, {}, TEST_CARD_NAME)
  checkEqual('整卡命令长度按整条消息', whole.length, whole.text.length)
  check(
    '恰好等于上限仍是一块',
    builder.buildCardParts(templateState, {}, whole.length, TEST_CARD_NAME).parts.length === 1,
  )
  const split = builder.buildCardParts(templateState, {}, 900, TEST_CARD_NAME)
  check('小上限会拆成多块', split.parts.length > 1, String(split.parts.length))
  check(
    '每块都不超过上限',
    split.parts.every((part) => part.length <= 900),
    JSON.stringify(split.parts.map((part) => part.length)),
  )
  check('第 1 块含等级', split.parts[0].text.includes('$等级$ 5'))
  check('第 1 块含属性', split.parts[0].text.includes('$属性$'))
  check(
    '后续块不含等级/属性',
    split.parts.slice(1).every((part) => !part.text.includes('$等级$') && !part.text.includes('$属性$')),
  )
  const allBlocks = builder.buildCardBlocks(templateState).map((item) => item.key)
  const partKeys = split.parts.flatMap((part) =>
    [...part.text.matchAll(/\$([^$\n]+)\$/g)].map((match) => `$${match[1]}$`),
  )
  checkEqual('拆分不丢段', [...partKeys].sort().join('|'), [...allBlocks].sort().join('|'))
  checkEqual('拆分不重复段', new Set(partKeys).size, partKeys.length)
  const oversized = builder.buildCardParts(templateState, {}, 800, TEST_CARD_NAME)
  check('单段超过上限时会报 tooLarge', oversized.parts.length === 0 && oversized.tooLarge.length > 0)
  check(
    'tooLarge 标出段名',
    oversized.tooLarge.every((item) => item.key && item.length > 800),
  )

  // ── 半熟练 ──────────────────────────────────────────────────────────
  const halfBase = '$姓名$ 半熟练测试\n$等级$ 5\n$属性$ 10/14/10/10/14/10\n'
  const joat14 = builder.parseCardText(halfBase + '$半熟练$ 全部:向下')
  check('半熟练解析无错误', joat14.errors.length === 0, JSON.stringify(joat14.errors))
  const joat14Values = builder.deriveCheckValues(joat14.state)
  checkEqual('2014 万事通先攻', joat14Values['先攻'], '+3')
  checkEqual('2014 万事通运动', joat14Values['运动'], '+1')
  checkEqual('2014 万事通察觉', joat14Values['察觉'], '+3')
  checkEqual('2014 万事通纯属性检定', joat14Values['智力'], '+1')
  checkEqual('2014 万事通不加豁免', joat14Values['敏捷豁免'], '+2')
  checkEqual('2014 万事通派生先攻', builder.deriveInitiative(joat14.state), '+3')
  checkEqual('2014 万事通派生被动', builder.derivePassivePerception(joat14.state), '13')

  const joat24 = builder.parseCardText(halfBase + '$半熟练$ 技能:向下')
  const joat24Values = builder.deriveCheckValues(joat24.state)
  checkEqual('2024 万事通先攻不适用', joat24Values['先攻'], '+2')
  checkEqual('2024 万事通运动', joat24Values['运动'], '+1')
  checkEqual('2024 万事通察觉', joat24Values['察觉'], '+3')
  checkEqual('2024 万事通纯属性检定不适用', joat24Values['智力'], '+0')

  const athlete = builder.parseCardText(halfBase + '$半熟练$ 力敏体:向上')
  const athleteValues = builder.deriveCheckValues(athlete.state)
  checkEqual('运动健将先攻', athleteValues['先攻'], '+4')
  checkEqual('运动健将运动', athleteValues['运动'], '+2')
  checkEqual('运动健将察觉不适用', athleteValues['察觉'], '+2')

  const bothHalf = builder.parseCardText(halfBase + '$半熟练$ 力敏体:向上; 全部:向下')
  const bothValues = builder.deriveCheckValues(bothHalf.state)
  checkEqual('半熟练重叠取较高', bothValues['先攻'], '+4')
  checkEqual('半熟练重叠技能取较高', bothValues['运动'], '+2')
  checkEqual('半熟练重叠感知取向下', bothValues['察觉'], '+3')
  checkEqual(
    '半熟练规则回写排序',
    builder.contentFor(bothHalf.state, K.HALF_PROF),
    '全部:向下; 力敏体:向上',
  )
  const halfSerialized = builder.serializeCard(bothHalf.state)
  const halfReparsed = builder.parseCardText(halfSerialized)
  check('半熟练回写可再解析', halfReparsed.errors.length === 0, JSON.stringify(halfReparsed.errors))
  checkEqual('半熟练回写幂等', builder.serializeCard(halfReparsed.state), halfSerialized)

  const fullProf = builder.parseCardText(halfBase + '$熟练$ 先攻\n$半熟练$ 全部:向下')
  checkEqual('熟练优先于半熟练', builder.deriveCheckValues(fullProf.state)['先攻'], '+5')

  const halfCommand = builder
    .buildSegmentCommands(joat14.state, {}, TEST_CARD_NAME)
    .find((item) => item.key === K.HALF_PROF)
  check('半熟练有分段命令', Boolean(halfCommand))
  check(
    '半熟练分段命令可导入',
    halfCommand && builder.parseCardText(halfCommand.command).errors.length === 0,
  )

  const badHalf = builder.parseCardText(halfBase + '$半熟练$ 全部:随便')
  check(
    '半熟练取整方式错误被拒绝',
    badHalf.errors.some(
      (error) => error.key === K.HALF_PROF && error.message.includes('取整方式'),
    ),
    JSON.stringify(badHalf.errors),
  )

  // ── 角色卡预览 ──────────────────────────────────────────────────────
  const previewState = builder.parseCardText(templateFixture.text).state
  const previewView = buildPreviewView(builder, previewState, { rulesVersion: '5r' }, '')
  checkEqual('预览姓名', previewView.name, '伊瑟兰·晨星')
  checkEqual('预览副标题', previewView.subtitle, '高等精灵 · 法师（塑能师） · 5 级')
  checkEqual('预览经验', [previewView.xp, previewView.xpNext].join('/'), '6,500/14,000')
  checkEqual('预览武器数', previewView.weapons.length, 4)
  checkEqual('预览法术分组数', previewView.spellGroups.length, 4)
  checkEqual('预览法术位网格', previewView.slotRows.length, 3)
  const previewHtml = renderPreviewHtml(previewView, cardCss)
  check('预览 HTML 有卡面容器', previewHtml.includes('class="sheet card"'))
  check('预览 HTML 有立绘占位', previewHtml.includes('photo placeholder'))
  check('预览 HTML 含法术表', previewHtml.includes('spell-table') && previewHtml.includes('火球术'))
  check('预览 HTML 含武器表', previewHtml.includes('weapon-panel') && previewHtml.includes('火焰箭'))
  previewState[K.NAME] = '<测试&>'
  const escapedHtml = renderPreviewHtml(
    buildPreviewView(builder, previewState, { rulesVersion: '5r' }, ''),
    cardCss,
  )
  check('预览文本做 HTML 转义', escapedHtml.includes('&lt;测试&amp;&gt;') && !escapedHtml.includes('<测试&>'))
  const edgeState = builder.parseCardText(fixtures[1].text).state
  const edgeView = buildPreviewView(builder, edgeState, { rulesVersion: '5e' }, '')
  const edgeInitiative = edgeView.coreStats.find((item) => item.label === '先攻')
  check(
    '预览先攻保留骰子加值',
    edgeInitiative && edgeInitiative.value.includes('+1d4'),
    JSON.stringify(edgeInitiative),
  )
  const edgePassive = edgeView.coreStats.find((item) => item.label === '被动察觉')
  check(
    '预览被动察觉按察觉加值现算',
    edgePassive && edgePassive.value === '10',
    JSON.stringify(edgePassive),
  )
  const halfPreview = buildPreviewView(builder, joat14.state, { rulesVersion: '5e' }, '')
  const halfInitiative = halfPreview.coreStats.find((item) => item.label === '先攻')
  checkEqual('预览先攻含半熟练', halfInitiative && halfInitiative.value, '+3')
  const halfSkillRows = halfPreview.abilities.flatMap((ability) => ability.skills)
  const halfAthletics = halfSkillRows.find((skill) => skill.name === '运动')
  check('预览技能半熟练标记', halfAthletics && halfAthletics.half === true, JSON.stringify(halfAthletics))
  const halfHtml = renderPreviewHtml(halfPreview, cardCss)
  check(
    '预览半熟练的半标记在加值后',
    halfHtml.includes('<span class="skv">+1</span><span class="half-mark">半</span>'),
  )

  // ── 汇总 ────────────────────────────────────────────────────────────
  if (failed > 0) {
    console.error(`\n网页建卡器校验失败：${failed} 项（通过 ${passed} 项）`)
    for (const failure of failures) console.error(`  ✗ ${failure}`)
    process.exitCode = 1
    return
  }
  console.log(`网页建卡器校验通过：${passed} 项（${fixtures.length} 个样例往返稳定）`)
}

main()
