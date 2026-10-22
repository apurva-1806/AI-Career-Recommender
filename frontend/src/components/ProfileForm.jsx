import { useRef, useState } from 'react'
import { parseResume } from '../api.js'
import SkillInput from './SkillInput.jsx'

const FALLBACK_EDUCATION = [
  { value: 'high_school', label: 'High school' },
  { value: 'associate', label: 'Associate degree or diploma' },
  { value: 'bachelor', label: "Bachelor's degree" },
  { value: 'master', label: "Master's degree" },
  { value: 'doctorate', label: 'Doctorate' },
]

const STEPS = [
  { id: 'skills', title: 'Technical skills' },
  { id: 'strengths', title: 'Strengths and interests' },
  { id: 'background', title: 'Education and experience' },
  { id: 'bio', title: 'Resume or bio' },
]

const plural = (count, word) => `${count} ${word}${count === 1 ? '' : 's'}`

export default function ProfileForm({ profile, onChange, meta, onSubmit, loading, error }) {
  const [step, setStep] = useState(0)
  const [upload, setUpload] = useState({ status: 'idle', message: '', found: [] })
  const fileRef = useRef(null)

  const set = (patch) => onChange({ ...profile, ...patch })
  const education = meta?.education_levels?.length ? meta.education_levels : FALLBACK_EDUCATION
  const technical = (meta?.technical_skills || []).map((s) => s.name)
  const soft = (meta?.soft_skills || []).map((s) => s.name)
  const educationLabel = education.find((e) => e.value === profile.education_level)?.label || ''

  const hasSignal =
    profile.technical_skills.length + profile.soft_skills.length + profile.interests.length > 0 ||
    profile.bio.trim().length >= 30

  const summaries = [
    profile.technical_skills.length ? plural(profile.technical_skills.length, 'skill') : 'None added yet',
    profile.soft_skills.length + profile.interests.length
      ? `${plural(profile.soft_skills.length, 'strength')}, ${plural(profile.interests.length, 'interest')}`
      : 'None added yet',
    `${educationLabel}, ${plural(Number(profile.years_experience) || 0, 'year')}`,
    profile.bio.trim() ? `${profile.bio.trim().split(/\s+/).length} words` : 'Optional',
  ]

  async function onFile(event) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    setUpload({ status: 'working', message: `Reading ${file.name}`, found: [] })
    try {
      const parsed = await parseResume(file)
      set({ bio: parsed.text })
      // Only offer skills that are not on the profile already.
      const listed = [...profile.technical_skills, ...profile.soft_skills, ...profile.interests].map((s) => s.toLowerCase())
      const isNew = (skill) => !listed.includes(skill.toLowerCase())
      const found = parsed.detected_technical_skills.filter(isNew)
      const foundSoft = parsed.detected_soft_skills.filter(isNew)
      setUpload({
        status: 'done',
        message: `Loaded ${file.name} into the box above${parsed.truncated ? ' (long file: the first 20,000 characters were kept)' : ''}.`,
        found,
        foundSoft,
        total: found.length + foundSoft.length,
      })
    } catch (err) {
      setUpload({ status: 'error', message: err.message, found: [] })
    }
  }

  function addDetected() {
    const merge = (current, extra) => [
      ...current,
      ...extra.filter((s) => !current.some((c) => c.toLowerCase() === s.toLowerCase())),
    ]
    set({
      technical_skills: merge(profile.technical_skills, upload.found || []),
      soft_skills: merge(profile.soft_skills, upload.foundSoft || []),
    })
    setUpload({ ...upload, total: 0, message: 'Added to your skills.' })
  }

  const isLast = step === STEPS.length - 1

  return (
    <div className="grid gap-8 lg:grid-cols-[19rem_1fr] lg:gap-14">
      <aside>
        <h1 className="text-3xl font-bold leading-tight tracking-tight sm:text-4xl">
          Tell us what you can do. See where it leads.
        </h1>
        <p className="mt-4 max-w-md text-[15px] leading-relaxed text-fog/70">
          Four short steps. Your profile is compared with {meta?.engine?.careers_indexed || 'more than 50'} career
          paths and the five closest are returned with the skills to build for each.
        </p>

        <ol className="mt-8 hidden space-y-1 lg:block">
          {STEPS.map((item, index) => (
            <li key={item.id}>
              <button
                type="button"
                onClick={() => setStep(index)}
                aria-current={index === step ? 'step' : undefined}
                className={`flex w-full items-start gap-3 rounded-xl px-3 py-2.5 text-left transition-colors ${
                  index === step ? 'bg-panel shadow-lift' : 'hover:bg-panel/60'
                }`}
              >
                <span
                  className={`mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full text-xs font-semibold ${
                    index === step ? 'bg-brand text-white' : 'border border-edge bg-white/5 text-fog/60'
                  }`}
                >
                  {index + 1}
                </span>
                <span>
                  <span className="block text-[15px] font-semibold">{item.title}</span>
                  <span className="block text-sm text-fog/55">{summaries[index]}</span>
                </span>
              </button>
            </li>
          ))}
        </ol>
      </aside>

      <form
        className="rounded-3xl border border-edge bg-panel p-5 shadow-lift sm:p-8"
        onSubmit={(event) => {
          event.preventDefault()
          if (isLast) onSubmit()
          else setStep(step + 1)
        }}
      >
        <div className="mb-6 flex items-center gap-3 lg:hidden">
          <div className="flex flex-1 gap-1.5" aria-hidden="true">
            {STEPS.map((item, index) => (
              <span key={item.id} className={`h-1.5 flex-1 rounded-full ${index <= step ? 'bg-brand' : 'bg-white/10'}`} />
            ))}
          </div>
          <span className="text-sm text-fog/60">
            Step {step + 1} of {STEPS.length}
          </span>
        </div>

        <h2 className="text-2xl font-bold tracking-tight">{STEPS[step].title}</h2>

        <div className="mt-5 min-h-[19rem] space-y-7">
          {step === 0 && (
            <SkillInput
              label="What tools, languages and methods do you work with?"
              hint="Type a skill and press Enter. Anything is accepted, not only the suggestions."
              values={profile.technical_skills}
              onChange={(technical_skills) => set({ technical_skills })}
              suggestions={technical}
              quickAdd={technical.slice(0, 14)}
              placeholder="Python, React, SQL, Figma"
            />
          )}

          {step === 1 && (
            <>
              <SkillInput
                label="Soft skills"
                hint="How you work with people and problems."
                values={profile.soft_skills}
                onChange={(soft_skills) => set({ soft_skills })}
                suggestions={soft}
                quickAdd={['Leadership', 'Problem-Solving', 'Communication', 'Creativity', 'Empathy', 'Attention to Detail']}
                placeholder="Leadership, problem-solving"
              />
              <SkillInput
                label="Interests"
                hint="Subjects or kinds of work you would like more of."
                values={profile.interests}
                onChange={(interests) => set({ interests })}
                suggestions={soft}
                quickAdd={['AI Research', 'Creative Writing', 'Design', 'Finance', 'Healthcare', 'Teaching', 'Sustainability']}
                placeholder="AI research, creative writing"
              />
            </>
          )}

          {step === 2 && (
            <>
              <fieldset>
                <legend className="text-[15px] font-semibold">Highest level of education</legend>
                <div className="mt-2 grid gap-2 sm:grid-cols-2">
                  {education.map((level) => {
                    const checked = profile.education_level === level.value
                    return (
                      <label
                        key={level.value}
                        className={`flex cursor-pointer items-center gap-3 rounded-xl border px-3.5 py-3 text-[15px] ${
                          checked ? 'border-brand bg-brand/15 font-semibold' : 'border-edge hover:border-brand/50'
                        }`}
                      >
                        <input
                          type="radio"
                          name="education"
                          value={level.value}
                          checked={checked}
                          onChange={() => set({ education_level: level.value })}
                          className="h-4 w-4 accent-[#4F8CFF]"
                        />
                        {level.label}
                      </label>
                    )
                  })}
                </div>
              </fieldset>

              <div>
                <label htmlFor="years" className="block text-[15px] font-semibold">
                  Years of professional experience
                </label>
                <p className="mt-0.5 text-sm text-fog/60">Count internships and freelance work. Enter 0 if you are starting out.</p>
                <div className="mt-3 flex items-center gap-4">
                  <input
                    id="years"
                    type="number"
                    min="0"
                    max="60"
                    step="0.5"
                    inputMode="decimal"
                    value={profile.years_experience}
                    onChange={(e) => set({ years_experience: e.target.value === '' ? '' : Math.min(60, Math.max(0, Number(e.target.value))) })}
                    className="field w-24 text-center text-lg font-semibold"
                  />
                  <input
                    type="range"
                    min="0"
                    max="25"
                    step="1"
                    aria-label="Years of professional experience"
                    value={Math.min(25, Number(profile.years_experience) || 0)}
                    onChange={(e) => set({ years_experience: Number(e.target.value) })}
                    className="h-2 flex-1 cursor-pointer accent-[#4F8CFF]"
                  />
                </div>
              </div>
            </>
          )}

          {step === 3 && (
            <div>
              <label htmlFor="bio" className="block text-[15px] font-semibold">
                Paste a resume or a short professional bio
              </label>
              <p className="mt-0.5 text-sm text-fog/60">
                Optional. The text is matched against career descriptions and scanned for skills you did not list.
              </p>
              <textarea
                id="bio"
                rows={8}
                maxLength={20000}
                value={profile.bio}
                onChange={(e) => set({ bio: e.target.value })}
                placeholder="For example: Analyst with three years in retail banking. I build SQL reports, automate spreadsheets with Python and present findings to branch managers."
                className="field mt-2 resize-y leading-relaxed"
              />
              <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <input ref={fileRef} type="file" accept=".pdf,.docx,.txt,.md" onChange={onFile} className="sr-only" id="resume-file" />
                  <button type="button" className="btn-quiet" onClick={() => fileRef.current?.click()} disabled={upload.status === 'working'}>
                    {upload.status === 'working' ? 'Reading file' : 'Upload a resume'}
                  </button>
                  <span className="text-sm text-fog/55">PDF, DOCX, TXT or MD, up to 5 MB</span>
                </div>
                <span className="text-sm tabular-nums text-fog/50">{profile.bio.length.toLocaleString()} / 20,000</span>
              </div>

              {upload.message && (
                <div
                  role={upload.status === 'error' ? 'alert' : 'status'}
                  className={`mt-3 rounded-xl px-3.5 py-3 text-sm ${
                    upload.status === 'error' ? 'bg-red-500/10 text-red-300' : 'bg-panel2 text-fog/80'
                  }`}
                >
                  <p>{upload.message}</p>
                  {upload.status === 'done' && upload.total > 0 && (
                    <div className="mt-2">
                      <p className="mb-1.5">Found {plural(upload.total, 'skill')} you have not listed:</p>
                      <div className="flex flex-wrap gap-1.5">
                        {[...(upload.found || []), ...(upload.foundSoft || [])].map((skill) => (
                          <span key={skill} className="chip-plain">{skill}</span>
                        ))}
                      </div>
                      <button type="button" className="btn-quiet mt-3" onClick={addDetected}>
                        Add these to my skills
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {isLast && !hasSignal && (
          <p className="mt-4 text-sm text-fog/70">
            Add at least one skill or interest, or a bio of 30 characters or more, to get recommendations.
          </p>
        )}
        {error && (
          <p role="alert" className="mt-4 rounded-xl bg-red-500/10 px-3.5 py-3 text-sm text-red-300">
            {error}
          </p>
        )}

        <div className="mt-6 flex items-center justify-between gap-3 border-t border-edge pt-5">
          <button type="button" className="btn-quiet" onClick={() => setStep(step - 1)} disabled={step === 0}>
            Back
          </button>
          {isLast ? (
            <button type="submit" className="btn-primary px-7" disabled={loading || !hasSignal}>
              {loading ? 'Finding careers' : 'Find my careers'}
            </button>
          ) : (
            <button type="submit" className="btn-primary px-7">
              Continue
            </button>
          )}
        </div>
      </form>
    </div>
  )
}
