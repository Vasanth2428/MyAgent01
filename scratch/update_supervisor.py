"""Binary-safe replacement of supervisor prompt frontend instruction in supervisor.py"""

filepath = r'src/graph/supervisor.py'
with open(filepath, 'rb') as f:
    data = f.read()

# Replace rule #2 (frontend task instruction)
old_rule2 = b'  2. For frontend tasks, explicitly instruct coding_worker to deliver premium design aesthetics that wow the user at first glance. Specify: custom HSL-tailored color palettes, dark/light mode toggles, glassmorphism with subtle backdrop-blur and borders, premium Google Fonts (Outfit, Inter, or Roboto), smooth linear gradients, subtle box shadows, responsive layouts, micro-animations, interactive transitions, and hover effects. Command the agent to use Vanilla CSS for maximum control unless TailwindCSS is explicitly requested. Never accept basic grey/white styling, native browser defaults, or placeholder designs.'

new_rule2 = b'  2. For frontend tasks, explicitly instruct coding_worker to produce Lovable-quality designs using the full modern stack: Tailwind CSS with HSL theme tokens (bg-primary, text-muted-foreground), shadcn/ui components (Button, Card, Input, Dialog, Table, Select, Tabs, Sheet), Lucide React icons, dark/light mode via CSS custom properties, glassmorphism (backdrop-blur-md), smooth gradients, responsive breakpoints (sm/md/lg/xl), micro-animations (transition-all, hover:scale-105, animate-fade-in), and Inter font from Google Fonts. Use the cn() utility for class composition and CVA for component variants. Never accept basic grey/white styling, native browser defaults, inline styles, or placeholder designs.'

if old_rule2 not in data:
    print('ERROR: Rule #2 target not found.')
    exit(1)

data = data.replace(old_rule2, new_rule2, 1)

# Now add new rule #6 (complex UI decomposition) after rule #4
old_rule4_end = b'  4. Ensure task instructions are concrete, specifying file paths and expected behaviors. Do not use vague or generic summaries.'

new_rule4_plus = (
    b'  4. Ensure task instructions are concrete, specifying file paths and expected behaviors. Do not use vague or generic summaries.\r\r\n'
    b'  6. For complex UIs (dashboards, admin panels, multi-page apps), decompose into sequential tasks: (a) Scaffold with design system via scaffold_react_app, (b) Create layout shell and navigation (Sidebar, Header, routing), (c) Build individual page components one at a time, (d) Add data integration and state management. Always instruct coding_worker to use shadcn/ui primitives (Button, Card, Dialog, Table, Input, Select, Tabs, Sheet) instead of building raw HTML equivalents.'
)

if old_rule4_end not in data:
    print('ERROR: Rule #4 target not found.')
    exit(1)

data = data.replace(old_rule4_end, new_rule4_plus, 1)

with open(filepath, 'wb') as f:
    f.write(data)

print('SUCCESS: Supervisor prompt updated with Lovable-quality frontend instructions and UI decomposition rule.')
