// 大阶段 4 M3：结果 CSV 在浏览器本地生成（服务端不落盘临时文件）。
//
// 两件事必须做对：
// 1) CSV Formula Injection —— 以 = + - @ \t \r 开头的单元格会被 Excel / Sheets
//    当成公式执行。加前导单引号可让其退化为普通文本，且不影响人眼阅读。
// 2) RFC 4180 转义 —— 含分隔符、双引号或换行的字段整体加引号，内部引号翻倍。

const FORMULA_PREFIX = /^[=+\-@\t\r]/

export function csvCell(value: unknown): string {
  let text = value === null || value === undefined ? '' : String(value)
  if (FORMULA_PREFIX.test(text)) text = `'${text}`
  if (/[",\r\n]/.test(text)) text = `"${text.replace(/"/g, '""')}"`
  return text
}

export function toCsv(rows: readonly (readonly unknown[])[]): string {
  return rows.map((row) => row.map(csvCell).join(',')).join('\r\n')
}

// 带 UTF-8 BOM：没有它 Windows Excel 双击打开会把中文显示成乱码。
export function toCsvBlob(rows: readonly (readonly unknown[])[]): Blob {
  return new Blob([`\ufeff${toCsv(rows)}`], { type: 'text/csv;charset=utf-8' })
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}
