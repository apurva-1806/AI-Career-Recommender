// Indian amounts read in lakhs and crores (₹6L, ₹1.2Cr); other currencies use K and M.
export function formatSalary(amount, currency = 'INR') {
  try {
    return new Intl.NumberFormat(currency === 'INR' ? 'en-IN' : 'en-US', {
      style: 'currency',
      currency,
      notation: 'compact',
      minimumFractionDigits: 0,
      maximumFractionDigits: 1,
    }).format(amount)
  } catch {
    return `${currency} ${Math.round(amount).toLocaleString()}`
  }
}

/**
 * One segment per core skill: filled when the skill is on the profile, hollow when it is still to build.
 */
export function SkillStrip({ matched, missing, onDark = false }) {
  const total = matched.length + missing.length
  return (
    <div
      className="flex gap-1"
      role="img"
      aria-label={`${matched.length} of ${total} core skills covered`}
    >
      {matched.map((skill) => (
        <span key={skill} title={skill} className={`h-2 flex-1 rounded-full ${onDark ? 'bg-white' : 'bg-brand-light'}`} />
      ))}
      {missing.map((skill) => (
        <span
          key={skill}
          title={`To build: ${skill}`}
          className={`h-2 flex-1 rounded-full border ${onDark ? 'border-white/40' : 'border-amber/50 bg-amber/15'}`}
        />
      ))}
    </div>
  )
}

export default function CareerCard({ recommendation, selected, onSelect }) {
  const { career, rank, match_score: score, matched_skills: matched, missing_skills: missing } = recommendation
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={`flex h-full w-full flex-col rounded-2xl border p-4 text-left transition-colors ${
        selected
          ? 'border-brand-light/60 bg-gradient-to-br from-brand to-[#2343C4] text-white shadow-glow'
          : 'border-edge bg-panel hover:border-brand'
      }`}
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className={`text-sm font-medium ${selected ? 'text-white/70' : 'text-fog/55'}`}>
          {rank === 1 ? 'Best match' : `Match ${rank}`}
        </span>
        <span className="font-display text-3xl font-bold tabular-nums leading-none">
          {Math.round(score)}
          <span className={`ml-0.5 text-base font-medium ${selected ? 'text-white/80' : 'text-fog/50'}`}>%</span>
        </span>
      </div>

      <h3 className="mt-3 text-lg font-bold leading-snug">{career.title}</h3>
      <p className={`text-sm ${selected ? 'text-white/70' : 'text-fog/60'}`}>{career.industry}</p>

      <div className="mt-auto pt-5">
        <SkillStrip matched={matched} missing={missing} onDark={selected} />
        <p className={`mt-2 text-sm ${selected ? 'text-white/80' : 'text-fog/70'}`}>
          {matched.length} of {matched.length + missing.length} core skills
        </p>
        <p className={`mt-0.5 text-sm ${selected ? 'text-white/60' : 'text-fog/50'}`}>
          {formatSalary(career.salary.min, career.salary.currency)} to {formatSalary(career.salary.max, career.salary.currency)}
        </p>
      </div>
    </button>
  )
}
