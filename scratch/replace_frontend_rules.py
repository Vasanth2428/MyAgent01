"""Binary-safe replacement of Frontend/Web Project Rules in coding_worker.py"""
import re

filepath = r'src/agents/coding_worker.py'
with open(filepath, 'rb') as f:
    data = f.read()

# Find the section boundaries using regex on bytes
# Start marker: "Frontend/Web Project Rules:"
# End marker: The line ending with "Do not leave the placeholder code in place."
start_marker = b'Frontend/Web Project Rules:'
end_marker = b'Do not leave the placeholder code in place.'

start_idx = data.find(start_marker)
if start_idx == -1:
    print("ERROR: Start marker not found")
    exit(1)

end_idx = data.find(end_marker, start_idx)
if end_idx == -1:
    print("ERROR: End marker not found")
    exit(1)

# Include the end marker in the range
end_idx += len(end_marker)

old_block = data[start_idx:end_idx]
print(f"Found target block at bytes {start_idx}-{end_idx} (length {len(old_block)})")

# Detect line ending used in this section
if b'\r\r\n' in old_block:
    NL = b'\r\r\n'
    print("Detected \\r\\r\\n line endings")
elif b'\r\n' in old_block:
    NL = b'\r\n'
    print("Detected \\r\\n line endings")
else:
    NL = b'\n'
    print("Detected \\n line endings")

