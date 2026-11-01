import axios from 'axios';
import { SystemHealth, Project, TestRun, FlakinessReport } from '../types';

const api = axios.create({
  baseURL: '/api',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const healthApi = {
  getHealth: async (): Promise<SystemHealth> => {
    const response = await api.get<SystemHealth>('/health');
    return response.data;
  },
};

export const projectsApi = {
  list: async (): Promise<Project[]> => {
    const response = await api.get<Project[]>('/projects');
    return response.data;
  },
  get: async (id: string): Promise<Project> => {
    const response = await api.get<Project>(`/projects/${id}`);
    return response.data;
  },
};

export const runsApi = {
  list: async (): Promise<TestRun[]> => {
    const response = await api.get<TestRun[]>('/runs');
    return response.data;
  },
  get: async (id: string): Promise<TestRun> => {
    const response = await api.get<TestRun>(`/runs/${id}`);
    return response.data;
  },
};

export const reportsApi = {
  getByRun: async (runId: string): Promise<FlakinessReport[]> => {
    const response = await api.get<FlakinessReport[]>(`/reports/run/${runId}`);
    return response.data;
  },
  analyze: async (runId: string): Promise<FlakinessReport[]> => {
    const response = await api.post<FlakinessReport[]>(`/runs/${runId}/analyze`);
    return response.data;
  },
};

export default api;

