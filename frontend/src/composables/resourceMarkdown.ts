import type { LearningResource, MindmapNode, Source } from '../types/resources'

function bullet(text: string, depth = 0): string {
  const indent = '  '.repeat(depth)
  return indent + '- ' + text.replaceAll('\n', '\n' + indent + '  ')
}

function outline(node: MindmapNode, depth = 0): string {
  return [bullet(node.label, depth), ...node.children.map(child => outline(child, depth + 1))].join('\n')
}

export function resourceMarkdown(resource: LearningResource, sources: Source[]): string {
  const content = resource.content
  const blocks = ['# ' + content.title, resource.notice]
  if (content.resource_type === 'lecture') {
    blocks.push('## 学习目标', content.learning_objectives.map(text => bullet(text)).join('\n'))
    blocks.push('## 先修知识', content.prerequisites.map(text => bullet(text)).join('\n'))
    for (const section of content.sections) blocks.push('## ' + section.heading, section.explanation)
    if (content.examples.length) blocks.push('## 示例')
    for (const example of content.examples) blocks.push('### ' + example.title, example.content)
    blocks.push('## 小结', content.summary)
  } else if (content.resource_type === 'exercise') {
    for (const question of content.questions) {
      blocks.push('## ' + question.question_id, question.prompt)
      if (question.options) blocks.push(question.options.map(option => bullet(option.label + '. ' + option.content)).join('\n'))
      blocks.push('### 答案', question.answer, '### 解析', question.analysis)
    }
  } else {
    blocks.push('## 知识结构', outline(content.root))
  }
  if (content.source_ids.length) blocks.push('## 来源与依据')
  for (const id of content.source_ids) {
    const source = sources.find(item => item.id === id)
    blocks.push(source ? bullet([source.title, source.locator, source.source, source.license].filter(Boolean).join(' · ')) : bullet(id + '（来源详情未加载）'))
  }
  return blocks.join('\n\n') + '\n'
}

export function markdownFilename(title: string): string {
  let name = Array.from(title.replace(/[<>:"/\\|?*\u0000-\u001f]/g, '_').trim()).slice(0, 80).join('').replace(/[. ]+$/, '')
  if (/^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)/i.test(name)) name = '_' + name
  return (name || '学习资源') + '.md'
}
