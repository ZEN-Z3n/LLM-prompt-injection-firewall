// react 'react';

type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH';
type Action = 'PASS_THROUGH' | 'SANITIZE' | 'BLOCK';

interface RiskBadgeProps {
  level: RiskLevel;
  className?: string;
}

export function RiskBadge({ level, className = '' }: RiskBadgeProps) {
  const classes: Record<RiskLevel, string> = {
    HIGH: 'badge-high',
    MEDIUM: 'badge-medium',
    LOW: 'badge-low',
  };
  const dots: Record<RiskLevel, string> = {
    HIGH: 'bg-danger-400',
    MEDIUM: 'bg-warning-400',
    LOW: 'bg-success-400',
  };
  return (
    <span className={`${classes[level]} ${className}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${dots[level]}`} />
      {level}
    </span>
  );
}

interface ActionBadgeProps {
  action: Action;
}

export function ActionBadge({ action }: ActionBadgeProps) {
  const config: Record<Action, { label: string; cls: string }> = {
    BLOCK: { label: 'Blocked', cls: 'bg-danger-500/15 text-danger-400 border-danger-500/20' },
    SANITIZE: { label: 'Sanitized', cls: 'bg-warning-500/15 text-warning-400 border-warning-500/20' },
    PASS_THROUGH: { label: 'Passed', cls: 'bg-success-500/15 text-success-400 border-success-500/20' },
  };
  const { label, cls } = config[action];
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-lg text-xs font-medium border ${cls}`}>
      {label}
    </span>
  );
}

interface ScoreBarProps {
  score: number;  // 0-1
  showLabel?: boolean;
}

export function ScoreBar({ score, showLabel = true }: ScoreBarProps) {
  const pct = Math.round(score * 100);
  const color =
    score >= 0.55 ? 'bg-gradient-to-r from-danger-600 to-danger-400' :
    score >= 0.2  ? 'bg-gradient-to-r from-warning-600 to-warning-400' :
                    'bg-gradient-to-r from-success-600 to-success-400';
  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 score-bar">
        <div
          className={`score-bar-fill ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      {showLabel && (
        <span className="text-xs font-mono text-gray-400 w-8 text-right">{pct}%</span>
      )}
    </div>
  );
}

interface LayerContributionBarProps {
  contributions: Record<string, number>;
}

export function LayerContributions({ contributions }: LayerContributionBarProps) {
  const layerColors: Record<string, string> = {
    pattern_matcher: 'bg-blue-500',
    structural_analyzer: 'bg-purple-500',
    statistical_analyzer: 'bg-yellow-500',
    ml_classifier: 'bg-green-500',
  };
  const layerLabels: Record<string, string> = {
    pattern_matcher: 'Pattern',
    structural_analyzer: 'Structural',
    statistical_analyzer: 'Statistical',
    ml_classifier: 'ML',
  };

  return (
    <div className="space-y-2">
      {Object.entries(contributions).map(([layer, value]) => (
        <div key={layer} className="flex items-center gap-3">
          <span className="text-xs text-gray-500 w-20 flex-shrink-0">{layerLabels[layer] || layer}</span>
          <div className="flex-1 h-1.5 bg-white/5 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full ${layerColors[layer] || 'bg-gray-500'} transition-all duration-700`}
              style={{ width: `${Math.round(value * 100)}%` }}
            />
          </div>
          <span className="text-xs font-mono text-gray-400 w-10 text-right">
            {(value * 100).toFixed(1)}%
          </span>
        </div>
      ))}
    </div>
  );
}
