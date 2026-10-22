/**
 * 网页建卡器的 Node 往返校验（`docs:build` 前自动运行）。
 *
 * 只做纯函数校验，不启动浏览器、不依赖 Vue：
 * 1. `card-spec.json` 与 `core.mjs` 的段清单/回写顺序互相对齐；
 * 2. 样例卡「解析 → 回写 → 再解析」稳定，规范样例逐字不变；
 * 3. 整卡命令、分段命令、精简整卡都能被导入逻辑读回；
 * 4. 编辑表单后回写的内容仍可被解析，关键值与派生值不丢。
 *
 * 失败时逐条打印（带样例名与段名），并以退出码 1 结束构建。
 */

import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  CARD_COMMAND,
  K,
  SEGMENT_KINDS,
  createCardBuilder,
} from '../theme/card-builder/core.mjs'

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
  const builder = createCardBuilder(spec)

  // ── 1. 清单对齐 ──────────────────────────────────────────────────────
  const specKeys = spec.segments.map((segment) => segment.key)
  const kindKeys = Object.keys(SEGMENT_KINDS)
  checkEqual('段清单数量', specKeys.length, 25)
  checkEqual('表单形态数量', kindKeys.length, 25)
  for (const key of specKeys) {
    check(`段 ${key} 有表单形态`, Boolean(SEGMENT_KINDS[key]))
  }
  for (const key of kindKeys) {
    check(`表单形态 ${key} 在清单中`, specKeys.includes(key))
  }
  checkEqual('回写顺序覆盖段清单', [...new Set(spec.output_order)].sort().join('|'), [...specKeys].sort().join('|'))
  check('回写顺序无重复', new Set(spec.output_order).size === spec.output_order.length)
  check('分组 id 非空', spec.groups.every((group) => group.id && group.label))
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
    const commands = builder.buildSegmentCommands(parsed.state, options)
    check(`${name}: 分段命令非空`, commands.length > 0)
    for (const item of commands) {
      check(
        `${name}: 命令格式 ${item.key}`,
        item.command.startsWith(`${CARD_COMMAND} ${item.key} `),
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
    // 整卡命令与精简整卡都可导入
    const whole = `${CARD_COMMAND}\n${serialized}`
    const wholeParsed = builder.parseCardText(whole)
    check(`${name}: 整卡命令可导入`, wholeParsed.errors.length === 0)
    checkEqual(`${name}: 整卡命令内容不变`, builder.serializeCard(wholeParsed.state, options), serialized)
    const minimal = builder.buildMinimalCard(parsed.state, options)
    check(`${name}: 精简整卡非空`, minimal.length > 0)
    check(`${name}: 精简整卡含等级`, minimal.includes('$等级$'))
    check(`${name}: 精简整卡含属性`, minimal.includes('$属性$'))
    const minimalParsed = builder.parseCardText(minimal)
    check(`${name}: 精简整卡可导入`, minimalParsed.errors.length === 0)
  }

  // 粘贴 .角色卡模板 的完整回复（卡 + 提示）也能导入
  const tips =
    '\n\n——提示（记录时请仅复制上方模板段并修改）——\n' +
    '属性段六个数值依次对应: 力量/敏捷/体质/智力/感知/魅力\n'
  const templateWithTips = builder.parseCardText(`${CARD_COMMAND}\n${templateFixture.text}${tips}`)
  check('模板回复（含提示）可导入', templateWithTips.errors.length === 0)
  checkEqual(
    '模板回复（含提示）内容不变',
    builder.serializeCard(templateWithTips.state),
    templateFixture.text,
  )

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
  state[K.COMBAT] = { AC: '18', 先攻: '+9', 速度: '30', 被动察觉: '12' }
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
  checkEqual('编辑后的卡战斗记录', editedParsed.state[K.COMBAT_NOTES][0], '祝福术(专注,3轮)')
  checkEqual('编辑后的卡技能专精', editedParsed.state[K.PROF].checks['运动'], 2)

  // 背景：固定键、5r 过滤 5e 专属项、未知键报错
  const fiveRText = builder.serializeCard(state, { rulesVersion: '5r' })
  const fiveEText = builder.serializeCard(state, { rulesVersion: '5e' })
  check('5r 不输出理想', !fiveRText.includes('理想:'), fiveRText)
  check('5e 输出理想', fiveEText.includes('理想:5e 专属背景项'))
  checkThrows('未知背景键被拒绝', () => builder.parseSegment(K.BACKGROUND, '故乡:无冬城'))

  // 先攻只读派生：敏捷 +1 + 先攻熟练 +3 + 额外 +2 = +6，忽略表单里的 +9
  checkEqual('先攻派生值', builder.deriveInitiative(state), '+6')
  check('卡文本用派生先攻', editedText.includes('先攻:+6'), editedText)
  check('卡文本不用表单先攻', !editedText.includes('先攻:+9'))
  checkEqual('熟练加值', builder.deriveProficiencyBonus(state), 3)
  checkEqual('下一级经验自动', builder.deriveXpNext(state), '14000')
  check('卡文本用自动下一级经验', editedText.includes('经验:6500/14000'))
  check('卡文本不用手填下一级经验', !editedText.includes('99999'))

  // 职业特性按等级升序
  checkEqual(
    '职业特性按等级排序',
    builder.contentFor(state, K.CLASS_TRAITS),
    '1|战斗风格:选择一种战斗风格/3|战斗大师:获得战技',
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

  // 武器命中加值允许骰子表达式（与插件同口径）
  const diceState = builder.createState()
  diceState[K.LEVEL] = '5'
  diceState[K.ABILITY] = ['10', '10', '10', '10', '10', '10']
  diceState[K.WEAPON] = [
    { name: '短剑', noAttack: false, attack: '+1d4', damage: '1d6+2', type: '穿刺', note: '' },
  ]
  check('武器命中骰子加值可导出', builder.validateState(diceState).errors.length === 0, JSON.stringify(builder.validateState(diceState).errors))
  checkEqual('武器命中骰子加值保留', builder.contentFor(diceState, K.WEAPON), '短剑+1d4,1d6+2穿刺')

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

  // 单段命令（首次建卡前后追加）能只导入这一段
  const single = builder.parseCardText(`${CARD_COMMAND} $战斗$ AC:15; 先攻:+2; 速度:30; 被动察觉:13`)
  check('单段命令解析成功', single.errors.length === 0)
  checkEqual('单段命令只识别一段', single.found, 1)
  checkEqual('单段命令战斗段 AC', single.state[K.COMBAT].AC, '15')

  // 多条分段命令粘在一起也能导入（每条各占一行）
  const multi = builder.parseCardText(
    [
      `${CARD_COMMAND} $姓名$ 多段导入`,
      `${CARD_COMMAND} $等级$ 3`,
      `${CARD_COMMAND} $属性$ 10/11/12/13/14/15`,
    ].join('\n'),
  )
  check('多条分段命令解析成功', multi.errors.length === 0, JSON.stringify(multi.errors))
  checkEqual('多条分段命令段数', multi.found, 3)
  checkEqual('多条分段命令姓名', multi.state[K.NAME], '多段导入')
  checkEqual('多条分段命令等级', multi.state[K.LEVEL], '3')

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
