import { ReactElement } from "react";

type JsonViewerProps = {
  data: unknown;
  title?: string;
};

export function JsonViewer({ data, title }: JsonViewerProps) {
  // Parse if string, otherwise use as-is
  let parsed: unknown;
  try {
    parsed = typeof data === "string" ? JSON.parse(data) : data;
  } catch {
    parsed = data;
  }

  const jsonString = JSON.stringify(parsed, null, 2);

  return (
    <div>
      {title && (
        <h3 className="text-lg font-semibold text-white mb-2">{title}</h3>
      )}
      <div className="bg-gray-900 rounded-lg border border-gray-700 overflow-hidden">
        <pre className="p-4 overflow-x-auto text-sm leading-relaxed">
          <code className="language-json">{highlightJson(jsonString)}</code>
        </pre>
      </div>
    </div>
  );
}

function highlightJson(json: string) {
  // Simple syntax highlighting using React elements
  const tokens: ReactElement[] = [];
  let buffer = "";
  let inString = false;
  let escapeNext = false;
  let tokenIndex = 0;

  const flushBuffer = (className?: string) => {
    if (buffer) {
      tokens.push(
        <span key={tokenIndex++} className={className}>
          {buffer}
        </span>
      );
      buffer = "";
    }
  };

  for (let i = 0; i < json.length; i++) {
    const char = json[i];

    if (escapeNext) {
      buffer += char;
      escapeNext = false;
      continue;
    }

    if (char === "\\" && inString) {
      buffer += char;
      escapeNext = true;
      continue;
    }

    if (char === '"') {
      if (inString) {
        buffer += char;
        flushBuffer("text-green-400");
        inString = false;
      } else {
        flushBuffer();
        buffer += char;
        inString = true;
      }
      continue;
    }

    if (inString) {
      buffer += char;
      continue;
    }

    // Handle property names (keys)
    if (char === ":") {
      // Look back to find the key
      const keyMatch = buffer.match(/"([^"]+)"$/);
      if (keyMatch) {
        const beforeKey = buffer.substring(0, buffer.length - keyMatch[0].length);
        const key = keyMatch[0];
        if (beforeKey) {
          tokens.push(
            <span key={tokenIndex++} className="text-gray-500">
              {beforeKey}
            </span>
          );
        }
        tokens.push(
          <span key={tokenIndex++} className="text-blue-400">
            {key}
          </span>
        );
        buffer = char;
        flushBuffer("text-gray-500");
        continue;
      }
    }

    // Numbers
    if (/\d/.test(char) && /[\s,\[\{:]$/.test(buffer)) {
      flushBuffer("text-gray-500");
      buffer = char;
      // Continue collecting the number
      while (i + 1 < json.length && /[\d.eE+-]/.test(json[i + 1])) {
        i++;
        buffer += json[i];
      }
      flushBuffer("text-orange-400");
      continue;
    }

    // Booleans and null
    if (
      (char === "t" && json.substring(i, i + 4) === "true") ||
      (char === "f" && json.substring(i, i + 5) === "false") ||
      (char === "n" && json.substring(i, i + 4) === "null")
    ) {
      flushBuffer("text-gray-500");
      const keyword =
        char === "t" ? "true" : char === "f" ? "false" : "null";
      tokens.push(
        <span key={tokenIndex++} className="text-purple-400">
          {keyword}
        </span>
      );
      i += keyword.length - 1;
      continue;
    }

    // Brackets and punctuation
    if (/[{}\[\],:]/.test(char)) {
      flushBuffer();
      buffer = char;
      flushBuffer("text-gray-500");
      continue;
    }

    buffer += char;
  }

  flushBuffer("text-gray-500");
  return tokens;
}
