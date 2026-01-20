'use client';

import { useState, useRef, useEffect } from 'react';

// Available Gemini models
const AVAILABLE_MODELS = [
  {
    id: 'gemini-3-pro-preview',
    name: 'Gemini 3 Pro',
    description: 'Latest preview with thinking capabilities',
    badge: 'Preview',
  },
  {
    id: 'gemini-2.5-pro-preview-06-05',
    name: 'Gemini 2.5 Pro',
    description: 'High performance reasoning model',
    badge: null,
  },
  {
    id: 'gemini-2.0-flash',
    name: 'Gemini 2.0 Flash',
    description: 'Fast and efficient responses',
    badge: 'Fast',
  },
  {
    id: 'gemini-2.0-flash-lite',
    name: 'Gemini 2.0 Flash Lite',
    description: 'Lightweight for simple tasks',
    badge: 'Lite',
  },
];

const STORAGE_KEY = 'deepresearcher-selected-model';

interface ModelSelectorProps {
  onModelChange?: (model: string) => void;
  className?: string;
}

export function ModelSelector({ onModelChange, className = '' }: ModelSelectorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [selectedModel, setSelectedModel] = useState<string>(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem(STORAGE_KEY);
      return saved || AVAILABLE_MODELS[0].id;
    }
    return AVAILABLE_MODELS[0].id;
  });
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSelectModel = (modelId: string) => {
    setSelectedModel(modelId);
    localStorage.setItem(STORAGE_KEY, modelId);
    setIsOpen(false);
    onModelChange?.(modelId);
  };

  const currentModel = AVAILABLE_MODELS.find((m) => m.id === selectedModel) || AVAILABLE_MODELS[0];

  return (
    <div className={`relative ${className}`} ref={dropdownRef}>
      {/* Trigger Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs font-medium text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
      >
        <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
        <span className="hidden sm:inline">{currentModel.name}</span>
        <span className="sm:hidden">{currentModel.name.split(' ').slice(-1)[0]}</span>
        <svg
          className={`w-3 h-3 transition-transform ${isOpen ? 'rotate-180' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <div className="absolute bottom-full right-0 mb-2 w-72 bg-white dark:bg-slate-800 rounded-xl shadow-xl border border-slate-200 dark:border-slate-700 overflow-hidden z-50">
          <div className="px-3 py-2 border-b border-slate-200 dark:border-slate-700">
            <p className="text-xs font-semibold text-slate-900 dark:text-white">
              AI Model
            </p>
            <p className="text-[10px] text-slate-500 dark:text-slate-400">
              Select the model for conversations
            </p>
          </div>
          <div className="py-1 max-h-64 overflow-y-auto">
            {AVAILABLE_MODELS.map((model) => (
              <button
                key={model.id}
                onClick={() => handleSelectModel(model.id)}
                className={`w-full flex items-start gap-3 px-3 py-2.5 text-left hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors ${
                  selectedModel === model.id
                    ? 'bg-primary-50 dark:bg-primary-900/20'
                    : ''
                }`}
              >
                {/* Selection indicator */}
                <div className="shrink-0 mt-0.5">
                  {selectedModel === model.id ? (
                    <div className="w-4 h-4 rounded-full bg-primary-600 flex items-center justify-center">
                      <svg
                        className="w-2.5 h-2.5 text-white"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                        strokeWidth={3}
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                    </div>
                  ) : (
                    <div className="w-4 h-4 rounded-full border-2 border-slate-300 dark:border-slate-600" />
                  )}
                </div>

                {/* Model info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span
                      className={`text-sm font-medium ${
                        selectedModel === model.id
                          ? 'text-primary-700 dark:text-primary-300'
                          : 'text-slate-900 dark:text-white'
                      }`}
                    >
                      {model.name}
                    </span>
                    {model.badge && (
                      <span
                        className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                          model.badge === 'Preview'
                            ? 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300'
                            : model.badge === 'Fast'
                            ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
                            : 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300'
                        }`}
                      >
                        {model.badge}
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
                    {model.description}
                  </p>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// Helper to get the currently selected model
export function getSelectedModel(): string {
  if (typeof window !== 'undefined') {
    return localStorage.getItem(STORAGE_KEY) || AVAILABLE_MODELS[0].id;
  }
  return AVAILABLE_MODELS[0].id;
}

export { AVAILABLE_MODELS };
