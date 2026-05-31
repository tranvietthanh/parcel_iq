"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useApiClient } from "@/lib/api";
import type { SearchSuggestion } from "@/types";
import Spinner from "@/components/ui/Spinner";

type SearchOmniboxProps = {
  onSelect: (result: SearchSuggestion) => void;
};

const DEBOUNCE_MS = 300;
const SEARCH_TYPE_PRIORITY: Record<string, number> = {
  SUBURB: 0,
  SCHOOL_CATCHMENT: 1,
  ADDRESS: 2,
};

/**
 * Unified search input: address, suburb, postcode, LGA name, school name.
 */
export default function SearchOmnibox({ onSelect }: SearchOmniboxProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchSuggestion[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const api = useApiClient();

  const search = useCallback(
    async (q: string) => {
      if (q.length < 2) {
        setResults([]);
        setIsOpen(false);
        return;
      }
      setIsLoading(true);
      try {
        const response = await api.get<{ suggestions: SearchSuggestion[] }>(
          `/api/search?q=${encodeURIComponent(q)}`,
        );
        const suggestions = (response.suggestions || [])
          .map((suggestion, index) => ({ suggestion, index }))
          .sort((a, b) => {
            const aPriority = SEARCH_TYPE_PRIORITY[a.suggestion.type] ?? 99;
            const bPriority = SEARCH_TYPE_PRIORITY[b.suggestion.type] ?? 99;

            if (aPriority !== bPriority) {
              return aPriority - bPriority;
            }

            // Preserve backend-provided relevance order within the same type.
            return a.index - b.index;
          })
          .map((entry) => entry.suggestion);
        setResults(suggestions);
        setIsOpen(suggestions.length > 0);
      } catch {
        setResults([]);
      } finally {
        setIsLoading(false);
      }
    },
    [api],
  );

  const handleChange = (value: string) => {
    setQuery(value);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => search(value), DEBOUNCE_MS);
  };

  const handleSelect = (result: SearchSuggestion) => {
    setQuery(result.label);
    setIsOpen(false);
    onSelect(result);
  };

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  return (
    <div className="relative w-full max-w-xl">
      <div className="relative">
        <input
          type="text"
          value={query}
          onChange={(e) => handleChange(e.target.value)}
          placeholder="Search address, suburb, postcode, LGA, school..."
          className="w-full rounded-lg border border-zinc-300 bg-white px-4 py-2.5 pr-10 text-sm shadow-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-200 dark:border-zinc-600 dark:bg-zinc-800 dark:text-white dark:focus:ring-blue-800"
          aria-label="Search properties"
          role="combobox"
          aria-expanded={isOpen}
          aria-autocomplete="list"
        />
        {isLoading && (
          <div className="absolute right-3 top-1/2 -translate-y-1/2">
            <Spinner size="sm" />
          </div>
        )}
      </div>

      {isOpen && results.length > 0 && (
        <ul
          role="listbox"
          className="absolute z-50 mt-1 max-h-60 w-full overflow-auto rounded-lg border border-zinc-200 bg-white shadow-lg dark:border-zinc-700 dark:bg-zinc-800"
        >
          {results.map((result, index) => {
            const key = result.property_id || result.zone_id || `${index}`;
            return (
              <li
                key={key}
                role="option"
                aria-selected={false}
                className="cursor-pointer px-4 py-2.5 text-sm hover:bg-blue-50 dark:hover:bg-zinc-700"
                onClick={() => handleSelect(result)}
              >
                <span className="mr-2 inline-block rounded bg-zinc-100 px-1.5 py-0.5 text-xs font-medium text-zinc-600 dark:bg-zinc-700 dark:text-zinc-300">
                  {result.type}
                </span>
                {result.label}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
