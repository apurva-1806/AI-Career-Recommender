import { useId, useMemo, useRef, useState } from 'react'

const sameSkill = (a, b) => a.trim().toLowerCase() === b.trim().toLowerCase()

/**
 * Tag input with type-ahead suggestions.
 * Enter or comma adds the typed text; Backspace on an empty field removes the last tag.
 */
export default function SkillInput({ label, hint, values, onChange, suggestions = [], quickAdd = [], placeholder }) {
  const inputId = useId()
  const listId = useId()
  const inputRef = useRef(null)
  const [text, setText] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)

  const matches = useMemo(() => {
    const query = text.trim().toLowerCase()
    if (!query) return []
    const available = suggestions.filter((s) => !values.some((v) => sameSkill(v, s)))
    const starts = available.filter((s) => s.toLowerCase().startsWith(query))
    const contains = available.filter((s) => !s.toLowerCase().startsWith(query) && s.toLowerCase().includes(query))
    return [...starts, ...contains].slice(0, 7)
  }, [text, suggestions, values])

  function add(raw) {
    const additions = raw
      .split(/[,;\n]/)
      .map((item) => item.trim().replace(/\s+/g, ' '))
      .filter(Boolean)
    if (additions.length) {
      const next = [...values]
      additions.forEach((item) => {
        if (!next.some((v) => sameSkill(v, item))) next.push(item.slice(0, 60))
      })
      onChange(next)
    }
    setText('')
    setOpen(false)
    setActive(0)
  }

  function remove(skill) {
    onChange(values.filter((v) => v !== skill))
    inputRef.current?.focus()
  }

  function onKeyDown(event) {
    if (event.key === 'ArrowDown' && matches.length) {
      event.preventDefault()
      setOpen(true)
      setActive((i) => (i + 1) % matches.length)
    } else if (event.key === 'ArrowUp' && matches.length) {
      event.preventDefault()
      setActive((i) => (i - 1 + matches.length) % matches.length)
    } else if (event.key === 'Enter' || event.key === ',') {
      if (!text.trim()) return
      event.preventDefault()
      add(open && matches[active] ? matches[active] : text)
    } else if (event.key === 'Backspace' && !text && values.length) {
      onChange(values.slice(0, -1))
    } else if (event.key === 'Escape') {
      setOpen(false)
    }
  }

  const quick = quickAdd.filter((s) => !values.some((v) => sameSkill(v, s))).slice(0, 10)

  return (
    <div>
      <label htmlFor={inputId} className="block text-[15px] font-semibold">
        {label}
      </label>
      {hint && <p className="mt-0.5 text-sm text-fog/60">{hint}</p>}

      <div className="relative mt-2">
        <div
          className="flex min-h-[3rem] flex-wrap items-center gap-1.5 rounded-xl border border-edge bg-panel p-2
                     focus-within:border-brand focus-within:ring-2 focus-within:ring-brand/25"
          onClick={() => inputRef.current?.focus()}
        >
          {values.map((skill) => (
            <span key={skill} className="chip-have">
              {skill}
              <button
                type="button"
                onClick={() => remove(skill)}
                aria-label={`Remove ${skill}`}
                className="-mr-1 grid h-5 w-5 place-items-center rounded-full text-brand-light/70 hover:bg-brand hover:text-white"
              >
                <svg viewBox="0 0 12 12" className="h-2.5 w-2.5" aria-hidden="true">
                  <path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                </svg>
              </button>
            </span>
          ))}
          <input
            id={inputId}
            ref={inputRef}
            value={text}
            onChange={(e) => {
              setText(e.target.value)
              setOpen(true)
              setActive(0)
            }}
            onKeyDown={onKeyDown}
            onBlur={() => setTimeout(() => setOpen(false), 120)}
            onPaste={(e) => {
              const pasted = e.clipboardData.getData('text')
              if (/[,;\n]/.test(pasted)) {
                e.preventDefault()
                add(pasted)
              }
            }}
            placeholder={values.length ? '' : placeholder}
            role="combobox"
            aria-expanded={open && matches.length > 0}
            aria-controls={listId}
            aria-autocomplete="list"
            autoComplete="off"
            className="min-w-[9rem] flex-1 bg-transparent px-1.5 py-1 text-[15px] placeholder:text-fog/40 focus:outline-none focus:ring-0"
            style={{ boxShadow: 'none' }}
          />
        </div>

        {open && matches.length > 0 && (
          <ul
            id={listId}
            role="listbox"
            className="absolute z-20 mt-1 w-full overflow-hidden rounded-xl border border-edge bg-panel py-1 shadow-lift"
          >
            {matches.map((option, index) => (
              <li
                key={option}
                role="option"
                aria-selected={index === active}
                onMouseDown={(e) => {
                  e.preventDefault()
                  add(option)
                }}
                onMouseEnter={() => setActive(index)}
                className={`cursor-pointer px-3.5 py-2 text-[15px] ${index === active ? 'bg-brand/15 text-brand-light' : ''}`}
              >
                {option}
              </li>
            ))}
          </ul>
        )}
      </div>

      {quick.length > 0 && (
        <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
          <span className="mr-1 text-sm text-fog/55">Common picks</span>
          {quick.map((skill) => (
            <button
              key={skill}
              type="button"
              onClick={() => add(skill)}
              className="chip-plain hover:border-brand hover:text-brand-light"
            >
              <span aria-hidden="true" className="text-fog/40">+</span>
              {skill}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
