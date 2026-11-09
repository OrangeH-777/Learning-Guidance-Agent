export interface User { id: string; username: string; is_admin: boolean }
export interface Course { id: string; name: string; description: string; enabled: boolean; knowledge_ready: boolean }
export interface ProfileFields { knowledge_base: string; learning_goal: string; preference: string }
export interface Profile { version: number; fields: ProfileFields | null }
export interface ModelSettings { version: number; configured: boolean; protocol?: string; base_url?: string; model_id?: string; has_key?: boolean; tested_at?: string }
export interface Task { id: string; course_id: string; topic: string; resource_type: string; status: string; error_code: string | null; resource_id: string | null; created_at: string; content_regenerations: number }
export interface HistoryItem { id: string; title: string; course_id: string; topic: string; resource_type: string; created_at: string }
