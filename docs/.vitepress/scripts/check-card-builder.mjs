/**
 * 网页建卡器的 Node 往返校验（`docs:build` 前自动运行）。
 *
 * 只做纯函数校验，不启动浏览器、不依赖 Vue：
 * 1. `card-spec.json` 与 `core.mjs` 的段清单/回写顺序互相对齐；
 * 2. 样例卡「解析 → 回写 → 再解析」稳定，规范样例逐字不变；
 * 3. 整卡命令、分段命令、精简整卡都能被导入逻辑读回；
 * 4. 编辑表单后回写的内容仍可被解析，关键值不丢。
 *
 * 失败时逐条打印（带样例名与段名），并以退出码 1 结束构建。
 */

import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  CARD_COMMAND,
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
  check('分组 id 非空', spec.groups.every((group) => group.id && group.label))
  check(
    '段的 group 都在分组表内',
    spec.segments.every((segment) => spec.groups.some((group) => group.id === segment.group)),
  )

  // ── 2. 示例卡 = 模板样例 ────────────────────────────────────────────
  const exampleCard = builder.buildExampleCard()
  const templateFixture = fixtureData.fixtures.find((item) => item.name === 'template')
  check('存在模板样例', Boolean(templateFixture))
  checkEqual('spec 示例拼出的卡 = 模板样例', exampleCard, templateFixture.text)

  // ── 3. 各样例往返 ───────────────────────────────────────────────────
  const fixtures = fixtureData.fixtures
  check('至少 3 个样例', fixtures.length >= 3)
  const states = new Map()
  for (const fixture of fixtures) {
    const name = fixture.name
    const parsed = builder.parseCardText(fixture.text)
    states.set(name, parsed.state)
    check(`${name}: 解析无错误`, parsed.errors.length === 0, JSON.stringify(parsed.errors))
    check(`${name}: 段数大于 0`, parsed.found > 0)
    const serialized = builder.serializeCard(parsed.state)
    check(`${name}: 回写结果非空`, serialized.length > 0)
    const reparsed = builder.parseCardText(serialized)
    check(`${name}: 回写可再次解析`, reparsed.errors.length === 0, JSON.stringify(reparsed.errors))
    const reserialized = builder.serializeCard(reparsed.state)
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
    const commands = builder.buildSegmentCommands(parsed.state)
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
        builder.contentFor(single.state, item.key),
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
    checkEqual(`${name}: 整卡命令内容不变`, builder.serializeCard(wholeParsed.state), serialized)
    const minimal = builder.buildMinimalCard(parsed.state)
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

  state['$姓名$'] = '测试角色'
  state['$种族$'] = '人类'
  state['$职业$'] = '战士'
  state['$等级$'] = '5'
  state['$属性$'] = ['16', '12', '14', '10', '11', '13']
  state['$生命值$'] = { cur: '44', max: '44', temp: '' }
  state['$生命骰$'] = { num: '5', max: '5', type: '10' }
  state['$战斗$'] = { AC: '18', 先攻: '+1', 速度: '30', 被动察觉: '12' }
  state['$进度$'] = { xp: '6500', xpNext: '14000', inspiration: '有' }
  state['$专长$'] = [{ name: '巨武器大师', text: '可以用附赠动作再攻击一次' }]
  state['$武器$'] = [
    { name: '长剑', noAttack: false, attack: '+6', damage: '1d8+3', type: '挥砍', note: '双手' },
    { name: '火焰箭', noAttack: true, attack: '', damage: '2d10', type: '火焰', note: '120尺' },
  ]
  state['$物品$'] = [{ name: '治疗药水', qty: '2', equipped: false }]
  state['$钱币$'] = { CP: '0', SP: '8', EP: '0', GP: '18', PP: '0' }
  state['$技能$']['运动'] = { bonus: '+5', expertise: false }
  state['$技能$']['威吓'] = { bonus: '+7', expertise: true }
  state['$豁免$'][0] = '+5'
  state['$熟练$'].checks['力量豁免'] = 1
  state['$熟练$'].checks['运动'] = 2
  state['$熟练$'].groups['武器'] = '军用武器·简易武器'
  state['$额外加值$'] = [{ key: '运动', adv: '优势', bonus: '+2' }]
  state['$能力$'] = [
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
  state['$法术$'] = {
    ability: '',
    dc: '',
    attack: '',
    list: [],
  }
  state['$法术位$'].levels[0] = { cur: '2', max: '2' }
  state['$战斗记录$'] = ['祝福术(专注,3轮)']

  const editedValidation = builder.validateState(state)
  check('编辑后的表单无错误', editedValidation.errors.length === 0, JSON.stringify(editedValidation.errors))
  const editedText = builder.serializeCard(state)
  const editedParsed = builder.parseCardText(editedText)
  check('编辑后的卡可再次解析', editedParsed.errors.length === 0)
  checkEqual('编辑后的卡姓名保留', editedParsed.state['$姓名$'], '测试角色')
  checkEqual('编辑后的卡等级保留', editedParsed.state['$等级$'], '5')
  checkEqual('编辑后的卡职业保留', editedParsed.state['$职业$'], '战士')
  checkEqual('编辑后的卡武器数', editedParsed.state['$武器$'].length, 2)
  checkEqual('编辑后的卡专长说明', editedParsed.state['$专长$'][0].text, '可以用附赠动作再攻击一次')
  checkEqual('编辑后的卡熟练组', editedParsed.state['$熟练$'].groups['武器'], '军用武器·简易武器')
  checkEqual('编辑后的卡能力恢复档', builder.contentFor(editedParsed.state, '$能力$'), '动作如潮:1/1短休+1,长休|短休回复一次')
  checkEqual('编辑后的卡战斗记录', editedParsed.state['$战斗记录$'][0], '祝福术(专注,3轮)')
  checkEqual('编辑后的卡技能专精', editedParsed.state['$技能$']['威吓'].expertise, true)

  // 故事换行自动合并（不产生非法换行）
  const storyState = builder.createState()
  storyState['$故事$'] = '第一行\n第二行'
  checkEqual('故事换行合并', builder.contentFor(storyState, '$故事$'), '第一行第二行')

  // 武器命中加值允许骰子表达式（与插件同口径）
  const diceState = builder.createState()
  diceState['$等级$'] = '5'
  diceState['$属性$'] = ['10', '10', '10', '10', '10', '10']
  diceState['$武器$'] = [
    { name: '短剑', noAttack: false, attack: '+1d4', damage: '1d6+2', type: '穿刺', note: '' },
  ]
  check('武器命中骰子加值可导出', builder.validateState(diceState).errors.length === 0, JSON.stringify(builder.validateState(diceState).errors))
  checkEqual('武器命中骰子加值保留', builder.contentFor(diceState, '$武器$'), '短剑+1d4,1d6+2穿刺')

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
  badState['$等级$'] = '5'
  badState['$属性$'] = ['10', '10', '10', '10', '10', '10']
  badState['$姓名$'] = '带$符号'
  const badValidation = builder.validateState(badState)
  check('姓名含 $ 被拦截', badValidation.errors.some((item) => item.key === '$姓名$'))
  badState['$姓名$'] = '正常'
  badState['$武器$'] = [
    { name: '长剑', noAttack: false, attack: '+5', damage: '1d8+3', type: '火焰剑', note: '' },
  ]
  const weaponValidation = builder.validateState(badState)
  check('武器伤害类型写错被拦截', weaponValidation.errors.some((item) => item.key === '$武器$'))
  badState['$武器$'] = [{ name: '长剑', noAttack: false, attack: '+5', damage: '1d8+3', type: '', note: '' }]
  badState['$等级$'] = 'abc'
  check('等级非数字被拦截', builder.validateState(badState).errors.some((item) => item.key === '$等级$'))

  // 单段命令（首次建卡前后追加）能只导入这一段
  const single = builder.parseCardText(`${CARD_COMMAND} $战斗$ AC:15; 先攻:+2; 速度:30; 被动察觉:13`)
  check('单段命令解析成功', single.errors.length === 0)
  checkEqual('单段命令只识别一段', single.found, 1)
  checkEqual('单段命令战斗段 AC', single.state['$战斗$'].AC, '15')

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
  checkEqual('多条分段命令姓名', multi.state['$姓名$'], '多段导入')
  checkEqual('多条分段命令等级', multi.state['$等级$'], '3')

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
