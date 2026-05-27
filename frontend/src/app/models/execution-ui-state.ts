export interface ExecutionUiState {
  status: 'idle' | 'running' | 'success' | 'error';
  title: string;
  stage?: string;
  progress?: number;
  detail?: string;
}
