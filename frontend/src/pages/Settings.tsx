import React, { useEffect, useState } from 'react';
import { Settings as SettingsIcon, Save, RefreshCw, ToggleLeft, ToggleRight, Info } from 'lucide-react';
import { getSettings, updateThresholds, toggleLayer } from '../api/client';
import type { SettingsResponse } from '../api/client';

const LAYER_INFO: Record<string, { label: string; desc: string; color: string }> = {
  pattern_matcher:    { label: 'Pattern Matcher',    desc: 'Regex/keyword rules from YAML ruleset', color: 'text-blue-400' },
  structural_analyzer:{ label: 'Structural Analyzer',desc: 'Detects ZWC, homoglyphs, invisible text, base64', color: 'text-purple-400' },
  statistical_analyzer:{ label: 'Statistical Analyzer',desc: 'Linguistic heuristics and instruction density', color: 'text-yellow-400' },
  ml_classifier:      { label: 'ML Classifier',     desc: 'sklearn TF-IDF / zero-shot BART classifier', color: 'text-green-400' },
};

export default function Settings() {
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [lowThresh, setLowThresh] = useState(0.2);
  const [highThresh, setHighThresh] = useState(0.55);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState('');
  const [error, setError] = useState('');

  const load = () => {
    getSettings().then(s => {
      setSettings(s);
      setLowThresh(s.low_threshold);
      setHighThresh(s.high_threshold);
    }).catch(() => {
      setError('Could not connect to backend');
    });
  };

  useEffect(() => { load(); }, []);

  const handleSaveThresholds = async () => {
    if (lowThresh >= highThresh) {
      setError('Low threshold must be less than high threshold');
      return;
    }
    setSaving(true);
    setError('');
    try {
      await updateThresholds(lowThresh, highThresh);
      setSaveMsg('Thresholds saved!');
      setTimeout(() => setSaveMsg(''), 2000);
      load();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  const handleToggleLayer = async (layer: string, currentlyEnabled: boolean) => {
    try {
      await toggleLayer(layer, !currentlyEnabled);
      load();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to toggle layer');
    }
  };

  return (
    <div className="p-8 space-y-8 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Settings</h1>
          <p className="text-gray-400 text-sm mt-1">Configure detection thresholds and layer preferences</p>
        </div>
        <button onClick={load} className="btn-secondary">
          <RefreshCw className="w-4 h-4" />
          Reload
        </button>
      </div>

      {error && (
        <div className="p-3 rounded-xl bg-danger-500/10 border border-danger-500/20 text-danger-400 text-sm">
          {error}
        </div>
      )}

      <div className="grid grid-cols-2 gap-6">
        {/* Threshold sliders */}
        <div className="card space-y-6">
          <div className="flex items-center gap-2">
            <SettingsIcon className="w-4 h-4 text-brand-400" />
            <h2 className="font-semibold text-white text-sm">Risk Thresholds</h2>
          </div>

          <div className="p-4 rounded-xl bg-white/3 border border-white/5 text-xs text-gray-400 flex items-start gap-2">
            <Info className="w-3 h-3 text-brand-400 flex-shrink-0 mt-0.5" />
            <p>
              Score &lt; low → <span className="text-success-400 font-semibold">LOW / Pass Through</span><br/>
              Low ≤ score &lt; high → <span className="text-warning-400 font-semibold">MEDIUM / Sanitize</span><br/>
              Score ≥ high → <span className="text-danger-400 font-semibold">HIGH / Block</span>
            </p>
          </div>

          <div className="space-y-6">
            <div>
              <div className="flex items-center justify-between mb-3">
                <label className="text-sm text-gray-300">Low Threshold</label>
                <span className="text-sm font-mono text-success-400 bg-success-500/10 px-2 py-0.5 rounded-lg">
                  {(lowThresh * 100).toFixed(0)}%
                </span>
              </div>
              <input
                id="low-threshold"
                type="range"
                min="0"
                max="0.99"
                step="0.01"
                value={lowThresh}
                onChange={e => setLowThresh(parseFloat(e.target.value))}
                className="w-full accent-success-500 cursor-pointer"
              />
              <div className="flex justify-between text-xs text-gray-600 mt-1">
                <span>0%</span><span>100%</span>
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-3">
                <label className="text-sm text-gray-300">High Threshold</label>
                <span className="text-sm font-mono text-danger-400 bg-danger-500/10 px-2 py-0.5 rounded-lg">
                  {(highThresh * 100).toFixed(0)}%
                </span>
              </div>
              <input
                id="high-threshold"
                type="range"
                min="0.01"
                max="1"
                step="0.01"
                value={highThresh}
                onChange={e => setHighThresh(parseFloat(e.target.value))}
                className="w-full accent-danger-500 cursor-pointer"
              />
              <div className="flex justify-between text-xs text-gray-600 mt-1">
                <span>0%</span><span>100%</span>
              </div>
            </div>
          </div>

          {/* Visual threshold indicator */}
          <div className="space-y-2">
            <div className="text-xs text-gray-500 mb-2">Threshold visualization</div>
            <div className="h-4 rounded-full relative overflow-hidden" style={{
              background: `linear-gradient(to right, 
                #22c55e 0%, #22c55e ${lowThresh * 100}%, 
                #f59e0b ${lowThresh * 100}%, #f59e0b ${highThresh * 100}%, 
                #ef4444 ${highThresh * 100}%, #ef4444 100%)`
            }}>
              <div
                className="absolute top-0 bottom-0 w-0.5 bg-white/80"
                style={{ left: `${lowThresh * 100}%` }}
              />
              <div
                className="absolute top-0 bottom-0 w-0.5 bg-white/80"
                style={{ left: `${highThresh * 100}%` }}
              />
            </div>
            <div className="flex justify-between text-xs text-gray-500">
              <span className="text-success-400">LOW</span>
              <span className="text-warning-400">MEDIUM</span>
              <span className="text-danger-400">HIGH</span>
            </div>
          </div>

          <button
            id="save-thresholds"
            onClick={handleSaveThresholds}
            disabled={saving}
            className="btn-primary w-full justify-center disabled:opacity-50"
          >
            {saving ? (
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            {saveMsg || 'Save Thresholds'}
          </button>
        </div>

        {/* Layer toggles */}
        <div className="card space-y-4">
          <div className="flex items-center gap-2">
            <SettingsIcon className="w-4 h-4 text-brand-400" />
            <h2 className="font-semibold text-white text-sm">Detection Layers</h2>
          </div>

          <p className="text-xs text-gray-500">
            Toggle individual layers on or off. Disabling a layer reduces detection coverage.
            At least one layer must remain enabled.
          </p>

          {settings ? (
            <div className="space-y-3">
              {Object.entries(LAYER_INFO).map(([key, info]) => {
                const isEnabled = settings.enabled_layers.includes(key);
                const weight = settings.layer_weights[key] ?? 0;
                return (
                  <div
                    key={key}
                    className={`p-4 rounded-xl border transition-all ${
                      isEnabled
                        ? 'border-white/8 bg-white/3'
                        : 'border-white/4 bg-white/1 opacity-50'
                    }`}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <span className={`text-sm font-semibold ${info.color}`}>{info.label}</span>
                          <span className="text-xs text-gray-500 font-mono">
                            weight: {(weight * 100).toFixed(0)}%
                          </span>
                        </div>
                        <p className="text-xs text-gray-500">{info.desc}</p>
                      </div>
                      <button
                        onClick={() => handleToggleLayer(key, isEnabled)}
                        className="ml-4 flex-shrink-0"
                        title={isEnabled ? 'Disable' : 'Enable'}
                      >
                        {isEnabled ? (
                          <ToggleRight className={`w-7 h-7 ${info.color}`} />
                        ) : (
                          <ToggleLeft className="w-7 h-7 text-gray-600" />
                        )}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="space-y-3">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="h-20 rounded-xl bg-white/3 animate-pulse" />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Current config */}
      {settings && (
        <div className="card">
          <h2 className="font-semibold text-white text-sm mb-4">Current Configuration</h2>
          <pre className="code-block text-xs">
            {JSON.stringify(settings, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
