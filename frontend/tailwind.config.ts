import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: '#ffffff',
          50: '#f9fafb',
          100: '#f3f4f6',
          150: '#e5e7eb',
          200: '#d1d5db',
          300: '#9ca3af',
        },
        brand: {
          50: '#eff6ff',
          100: '#dbeafe',
          200: '#bfdbfe',
          300: '#93c5fd',
          400: '#60a5fa',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
          800: '#1e40af',
          900: '#1e3a8a',
        },
        text: {
          primary: '#18181b',
          secondary: '#4b5563',
          muted: '#9ca3af',
        },
        accent: {
          green: '#10b981',
          red: '#ef4444',
          amber: '#f59e0b',
          blue: '#3b82f6',
        },
      },
      fontFamily: {
        sans: ['Noto Sans SC', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Roboto Mono', 'Menlo', 'Courier New', 'monospace'],
      },
      boxShadow: {
        'border': '0 0 0 1px #e5e7eb',
        'border-hover': '0 0 0 1px #d1d5db',
        'card': '0 4px 20px rgba(0, 0, 0, 0.03)',
        'card-hover': '0 8px 30px rgba(0, 0, 0, 0.06)',
        'elevated': '0 12px 40px rgba(0, 0, 0, 0.08)',
      },
      animation: {
        'fade-in': 'fadeIn 0.3s ease-out',
        'slide-up': 'slideUp 0.3s ease-out',
        'slide-in-right': 'slideInRight 0.2s ease-out',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideInRight: {
          '0%': { opacity: '0', transform: 'translateX(-4px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
      },
    },
  },
  plugins: [],
};

export default config;
