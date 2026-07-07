"""Binary-safe replacement of VALIDATION_SYSTEM_PROMPT in coding_worker.py"""

filepath = r'src/agents/coding_worker.py'
with open(filepath, 'rb') as f:
    data = f.read()

old = b'2. Writing, modifying, or analyzing React/JS/TS/TSX/JSX frontend or backend Node.js/Express code (including server.js, API routes, database connections, configuration, packaging, and build tools like Vite, Webpack, Babel, npm, etc.).'

new = b'2. Writing, modifying, or analyzing React/JS/TS/TSX/JSX frontend or backend Node.js/Express code (including server.js, API routes, database connections, configuration, packaging, and build tools like Vite, Webpack, Babel, npm, Tailwind CSS, PostCSS, shadcn/ui components, class-variance-authority, clsx, tailwind-merge, Lucide React icons, React Router, etc.).'

if old not in data:
    print('ERROR: Target string not found.')
else:
    data = data.replace(old, new, 1)
    with open(filepath, 'wb') as f:
        f.write(data)
    print('SUCCESS: VALIDATION_SYSTEM_PROMPT updated with new technologies.')