new_block_lines = [
    b'Frontend/Web Project Rules (Lovable-Quality Design System):',
    b'- Inspect existing configurations first: Always check `./workspace` for existing configurations (like package.json, vite.config.js, tailwind.config.js) and align your code structure and dependencies with them instead of creating redundant configurations or nested conflicting subprojects.',
    b'- Creating new pages/forms/subprojects: When asked to create a new page, form, or UI module, create a new subdirectory under `./workspace/` (e.g., `./workspace/dashboard/`). Do NOT pollute the root directory.',
    b'- Use scaffold_react_app to bootstrap new projects: This generates a Lovable-quality React+TypeScript+Vite+Tailwind CSS+shadcn/ui scaffold with a complete design system (HSL color tokens, dark/light mode CSS variables, cn() utility, CVA-powered Button component, Google Fonts Inter, Lucide React icons).',
    b'- Standard React/TypeScript Structure inside subdirectories: Any newly created subdirectory must contain:',
    b'  1. A local `package.json` with React, Tailwind CSS, shadcn/ui deps (clsx, tailwind-merge, class-variance-authority, lucide-react, react-router-dom).',
    b'  2. A `tailwind.config.js` with the design system theme tokens (colors, border-radius, fonts, animations).',
    b'  3. A `postcss.config.js` for Tailwind processing.',
    b'  4. A `tsconfig.json` with @/ path aliases.',
    b'  5. A `vite.config.js` with React plugin and @/ path alias resolution.',
    b"  6. An `index.html` with Google Fonts (Inter) preloaded and entry point `src/main.tsx`.",
    b'  7. A `src/index.css` with Tailwind directives and light/dark mode CSS custom properties.',
    b'  8. A `src/lib/utils.ts` with the cn() helper (clsx + tailwind-merge).',
    b'  9. A `src/components/ui/` directory with shadcn/ui-style components (Button, Card, Input, Dialog, etc.).',
    b'  10. Entry point `src/main.tsx` and main component `src/App.tsx`.',
    b'- Update Parent Config: Always update the `root` setting in the parent `workspace/vite.config.js` to point to the newly created subdirectory.',
    b'- File extensions: Always use `.tsx` extensions for any files containing JSX syntax so bundlers like Vite can compile them successfully. Prefer TypeScript (.ts/.tsx) over JavaScript (.js/.jsx) for all new files.',
    b'- Configuration files: Configuration files (such as `vite.config.js`, `tailwind.config.js`, or `postcss.config.js`) must contain valid JavaScript/JSON module exports matching the configuration schema. Never write shell commands or CLI invocations inside configuration files.',
    b'',
    b'Lovable-Quality Styling & Design System Rules:',
    b'- Use Tailwind CSS as the primary styling system. Use theme tokens (bg-primary, text-muted-foreground, border-border, etc.) instead of raw color utilities (bg-blue-500, text-gray-600). Configure all custom colors as HSL CSS custom properties in tailwind.config.js.',
    b'- Use shadcn/ui components from `src/components/ui/` as the base building blocks. Never build raw HTML buttons, inputs, dialogs, tables, selects, or cards when shadcn/ui equivalents exist. If a component is missing, create it in `src/components/ui/` following the shadcn/ui pattern (CVA variants, cn() utility, forwardRef).',
    b'- Use the cn() utility from `@/lib/utils` for all conditional class composition. Never use string concatenation for Tailwind classes.',
    b'- Use CVA (class-variance-authority) for component variant management. Define variant objects for size, color, and state variations.',
    b'- Dark mode support: Use Tailwind `dark:` variants with CSS custom property-based theming. Toggle via adding/removing the `dark` class on the `<html>` element.',
    b'- Typography: Use Google Fonts Inter as the base font (already configured in tailwind.config.js). Use Tailwind typography utilities (text-lg, font-semibold, tracking-tight, leading-relaxed).',
    b'- Animations & Micro-interactions: Use Tailwind transition utilities (transition-all, duration-200, ease-in-out), hover effects (hover:scale-105, hover:shadow-lg), and custom keyframe animations (animate-fade-in, animate-slide-in) defined in tailwind.config.js.',
    b'- Glassmorphism: Use `backdrop-blur-md bg-white/80 dark:bg-gray-900/80 border border-white/20` for glass card effects.',
    b'- Smooth Gradients: Use Tailwind gradient utilities (bg-gradient-to-br from-primary/20 to-accent/10) for background effects.',
    b'- Responsive layouts: Design mobile-first using Tailwind breakpoints (sm:, md:, lg:, xl:). Use CSS Grid (grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3) and Flexbox (flex items-center justify-between) for layouts.',
    b'- Icons: Use Lucide React for all icons (import { IconName } from "lucide-react"). Never use emoji or text characters as icon substitutes.',
    b'- Component Architecture: Follow atomic design (atoms: Button, Badge, Input | molecules: SearchBar, StatCard | organisms: Sidebar, DataTable, Header | templates: DashboardLayout). Every page gets a dedicated layout component.',
    b'- React Router: Use react-router-dom for multi-page apps with <BrowserRouter>, <Routes>, <Route>, and <Outlet> for nested layouts.',
    b'',
    b'Frontend Anti-Patterns (NEVER DO):',
    b'- Never use inline styles or raw CSS when Tailwind equivalents exist.',
    b'- Never use placeholder text like "Lorem ipsum" or "TODO" in UI content. Use realistic mock data.',
    b'- Never leave unstyled native HTML elements (raw <table>, <select>, <input>). Wrap them in shadcn/ui components.',
    b'- Never use generic raw Tailwind colors (red-500, blue-600, gray-400). Always use theme tokens (primary, secondary, muted, accent, destructive).',
    b'- Never skip dark mode support. Every color must work in both light and dark themes via CSS custom properties.',
    b'- Never create flat, boring layouts. Use depth (shadows, borders, glassmorphism), hierarchy (font sizes, spacing), and visual rhythm (consistent gaps, alignment).',
    b'',
    b'Scaffold Completeness Constraint: If scaffold_react_app creates placeholder files, you MUST immediately modify those files to implement the full application logic and styling. Do not leave the placeholder code in place.',
]

new_block = NL.join(new_block_lines)

data = data[:start_idx] + new_block + data[end_idx:]

with open(filepath, 'wb') as f:
    f.write(data)

print("SUCCESS: Frontend/Web Project Rules replaced with Lovable-quality design system rules.")
