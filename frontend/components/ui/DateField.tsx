'use client';

import { useState } from 'react';

export function DateField({
  label,
  name,
  defaultValue,
  className = 'input w-36',
  required,
}: {
  label: string;
  name?: string;
  defaultValue?: string;
  className?: string;
  required?: boolean;
}) {
  const [value, setValue] = useState(defaultValue || '');

  return (
    <label className="flex flex-col gap-1.5 text-xs text-text-muted">
      <span>{label}</span>
      <div className="date-field">
        {!value && <span className="date-overlay">年/月/日</span>}
        <input
          type="date"
          name={name}
          className={className}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          required={required}
          style={value ? {} : { color: 'transparent' }}
        />
      </div>
    </label>
  );
}
