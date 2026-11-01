import axios from 'axios';
import {
  SystemHealth,
  Project,
  TestRun,
  FlakinessReport,
  DetailedRunReportResponse,
  IterationDiffResponse,
  RunComparisonResponse,
  FixVerificationRequest,
  FixVerificationResponse,
} from '../types';

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

export interface RunListParams {
  project_id?: string;
  status?: string;
  run_type?: string;
  search?: string;
  sort_by?: string;
  sort_order?: string;
  limit?: number;
  offset?: number;
}

export const runsApi = {
  list: async (params?: RunListParams): Promise<TestRun[]> => {
    const response = await api.get<TestRun[]>('/runs', { params });
    return response.data;
  },
  get: async (id: string): Promise<TestRun> => {
    const response = await api.get<TestRun>(`/runs/${id}`);
    return response.data;
  },
  compare: async (runAId: string, runBId: string): Promise<RunComparisonResponse> => {
    const response = await api.get<RunComparisonResponse>('/comparison', {
      params: { run_a_id: runAId, run_b_id: runBId },
    });
    return response.data;
  },
};

export const reportsApi = {
  getByRun: async (runId: string): Promise<FlakinessReport[]> => {
    const response = await api.get<FlakinessReport[]>(`/reports/run/${runId}`);
    return response.data;
  },
  getDetailed: async (runId: string): Promise<DetailedRunReportResponse> => {
    const response = await api.get<DetailedRunReportResponse>(`/reports/run/${runId}/detailed`);
    return response.data;
  },
  getDiff: async (runId: string, testCaseId: string): Promise<IterationDiffResponse> => {
    const response = await api.get<IterationDiffResponse>(`/reports/run/${runId}/diff/${testCaseId}`);
    return response.data;
  },
  analyze: async (runId: string): Promise<FlakinessReport[]> => {
    const response = await api.post<FlakinessReport[]>(`/runs/${runId}/analyze`);
    return response.data;
  },
  rca: async (runId: string): Promise<FlakinessReport[]> => {
    const response = await api.post<FlakinessReport[]>(`/runs/${runId}/rca`);
    return response.data;
  },
};

export const verificationApi = {
  start: async (payload: FixVerificationRequest): Promise<TestRun> => {
    const response = await api.post<TestRun>('/verification', payload);
    return response.data;
  },
  get: async (runId: string): Promise<FixVerificationResponse> => {
    const response = await api.get<FixVerificationResponse>(`/verification/${runId}`);
    return response.data;
  },
};

export default api;

