import axios from 'axios';

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 30000,
});

// Types
export interface ScanResponse {
  scan_id: number | null;
  risk_score: number;
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH';
  action: 'PASS_THROUGH' | 'SANITIZE' | 'BLOCK';
  primary_reason: string;
  total_processing_time_ms: number;
  layer_contributions: Record<string, number>;
  layers: {
    pattern_matcher: LayerResult | null;
    structural_analyzer: LayerResult | null;
    statistical_analyzer: LayerResult | null;
    ml_classifier: LayerResult | null;
  };
}

export interface LayerResult {
  layer: string;
  confidence: number;
  is_flagged: boolean;
  processing_time_ms: number;
  matches?: PatternMatch[];
  flags?: StructuralFlag[];
  signals?: StatSignal[];
  label?: string;
  model_used?: string;
  raw_scores?: Record<string, number>;
}

export interface PatternMatch {
  pattern_id: string;
  category: string;
  description: string;
  matched_text: string;
  start: number;
  end: number;
  weight: number;
}

export interface StructuralFlag {
  kind: string;
  description: string;
  location: string;
  span: [number, number];
  severity: number;
}

export interface StatSignal {
  name: string;
  value: number;
  weight: number;
  description: string;
}

export interface LogEntry {
  id: number;
  timestamp: string;
  source_type: string;
  source_name: string;
  risk_score: number;
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH';
  action_taken: 'PASS_THROUGH' | 'SANITIZE' | 'BLOCK';
  matched_patterns: string[];
  primary_reason: string;
  layer_contributions: Record<string, number>;
  raw_snippet: string;
  is_false_positive: boolean | null;
}

export interface LogsResponse {
  total: number;
  page: number;
  page_size: number;
  items: LogEntry[];
}

export interface StatsResponse {
  total_scans: number;
  blocked_count: number;
  sanitized_count: number;
  passed_count: number;
  blocked_pct: number;
  false_positive_count: number;
  false_positive_rate: number;
  top_patterns: { pattern_id: string; count: number }[];
  risk_distribution: Record<string, number>;
  scans_over_time: { date: string; count: number }[];
}

export interface SettingsResponse {
  low_threshold: number;
  high_threshold: number;
  enabled_layers: string[];
  layer_weights: Record<string, number>;
}

// API methods
export const scanText = (text: string, sourceName = 'inline') =>
  api.post<ScanResponse>('/scan', { text, source_name: sourceName }).then(r => r.data);

export const scanFile = (file: File) => {
  const form = new FormData();
  form.append('file', file);
  return api.post<ScanResponse>('/scan/file', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then(r => r.data);
};

export const getLogs = (page = 1, pageSize = 20, riskLevel?: string) =>
  api.get<LogsResponse>('/logs', {
    params: { page, page_size: pageSize, ...(riskLevel ? { risk_level: riskLevel } : {}) },
  }).then(r => r.data);

export const getStats = (days = 30) =>
  api.get<StatsResponse>('/stats', { params: { days } }).then(r => r.data);

export const submitFeedback = (scanId: number, isFalsePositive: boolean, note = '') =>
  api.post('/feedback', { scan_id: scanId, is_false_positive: isFalsePositive, note }).then(r => r.data);

export const getSettings = () =>
  api.get<SettingsResponse>('/settings').then(r => r.data);

export const updateThresholds = (low: number, high: number) =>
  api.put('/settings/thresholds', { low_threshold: low, high_threshold: high }).then(r => r.data);

export const toggleLayer = (layer: string, enabled: boolean) =>
  api.put('/settings/layers', { layer, enabled }).then(r => r.data);

export default api;
