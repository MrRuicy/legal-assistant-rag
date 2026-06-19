/* ============================================================
   utils/citation.ts — 把检索条文按「回答实际引用」过滤
   依据后端 verify.cited（如「《劳动合同法》第19条」/「第19条」）。
   原则：可多显示不可少显示 —— 只用条号做命中判断，法律名不作排除条件，
   避免法律名简称/全称差异把真正被引用的条文误删。
   ============================================================ */

import type { Reference, VerifyResult } from '@/types/chat'

/** 从引用标签里抽出阿拉伯条号 */
function citedArticleNos(cited: string[]): Set<string> {
  const nos = new Set<string>()
  for (const label of cited) {
    const m = label.match(/第\s*(\d+)\s*条/)
    if (m) nos.add(m[1])
  }
  return nos
}

/**
 * 只保留回答中实际引用到的条文（按条号宽松匹配）。
 * 兜底（任一成立即返回全部，宁可多显示）：
 * - cited 为空（status 'none' 等无法判断）
 * - 解析不出任何条号
 * - 匹配结果为空（标签与 hits 对不上）
 */
export function filterCitedRefs(
  refs: Reference[] | undefined,
  verify: VerifyResult | undefined,
): Reference[] {
  if (!refs?.length) return []
  const cited = verify?.cited ?? []
  if (!cited.length) return refs

  const nos = citedArticleNos(cited)
  if (!nos.size) return refs

  const filtered = refs.filter((r) => nos.has(String(r.article_no)))
  return filtered.length ? filtered : refs
}

/**
 * 「被回答引用、但检索库里没有」的条文标签（模型知识泄漏）。
 * 取后端 verify.fabricated，再剔除「条号其实检索到了、只是法律名简称没匹配上」
 * 的误判（口径与 filterCitedRefs 的按条号判断一致）。
 * 返回可读标签列表（如「《劳动合同法》第40条」），供引用区诚实提示。
 */
export function missingCitedLabels(
  refs: Reference[] | undefined,
  verify: VerifyResult | undefined,
): string[] {
  const fabricated = verify?.fabricated ?? []
  if (!fabricated.length) return []

  const retrievedNos = new Set((refs ?? []).map((r) => String(r.article_no)))
  return fabricated.filter((label) => {
    const m = label.match(/第\s*(\d+)\s*条/)
    // 条号解析不出 → 保守显示；条号在检索集里 → 视为简称误判，不提示
    if (!m) return true
    return !retrievedNos.has(m[1])
  })
}


