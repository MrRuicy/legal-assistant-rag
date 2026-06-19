/* ============================================================
   composables/useMarkdown.ts — Markdown 渲染 + 条号链接化
   把「《XX法》第N条」包成可点击 span（data-law / data-no），
   供 AiMessage 委托点击 → scrollToRef。
   ============================================================ */

import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js/lib/core'
import json from 'highlight.js/lib/languages/json'
import xml from 'highlight.js/lib/languages/xml'
import python from 'highlight.js/lib/languages/python'
import bash from 'highlight.js/lib/languages/bash'

// 法律回答里代码块罕见，只注册少量常用语言，避免打包全部 ~190 种
hljs.registerLanguage('json', json)
hljs.registerLanguage('xml', xml)
hljs.registerLanguage('html', xml)
hljs.registerLanguage('python', python)
hljs.registerLanguage('bash', bash)

const md = new MarkdownIt({
  html: false, // 不信任 LLM 输出的原始 HTML，防 XSS
  linkify: true,
  breaks: true,
  highlight(str, lang): string {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(str, { language: lang }).value
      } catch {
        /* fall through */
      }
    }
    return ''
  },
})

// 匹配「《法律名》第N条」或「第N条之N」；法律名可缺省
const LAW_REF_RE = /(《[^》]{1,30}》)?(第[一二三四五六七八九十百零\d]+条(?:之[一二三四五六七八九十\d]+)?)/g

/**
 * 渲染 Markdown 为安全 HTML，并把条号引用包成可点击 span。
 * 注意：仅在文本节点替换，避免破坏代码块/链接。markdown-it 输出后做后处理，
 * 但要避开 <pre>/<code> 内部——这里用简单策略：渲染后按 <pre>...</pre> 切分跳过。
 */
export function renderMarkdown(src: string): string {
  const html = md.render(src ?? '')
  return linkifyLawRefs(html)
}

function linkifyLawRefs(html: string): string {
  // 按 <pre>...</pre> 切段，奇数段是代码块（跳过）
  const parts = html.split(/(<pre[\s\S]*?<\/pre>)/g)
  return parts
    .map((seg) => {
      if (seg.startsWith('<pre')) return seg
      // 仅在标签外的文本里替换：粗略按标签切分
      return seg.replace(/(>)([^<]+)(<)/g, (_m, lt, text: string, gt) => {
        return lt + wrapRefs(text) + gt
      })
    })
    .join('')
}

function wrapRefs(text: string): string {
  return text.replace(LAW_REF_RE, (match, law: string | undefined, no: string) => {
    if (!no) return match
    const lawAttr = law ? law.replace(/[《》]/g, '') : ''
    return `<span class="law-ref" data-law="${escapeAttr(lawAttr)}" data-no="${escapeAttr(no)}">${match}</span>`
  })
}

function escapeAttr(s: string): string {
  return s.replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

export function useMarkdown() {
  return { renderMarkdown }
}
