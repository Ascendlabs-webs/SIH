export type AlertLevel = 'GREEN' | 'YELLOW' | 'ORANGE' | 'RED';

export interface FeatureSummary {
  mfcc_mean: number[];
  spectral_centroid_mean: number;
  spectral_bandwidth_mean: number;
  spectral_rolloff_mean: number;
  spectral_flux_mean: number;
  zcr_mean: number;
  rms_mean: number;
  f0_mean: number;
  f0_std: number;
  silence_ratio: number;
  vad_active_ratio: number;
}

export interface AnalysisResult {
  risk_score: number;
  alert_level: AlertLevel;
  classification: 'REAL' | 'SYNTHETIC';
  confidence: number;
  recommendation: string;
  timestamp: string;
  window_duration: number;
  latency_ms: number;
  latency_breakdown: Record<string, number>;
  model_raw_score: number;
  score_calibrated: boolean;
  audio_risk: number;
  context_risk: number;
  requires_secondary_verification: boolean;
  protection_state: string;
  protection_actions: string[];
  sample_rate: number;
  vad_active: boolean;
  detector: string;
  features?: FeatureSummary | null;
}

export interface StatusResponse {
  app: string;
  version: string;
  detector: string;
  detector_label: string;
  target_sample_rate: number;
  window_seconds: number;
  store_raw_audio: boolean;
  rolling_window_size: number;
  history_count: number;
}

export interface CallContext {
  caller_known: boolean;
  pending_transaction: boolean;
  sensitive_action: boolean;
  call_type: 'webrtc' | 'twilio' | 'vonage' | 'upload' | 'demo' | 'mic';
}

export interface ProtectionSnapshot {
  state: string;
  required_actions: string[];
  pending_challenges: Array<{ channel: string; status: string; at: string; demo: boolean }>;
  last_alert_level: AlertLevel;
  transitioned: boolean;
  updated_at: string;
}

export interface ModelStatus {
  detector_mode: string;
  active_detector: string;
  is_demo: boolean;
  mode_label: 'DEMO' | 'REAL ML';
  model_loaded: boolean;
  model_name: string;
  model_path: string;
  device: string;
  num_params: number;
  warning: string | null;
}
