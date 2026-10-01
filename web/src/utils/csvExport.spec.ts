import { describe, expect, it } from 'vitest'

import { csvCell, toCsv } from './csvExport'

describe('csvCell', () => {
  it('普通文本原样输出', () => {
    expect(csvCell('栈')).toBe('栈')
    expect(csvCell(30)).toBe('30')
  })

  it('null / undefined 输出空串', () => {
    expect(csvCell(null)).toBe('')
    expect(csvCell(undefined)).toBe('')
  })

  it.each(['=1+1', '+A1', '-2+3', '@SUM(A1)'])(
    'CSV Formula Injection：%s 加前导单引号',
    (value) => {
      expect(csvCell(value)).toBe(`'${value}`)
    },
  )

  it('前导制表符同样被视为公式风险（且制表符本身不需要加引号）', () => {
    expect(csvCell('\tcmd')).toBe("'\tcmd")
  })

  it('前导回车既被识别为公式风险，又因含 \\r 触发 RFC4180 引号包裹', () => {
    expect(csvCell('\rcmd')).toBe('"\'\rcmd"')
  })

  it('前导单引号只对危险开头生效，普通短横线在中间不受影响', () => {
    expect(csvCell('数据结构-线性表')).toBe('数据结构-线性表')
  })

  it('含逗号 / 双引号 / 换行的字段整体加引号，内部引号翻倍', () => {
    expect(csvCell('a,b')).toBe('"a,b"')
    expect(csvCell('say "hi"')).toBe('"say ""hi"""')
    expect(csvCell('l1\nl2')).toBe('"l1\nl2"')
  })

  it('危险开头与需要转义的字段可叠加处理', () => {
    expect(csvCell('=cmd,"x"')).toBe('"\'=cmd,""x"""')
  })
})

describe('toCsv', () => {
  it('按 CRLF 连接行、逗号连接列', () => {
    expect(
      toCsv([
        ['行号', '名称'],
        [1, '栈'],
      ]),
    ).toBe('行号,名称\r\n1,栈')
  })
})
