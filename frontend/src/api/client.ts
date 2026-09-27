import axios from 'axios'

// Business requests will use the same-origin /api proxy.
// Provider API keys must never be added to this browser client.
export const apiClient = axios.create({ baseURL: '/api', timeout: 10_000 })

export interface HealthResponse {
  status: string
  service: string
  stage: string
}

export async function getHealth(): Promise<HealthResponse> {
  const response = await axios.get<HealthResponse>('/health', { timeout: 5_000 })
  return response.data
}
