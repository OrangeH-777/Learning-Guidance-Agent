export interface MindmapNode { label: string; children: MindmapNode[] }
export interface Question { question_type: 'single_choice' | 'short_answer'; question_id: string; prompt: string; options?: { label: string; content: string }[]; answer: string; analysis: string }
interface Base { title: string; source_ids: string[] }
export type Content = Base & (
  { resource_type: 'lecture'; learning_objectives: string[]; prerequisites: string[]; sections: { heading: string; explanation: string }[]; examples: { title: string; content: string }[]; summary: string } |
  { resource_type: 'exercise'; questions: Question[] } |
  { resource_type: 'mindmap'; root: MindmapNode }
)
export interface GenerationProcess {
  chapter: string | null
  planning: { objectives: string[]; outline: string[] } | null
  regenerations: number
  passed_checks: string[]
  format_unchanged: boolean | null
}
export interface LearningResource { process?: GenerationProcess; id: string; course_id: string; topic: string; content: Content; notice: string; human_pass: boolean; created_at: string; metadata: { profile: { version: number }; model: { model_id: string; protocol: string }; knowledge_version: string; prompt_version: string; automatic_checks: string } }
export interface Source { id: string; title: string; locator: string; source: string; license: string; content: string }
